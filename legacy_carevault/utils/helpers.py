import html
import math
from pathlib import Path
from datetime import date, datetime
from typing import Any
import streamlit as st

CSS_PATH = Path(__file__).resolve().parent.parent / "assets" / "styles.css"

NOT_RECORDED = "Not recorded"


@st.cache_data(show_spinner=False)
def _read_css(path: str, mtime: float) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_custom_css():
    """Inject the custom CSS into the Streamlit app."""
    if CSS_PATH.exists():
        css_content = _read_css(str(CSS_PATH), CSS_PATH.stat().st_mtime)
        st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)


def is_missing(value: Any) -> bool:
    """True for None, NaN, and blank strings — the ways missing data shows up in session DataFrames."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    try:
        import pandas as pd
        if value is pd.NA or value is pd.NaT:
            return True
    except Exception:
        pass
    return isinstance(value, str) and not value.strip()


def display(value: Any, missing: str = NOT_RECORDED) -> str:
    """Return a plain-text display value, using a clear label when data is missing."""
    if is_missing(value):
        return missing
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def esc(value: Any, missing: str = NOT_RECORDED) -> str:
    """HTML-escaped display value. Use for every user-editable value placed in custom HTML."""
    return html.escape(display(value, missing))


def parse_date(value: Any):
    """Parse an ISO date string (or date) into a date, returning None when unavailable."""
    if is_missing(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def format_date(date_str: Any) -> str:
    """Format YYYY-MM-DD to DD Mon YYYY."""
    parsed = parse_date(date_str)
    if parsed is None:
        return NOT_RECORDED if is_missing(date_str) else str(date_str)
    return parsed.strftime("%d %b %Y")


def relative_day(value: Any, today: date | None = None) -> str:
    """Human phrasing such as 'Today', 'In 9 days' or '3 months ago'."""
    d = parse_date(value)
    if d is None:
        return ""
    today = today or date.today()
    delta = (d - today).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Tomorrow"
    if delta == -1:
        return "Yesterday"
    days = abs(delta)
    if days < 31:
        unit = f"{days} days"
    elif days < 365:
        months = round(days / 30.4)
        unit = f"{months} month{'s' if months != 1 else ''}"
    else:
        years = round(days / 365, 1)
        unit = f"{years:g} year{'s' if years != 1 else ''}"
    return f"In {unit}" if delta > 0 else f"{unit} ago"


def greeting(now: datetime | None = None) -> str:
    hour = (now or datetime.now()).hour
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    return "Good evening"


def initials(name: str) -> str:
    parts = [p for p in str(name).split() if p]
    if not parts:
        return "?"
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()


# --------------------------------------------------------------------------
# Status badges — every badge pairs colour with a text glyph so meaning never
# relies on colour alone.
# --------------------------------------------------------------------------
_BADGE_GLYPHS = {
    "badge-ready": "✓",
    "badge-processing": "◷",
    "badge-danger": "!",
    "badge-info": "•",
    "badge-neutral": "–",
    "badge-stopped": "✕",
}


def get_badge_class(status: str) -> str:
    s = str(status).lower()
    if any(k in s for k in ["critical", "danger", "allergy", "severe"]):
        return "badge-danger"
    if any(k in s for k in ["cancel", "unavailable", "discontinued"]):
        return "badge-stopped"
    if any(k in s for k in ["completed", "final", "ready", "active", "optimal", "sufficient", "discharged"]):
        return "badge-ready"
    if any(k in s for k in ["processing", "pending", "in progress", "on hold", "inpatient"]):
        return "badge-processing"
    if any(k in s for k in ["upcoming", "scheduled", "follow-up"]):
        return "badge-info"
    return "badge-neutral"


def render_badge(status_text: str) -> str:
    text = display(status_text, "Unknown")
    cls = get_badge_class(text)
    glyph = _BADGE_GLYPHS.get(cls, "•")
    return f'<span class="cv-badge {cls}"><span aria-hidden="true">{glyph}</span>{html.escape(text)}</span>'


def render_empty_state(title: str = "No records found", message: str = "Try searching with a different keyword or filter.", icon: str = "🔍"):
    st.markdown(
        f"""
        <div class="empty-state-box" role="status">
            <div class="empty-state-icon" aria-hidden="true">{icon}</div>
            <div class="empty-state-title">{html.escape(title)}</div>
            <div class="empty-state-text">{html.escape(message)}</div>
        </div>
        """,
        unsafe_allow_html=True
    )


def render_disclaimer():
    st.markdown(
        """
        <div class="disclaimer-banner" role="note">
            <strong>Demo data.</strong>&nbsp;All patients, records and facilities shown are fictional.
            CareVault keeps records for reference only — it does not give medical advice.
            Always confirm medical information with a qualified healthcare professional.
        </div>
        """,
        unsafe_allow_html=True
    )
