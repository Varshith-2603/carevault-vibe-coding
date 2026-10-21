"""Thin wrapper around the Anthropic SDK with the app's safety rules baked in.

* AI is available only when the server has credentials configured
  (``ANTHROPIC_API_KEY`` / ``ANTHROPIC_AUTH_TOKEN``, or ``MEDIONE_AI_ENABLED=1``
  when an ``ant auth login`` profile is used) and the user has given consent.
* Callers pass only the signed-in user's own data; nothing else is sent.
* Every response is JSON constrained by a schema, so it can be shown for review
  instead of being trusted blindly.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from medione import config

SYSTEM_PROMPT = """You assist a patient who is organising their own medical records in an app called Thought Medione.

Rules you must always follow:
- Use only the documents and records provided in this request. Never add facts from general knowledge about the patient.
- Never invent or guess names of medicines, doses, frequencies, dates, test values, doctors, hospitals or diagnoses. If something is missing, leave it empty (null). If something is hard to read or ambiguous, still give your best reading but mark it as uncertain and say why.
- Copy medical wording as written. Do not convert units or rewrite doses.
- You are not a doctor. Do not diagnose, do not judge whether results are good or bad beyond repeating the reference range printed on the report, and never suggest starting, stopping or changing any medicine or treatment. When the patient might need medical advice, tell them to ask their doctor.
- Never claim that anything has been checked or verified by a doctor.
- Write for a non-specialist in short, clear sentences."""


class AIUnavailable(Exception):
    """AI is not configured on this server or the user hasn't consented."""


class AIError(Exception):
    """The AI request failed; the message is safe to show to the user."""


def is_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                or os.environ.get("MEDIONE_AI_ENABLED", "").lower() in {"1", "true", "yes"})


_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic(timeout=180.0, max_retries=2)
    return _client


def set_client_for_tests(client: Any) -> None:
    global _client
    _client = client


def run_json(content: list[dict] | str, schema: dict, effort: str = "medium", max_tokens: int = 16000) -> dict:
    """Send one request and return the schema-validated JSON object."""
    if not is_configured() and _client is None:
        raise AIUnavailable("AI features aren't set up on this server.")
    import anthropic
    client = _get_client()
    try:
        response = client.beta.messages.create(
            model=config.settings.ai_model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.AuthenticationError as exc:
        raise AIError("The AI service rejected the server's credentials. Ask the administrator to check the API key.") from exc
    except anthropic.RateLimitError as exc:
        raise AIError("The AI service is busy right now. Please try again in a minute.") from exc
    except anthropic.BadRequestError as exc:
        raise AIError("The AI service couldn't process this file. Try a clearer scan or a PDF.") from exc
    except anthropic.APIStatusError as exc:
        raise AIError("The AI service returned an error. Please try again later.") from exc
    except anthropic.APIConnectionError as exc:
        raise AIError("Couldn't reach the AI service. Check the internet connection and try again.") from exc

    if response.stop_reason == "refusal":
        raise AIError("The AI service declined to process this request.")
    if response.stop_reason == "max_tokens":
        raise AIError("The document was too long to process in one go. Try uploading fewer pages.")
    text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AIError("The AI response couldn't be read. Please try again.") from exc


def nullable(schema: dict) -> dict:
    return {"anyOf": [schema, {"type": "null"}]}


def obj(properties: dict) -> dict:
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


STR = {"type": "string"}
NSTR = nullable(STR)
NNUM = nullable({"type": "number"})
BOOL = {"type": "boolean"}


def file_block(data: bytes, mime: str) -> Optional[dict]:
    import base64
    b64 = base64.standard_b64encode(data).decode("ascii")
    if mime == "application/pdf":
        return {"type": "document", "source": {"type": "base64", "media_type": mime, "data": b64}}
    if mime in {"image/jpeg", "image/png", "image/webp", "image/gif"}:
        return {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}}
    return None
