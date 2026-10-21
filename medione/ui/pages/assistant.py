"""AI consent panel (used in Settings). The AI helper itself now lives in the floating Medi chatbot."""
from __future__ import annotations

import streamlit as st

from medione import auth
from medione.ui.state import Ctx, flash

CONSENT_TEXT = """**Before you turn on AI features**

- When you use an AI feature (Medi's open questions, document reading or explanations), the relevant records or
  document from the **currently selected profile** are sent to Anthropic's Claude API to be processed. Nothing is
  sent until you ask.
- The AI can misread documents or make mistakes. Everything it produces is labelled, and extracted details are
  saved only after you review them.
- The AI does not diagnose and will not tell you to start, stop or change any treatment.
- You can turn this off at any time in Settings. Turning it off doesn't delete AI summaries already saved."""


def _consent(uid: int) -> None:
    auth.set_ai_consent(uid, True)
    flash("AI features turned on.")


def consent_panel(ctx: Ctx, key: str) -> None:
    with st.container(border=True):
        st.markdown(CONSENT_TEXT)
        if ctx.profile["relationship"] != "self":
            st.caption("For family members, make sure they (or you as their guardian) agree to this processing.")
        ok = st.checkbox("I understand and agree", key=f"{key}_ok")
        st.button("Turn on AI features", disabled=not ok, on_click=_consent, args=(ctx.uid,), key=f"{key}_btn",
                  type="primary")
