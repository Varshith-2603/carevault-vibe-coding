"""Medi: the floating, animated helper toy and its chat panel (bottom-right on every signed-in page)."""
from __future__ import annotations

import streamlit as st

from medione.ai.client import is_configured
from medione.services import helpbot
from medione.ui.state import Ctx, go, open_record

AI_OVERVIEW = "Summarise my history with AI"

MASCOT = """
<div class="tm-toy" aria-hidden="true">
  <div class="tm-bubble">May I help you?</div>
  <svg class="tm-bot" viewBox="0 0 120 130" width="92" height="100">
    <defs>
      <linearGradient id="tmHead" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2DD4BF"/><stop offset="1" stop-color="#0E7490"/></linearGradient>
      <linearGradient id="tmBody" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#14B8A6"/><stop offset="1" stop-color="#0F766E"/></linearGradient>
    </defs>
    <ellipse cx="60" cy="124" rx="30" ry="5" fill="#0F2A33" opacity=".15" class="tm-shadow"/>
    <line x1="60" y1="14" x2="60" y2="26" stroke="#0E7490" stroke-width="4" stroke-linecap="round"/>
    <circle cx="60" cy="11" r="6" fill="#F59E0B" class="tm-ant"/>
    <g class="tm-arm"><rect x="94" y="72" width="10" height="28" rx="5" fill="#0F766E"/><circle cx="99" cy="70" r="7" fill="#2DD4BF"/></g>
    <rect x="16" y="76" width="10" height="26" rx="5" fill="#0F766E"/>
    <rect x="26" y="68" width="68" height="46" rx="16" fill="url(#tmBody)"/>
    <rect x="52" y="78" width="16" height="26" rx="3" fill="#fff"/><rect x="47" y="83" width="26" height="16" rx="3" fill="#fff"/>
    <rect x="53" y="84" width="14" height="14" rx="2" fill="#EF4444"/><rect x="58" y="80" width="4" height="22" fill="#EF4444"/>
    <rect x="18" y="24" width="84" height="50" rx="22" fill="url(#tmHead)"/>
    <rect x="28" y="33" width="64" height="33" rx="15" fill="#F0FDFA"/>
    <g class="tm-eyes"><ellipse cx="47" cy="47" rx="5.5" ry="6.5" fill="#0F2A33"/><ellipse cx="73" cy="47" rx="5.5" ry="6.5" fill="#0F2A33"/>
      <circle cx="49" cy="45" r="1.8" fill="#fff"/><circle cx="75" cy="45" r="1.8" fill="#fff"/></g>
    <path d="M51 57 Q60 64 69 57" stroke="#0F2A33" stroke-width="3" fill="none" stroke-linecap="round"/>
    <circle cx="36" cy="57" r="4" fill="#FDA4AF" opacity=".7"/><circle cx="84" cy="57" r="4" fill="#FDA4AF" opacity=".7"/>
  </svg>
</div>"""


def _ai_ready(ctx: Ctx) -> bool:
    return is_configured() and bool(ctx.user.ai_consent_at)


def _greeting(ctx: Ctx) -> dict:
    name = ctx.profile["full_name"].split()[0]
    text = (f"Hi {ctx.user.display_name}! I'm **Medi** 👋 — your Thought Medione helper.\n\n"
            f"I'm looking at **{name}'s** records. Ask me about appointments, medicines, reports, or how to use the app.")
    if is_configured() and not ctx.user.ai_consent_at:
        text += "\n\n*Tip: switch on AI features in Settings and I can answer more open questions.*"
    return {"role": "assistant", "text": text, "source": "", "records": [], "actions": [],
            "suggestions": helpbot.GREETING_SUGGESTIONS}


def _toggle(ctx: Ctx) -> None:
    st.session_state["bot_open"] = not st.session_state.get("bot_open", False)
    if st.session_state["bot_open"] and not st.session_state.get("bot_msgs"):
        st.session_state["bot_msgs"] = [_greeting(ctx)]


