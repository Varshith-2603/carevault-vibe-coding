"""How the app works, privacy and safety notes."""
from __future__ import annotations

import streamlit as st

from medione.ui.state import Ctx
from medione.ui.widgets import page_header


def render(ctx: Ctx) -> None:
    page_header("Help & privacy")
    st.error("**In a medical emergency call 112** (national emergency number, India) or 108 for an ambulance.")
    st.markdown("""
#### Getting started
1. **Add record** → upload a prescription, report or discharge summary (PDF or photo), or type the details in.
2. If AI reading is on, check what it read against the original and tick *I have checked these details* before saving.
3. Use **Timeline** to see everything in date order and **Records** to search.
4. Set **Reminders** for medicines and follow-ups, and add them to your phone calendar.
5. **Share** selected records with a doctor through a link that expires.
6. Stuck? Tap **Medi**, the little robot in the bottom-right corner, and ask — e.g. *“latest blood test”* or *“how do I share records?”*

#### What the labels mean
- **Entered by you** — you typed it in.
- **AI-extracted · not yet reviewed** — read from a document by AI; may contain mistakes until you check it.
- **AI-extracted · reviewed by you** — read by AI and checked by you against the original.
- **Verified by a clinician** — reserved for future verified connections with healthcare providers. Nothing in the app has this label today.

#### Your privacy
- Your records are visible only to you after you sign in. Original files are stored encrypted.
- Share links show only the records you chose, stop working when they expire or when you turn them off, and every visit is logged.
- AI features are off until you turn them on. When used, the relevant records are sent to Anthropic's Claude API for processing.
- You can download all your data or delete your account at any time (Settings).

#### What Thought Medione does not do
- It does not diagnose, interpret results for you, or recommend starting, stopping or changing treatment.
- It does not contact doctors, hospitals or pharmacies on your behalf.
- It is not connected to any hospital system.
""")
