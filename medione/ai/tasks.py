"""The AI tasks the app offers. Results are always shown to the user, labelled as AI output."""
from __future__ import annotations

import json
from datetime import date
from typing import Optional

from medione.ai.client import BOOL, NNUM, NSTR, STR, AIError, file_block, obj, run_json
from medione.models import RECORD_TYPES

EXTRA_NAMES = sorted({e.name for t in RECORD_TYPES.values() for e in t.extras})

EXTRACTION_SCHEMA = obj({
    "document_type": {"type": "string", "enum": list(RECORD_TYPES)},
    "title": STR,
    "record_date": NSTR,
    "end_date": NSTR,
    "follow_up_date": NSTR,
    "doctor_name": NSTR,
    "facility_name": NSTR,
    "condition": NSTR,
    "summary": NSTR,
    "extra_fields": {"type": "array", "items": obj({"name": {"type": "string", "enum": EXTRA_NAMES}, "value": STR})},
    "medications": {"type": "array", "items": obj({
        "name": STR, "dosage": NSTR, "frequency": NSTR, "duration": NSTR, "route": NSTR, "instructions": NSTR,
        "uncertain": BOOL, "uncertain_reason": NSTR})},
    "lab_results": {"type": "array", "items": obj({
        "test_name": STR, "value": STR, "unit": NSTR, "ref_low": NNUM, "ref_high": NNUM, "ref_text": NSTR,
        "uncertain": BOOL})},
    "uncertain_fields": {"type": "array", "items": STR},
    "legibility_note": NSTR,
})

EXTRACTION_PROMPT = f"""Read the attached medical document and fill in the JSON fields.

- document_type: the best match from the allowed list. Use "other" if none fits.
- title: a short neutral title, e.g. "Complete blood count" or "Prescription – Dr. A. Kumar".
- Dates: YYYY-MM-DD only when the full date is written. If only part is legible, use null and list the field in uncertain_fields.
- record_date is the date of the visit/test/prescription; end_date only for discharge dates. follow_up_date: a written follow-up/review date; if only a relative one is written (e.g. "review after 2 weeks") and record_date is known, calculate it and list "follow_up_date" in uncertain_fields.
- For each medicine copy the frequency exactly as written (e.g. "1-0-1", "BD", "twice daily", "SOS") and the duration (e.g. "5 days").
- doctor_name / facility_name exactly as written. Do not add titles, specialties or affiliations that aren't written.
- condition only if a diagnosis/condition is explicitly written by the clinician.
- summary: 1–3 sentences restating what the document says, without interpretation.
- extra_fields: only fields that apply ({', '.join(EXTRA_NAMES)}), with text copied as written.
- medications: one entry per medicine exactly as written. Set uncertain=true and explain if handwriting, spelling, dose or frequency is unclear.
- lab_results: one entry per test with the value as printed, the unit, and the reference range printed on the report (numbers in ref_low/ref_high when given as a range, otherwise ref_text). Do not add ranges that aren't printed.
- uncertain_fields: names of any top-level fields you were unsure about.
- legibility_note: a short note if parts of the document were unreadable, else null.
Today's date is {{today}}."""


def extract_document(data: bytes, mime: str, text_layer: Optional[str] = None) -> dict:
    block = file_block(data, mime)
    if block is None:
        raise AIError("This file type can't be read by the AI.")
    content = [block, {"type": "text", "text": EXTRACTION_PROMPT.replace("{today}", date.today().isoformat())}]
    result = run_json(content, EXTRACTION_SCHEMA, effort="high")
    if result.get("document_type") not in RECORD_TYPES:
        result["document_type"] = "other"
    return result


SUMMARY_SCHEMA = obj({
    "overview": STR,
    "key_points": {"type": "array", "items": STR},
    "gaps_or_conflicts": {"type": "array", "items": STR},
    "questions_for_doctor": {"type": "array", "items": STR},
})


def summarise_history(structured_summary: dict) -> dict:
    payload = json.dumps(structured_summary, default=str)[:180_000]
    prompt = ("Below are the patient's stored records as JSON. Write a concise, chronological overview a patient "
              "could read before seeing a doctor. key_points: the most important documented facts with dates. "
              "gaps_or_conflicts: missing information, contradictory entries, or items marked uncertain / not reviewed. "
              "questions_for_doctor: neutral questions the patient might ask (no advice). Use only this data.\n\n"
              f"<records>{payload}</records>")
    return run_json(prompt, SUMMARY_SCHEMA)


DOC_SUMMARY_SCHEMA = obj({"summary": STR, "terms_explained": {"type": "array", "items": obj({"term": STR, "meaning": STR})},
                          "unclear_parts": NSTR})