def _ask(ctx: Ctx, question: str) -> None:
    question = (question or "").strip()[:500]
    if not question:
        return
    msgs = st.session_state.setdefault("bot_msgs", [_greeting(ctx)])
    msgs.append({"role": "user", "text": question})
    if question == AI_OVERVIEW and _ai_ready(ctx):
        r = helpbot.ai_history_overview(ctx.uid, ctx.pid)
    else:
        r = helpbot.answer(ctx.uid, ctx.pid, question, ctx.profile["full_name"].split()[0],
                           history=[m for m in msgs if m["role"] in ("user", "assistant")], ai_ready=_ai_ready(ctx))
    msgs.append({"role": "assistant", "text": r.text, "source": r.source, "records": r.records,
                 "actions": r.actions, "suggestions": r.suggestions, "urgent": r.urgent})
    del msgs[:-30]


def _ask_from_input(ctx: Ctx) -> None:
    _ask(ctx, st.session_state.get("bot_input", ""))
    st.session_state["bot_input"] = ""


def _clear(ctx: Ctx) -> None:
    st.session_state["bot_msgs"] = [_greeting(ctx)]


def render(ctx: Ctx) -> None:
    is_open = st.session_state.get("bot_open", False)
    with st.container(key="tm_bot_open" if is_open else "tm_bot"):
        st.markdown(MASCOT, unsafe_allow_html=True)
        st.button("Close Medi, the help assistant" if is_open else "Open Medi, the help assistant",
                  key="tm_bot_toggle", on_click=_toggle, args=(ctx,))
    if not is_open:
        return
    with st.container(key="tm_bot_panel"):
        st.markdown('<div class="tm-bot-head"><div class="av"><svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round"><rect x="4" y="7" width="16" height="12" rx="4"/><path d="M12 3v4"/><circle cx="9" cy="13" r="1.2" fill="#fff"/><circle cx="15" cy="13" r="1.2" fill="#fff"/></svg></div><div><b>Medi</b><span>Your Thought Medione helper'
                    '</span></div></div>', unsafe_allow_html=True)
        st.button("✕", key="tm_bot_close", on_click=_toggle, args=(ctx,), help="Close")
        msgs = st.session_state.setdefault("bot_msgs", [_greeting(ctx)])
        with st.container(height=340, key="tm_bot_msgs", border=False):
            for i, m in enumerate(msgs):
                with st.chat_message(m["role"], avatar=":material/smart_toy:" if m["role"] == "assistant" else ":material/person:"):
                    if m.get("urgent"):
                        st.error(m["text"])
                    else:
                        st.markdown(m["text"])
                    for r in m.get("records", []):
                        date = r.get("date") or "no date"
                        st.button(f"📄 {date} · {r['title']}", key=f"bot_rec_{i}_{r['id']}", on_click=open_record,
                                  args=(r["id"],), width="stretch")
                    for label, page in m.get("actions", []):
                        st.button(label, key=f"bot_act_{i}_{page}", on_click=go, args=(page,), type="tertiary",
                                  icon=":material/arrow_forward:")
                    if m.get("source"):
                        st.caption(f"Source: {m['source']}")
            last = msgs[-1]
            suggestions = last.get("suggestions") or []
            if _ai_ready(ctx) and AI_OVERVIEW not in suggestions and last.get("role") == "assistant" and len(msgs) == 1:
                suggestions = [*suggestions, AI_OVERVIEW]
            if suggestions:
                for j, s in enumerate(suggestions):
                    st.button(s, key=f"bot_sug_{len(msgs)}_{j}", on_click=_ask, args=(ctx, s), type="secondary")
        with st.form("bot_form", clear_on_submit=False, border=False):
            c1, c2 = st.columns([5, 1.4], vertical_alignment="bottom")
            c1.text_input("Ask Medi", key="bot_input", placeholder="Ask about your records or the app…",
                          label_visibility="collapsed")
            c2.form_submit_button("Send", on_click=_ask_from_input, args=(ctx,), type="primary", width="stretch")
        c1, c2 = st.columns([3, 1])
        c1.caption("Medi doesn't give medical advice. Emergency: call 112.")
        c2.button("Clear", key="bot_clear", on_click=_clear, args=(ctx,), type="tertiary")