def summarise_document(data: bytes, mime: str) -> dict:
    block = file_block(data, mime)
    if block is None:
        raise AIError("This file type can't be read by the AI.")
    prompt = ("Explain this medical document in plain language for the patient: what kind of document it is, "
              "what it states, and any medical terms (with simple meanings). Do not interpret beyond what is written "
              "and do not give advice. Mention any part you couldn't read in unclear_parts.")
    return run_json([block, {"type": "text", "text": prompt}], DOC_SUMMARY_SCHEMA)


EXPLAIN_SCHEMA = obj({"term": STR, "plain_explanation": STR, "where_it_appears": NSTR, "ask_your_doctor": STR})


def explain_term(term: str, context: str = "") -> dict:
    term = term.strip()[:200]
    prompt = (f"Explain the medical term or abbreviation \"{term}\" in plain language (3–5 sentences) for a patient. "
              "Give general meaning only — do not say whether it applies to them, and give no treatment advice. "
              "In ask_your_doctor, suggest one neutral question they could ask their doctor."
              + (f"\nIt appeared in this context from their own record: <context>{context[:2000]}</context>" if context else ""))
    return run_json(prompt, EXPLAIN_SCHEMA, effort="low")


SEARCH_SCHEMA = obj({
    "keywords": STR,
    "record_types": {"type": "array", "items": {"type": "string", "enum": list(RECORD_TYPES)}},
    "date_from": NSTR, "date_to": NSTR,
    "doctor": NSTR, "facility": NSTR, "condition": NSTR, "medication": NSTR, "test": NSTR,
    "explanation": STR,
})


def interpret_search(question: str, known: dict) -> dict:
    """Turn a natural-language question into filters. The app then runs a normal search on real records."""
    prompt = (f"Today's date is {date.today().isoformat()}. Convert the patient's request into search filters for "
              "their record library. Only use doctor/facility/condition/medication/test values from the known lists "
              "(pick the closest match) or null. keywords: remaining important words (may be empty). Dates YYYY-MM-DD. "
              "explanation: one short sentence describing the filters.\n"
              f"<known>{json.dumps(known)[:20000]}</known>\n<request>{question.strip()[:500]}</request>")
    return run_json(prompt, SEARCH_SCHEMA, effort="low")


DOC_QA_SCHEMA = obj({
    "answer_from_document": STR,
    "general_information": NSTR,
    "uncertain_parts": NSTR,
    "questions_for_doctor": {"type": "array", "items": STR},
})


def ask_document(data: bytes, mime: str, question: str) -> dict:
    """Answer a question about one document, keeping what the document says separate from general knowledge."""
    block = file_block(data, mime)
    if block is None:
        raise AIError("This file type can't be read by the AI.")
    prompt = ("The patient asks a question about the attached medical document.\n"
              "- answer_from_document: answer ONLY from what the document says, quoting values exactly. If the document "
              "doesn't say, write that it isn't stated in this document.\n"
              "- general_information: optional plain-language background that is NOT from the document (or null).\n"
              "- uncertain_parts: anything unreadable or ambiguous (or null).\n"
              "- questions_for_doctor: 0–4 neutral questions they could ask.\n"
              "Never diagnose and never suggest starting, stopping or changing treatment.\n"
              f"<question>{question.strip()[:800]}</question>")
    return run_json([block, {"type": "text", "text": prompt}], DOC_QA_SCHEMA)


CHAT_SCHEMA = obj({
    "answer": STR,
    "uses_their_records": BOOL,
    "see_doctor_note": NSTR,
})


def chat_answer(question: str, history: list[dict], records_json: str, faq_text: str) -> dict:
    """Free-form help-desk answer. Grounded in the app FAQ and the active profile's own record summary."""
    turns = "\n".join(f"{t['role']}: {t['text'][:400]}" for t in history[-6:])
    prompt = ("You are Medi, the friendly in-app helper of Thought Medione (a personal health records app). Answer in "
              "2–6 short sentences of plain language. Use the app guide for how-to questions and the patient's record "
              "summary for questions about their own health information — cite record names and dates you used. If "
              "the records don't contain the answer, say so; never invent records, results or doses. General health "
              "information is fine, but no diagnosis and no advice to start, stop or change any treatment. "
              "see_doctor_note: a short nudge to consult a doctor when the question needs clinical judgement, else null.\n"
              f"<app_guide>{faq_text[:12000]}</app_guide>\n<patient_records>{records_json[:60000]}</patient_records>\n"
              f"<recent_chat>{turns}</recent_chat>\n<question>{question.strip()[:800]}</question>")
    return run_json(prompt, CHAT_SCHEMA, effort="low")
