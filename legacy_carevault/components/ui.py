"""CareVault design-system primitives.

Every page builds from these helpers so cards, badges, detail grids, empty
states and record rows look and behave the same everywhere.
"""
import html
import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd
import streamlit as st

from components.state import open_dialog
from datetime import date

from utils.helpers import display, esc, format_date, is_missing, parse_date, relative_day, render_badge
from utils.records import RECORD_TYPES, record_subtitle, record_title, record_status, vitals_summary

# Lucide-style line icons (24px grid, stroke inherits currentColor)
_ICON_PATHS = {
    "calendar": '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    "hospital": '<path d="M3 21h18M5 21V7l7-4 7 4v14M10 21v-4h4v4M12 8v4M10 10h4"/>',
    "flask": '<path d="M9 3h6M10 3v6l-5.4 9.4A2 2 0 0 0 6.3 21h11.4a2 2 0 0 0 1.7-2.6L14 9V3"/><path d="M7.5 15h9"/>',
    "pill": '<path d="m10.5 20.5 10-10a4.95 4.95 0 1 0-7-7l-10 10a4.95 4.95 0 1 0 7 7Z"/><path d="m8.5 8.5 7 7"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
    "heart": '<path d="M19 14c1.5-1.5 3-3.2 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.8 0-3 .5-4.5 2-1.5-1.5-2.7-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4 3 5.5l7 7Z"/><path d="M3.2 12h6.3l.5-1 2 4.5 2-7 1.5 3.5h5.3"/>',
    "alert": '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/>',
    "history": '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l4 2"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "file": '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z"/><path d="M14 3v6h6M8 13h8M8 17h5"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
}

KIND_ICON = {"visit": "hospital", "diagnostic": "flask", "prescription": "pill", "history": "history",
             "appointment": "calendar", "vital": "heart"}
KIND_TONE = {"visit": "teal", "diagnostic": "blue", "prescription": "amber", "history": "slate",
             "appointment": "blue", "vital": "rose"}


def icon(name: str, size: int = 18) -> str:
    path = _ICON_PATHS.get(name, _ICON_PATHS["folder"])
    return (f'<svg class="cv-svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{path}</svg>')


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")


def html_block(markup: str):
    """Render trusted HTML. Indentation and blank lines are removed so Markdown never turns
    an indented line into a code block."""
    compact = "\n".join(line.strip() for line in markup.splitlines() if line.strip())
    st.markdown(compact, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Headings
# --------------------------------------------------------------------------
def section_header(title: str, caption: str = "", level: int = 2):
    tag = f"h{level}"
    cap = f'<p class="cv-section-caption">{html.escape(caption)}</p>' if caption else ""
    html_block(f'<div class="cv-section-head"><{tag} class="cv-section-title">{html.escape(title)}</{tag}>{cap}</div>')


def demo_pill() -> str:
    return '<span class="cv-demo-pill" title="This is fictional sample data">Demo data</span>'


# --------------------------------------------------------------------------
# Cards
# --------------------------------------------------------------------------
def stat_card(
    key: str,
    label: str,
    value: Any,
    sub: str = "",
    icon_name: str = "folder",
    tone: str = "blue",
    action_label: Optional[str] = None,
    on_click: Optional[Callable] = None,
    args: tuple = (),
    kwargs: Optional[dict] = None,
):
    """Summary card with an optional action button that sits inside the card."""
    with st.container(border=True, key=f"cvstat_{key}"):
        html_block(
            f"""
            <div class="stat-card-inner">
                <div class="stat-header">
                    <div class="stat-label">{html.escape(label)}</div>
                    <div class="stat-icon-wrapper tone-{tone}">{icon(icon_name)}</div>
                </div>
                <div class="stat-value">{html.escape(str(value))}</div>
                <div class="stat-subtext">{sub}</div>
            </div>
            """
        )
        if action_label and on_click:
            st.button(action_label, key=f"cvstat_btn_{key}", type="tertiary", on_click=on_click,
                      args=args, kwargs=kwargs or {}, icon=":material/arrow_forward:", icon_position="right")


def stat_grid(key: str):
    """Horizontal, wrapping container for stat cards (wraps to fewer columns on narrow screens)."""
    return st.container(horizontal=True, gap="small", key=f"cvgrid_{key}")


def info_grid(pairs: Sequence[Tuple[str, Any]], missing: str = "Not recorded", cols: int = 2) -> str:
    items = "".join(
        f'<div class="cv-info-item"><dt>{html.escape(label)}</dt><dd>{value if isinstance(value, Raw) else esc(value, missing)}</dd></div>'
        for label, value in pairs
    )
    return f'<dl class="cv-info-grid cols-{cols}">{items}</dl>'


class Raw(str):
    """Marks pre-built, already-escaped HTML so ``info_grid`` doesn't escape it again."""


def text_panel(label: str, text: Any, tone: str = "neutral", missing: str = "Not recorded") -> str:
    body = "<br>".join(esc(text, missing).splitlines())
    missing_cls = " is-missing" if is_missing(text) else ""
    return (f'<div class="cv-panel tone-{tone}"><div class="cv-panel-label">{html.escape(label)}</div>'
            f'<div class="cv-panel-body{missing_cls}">{body}</div></div>')


def notice(text: str, tone: str = "info", icon_name: str = "alert") -> str:
    return f'<div class="cv-notice tone-{tone}" role="note">{icon(icon_name, 16)}<div>{text}</div></div>'


def field_error(message: str):
    html_block(f'<div class="cv-field-error" role="alert">{icon("alert", 14)}<span>{html.escape(message)}</span></div>')


# --------------------------------------------------------------------------
# Record rows (list view) — works as a table row on desktop and a card on mobile
# --------------------------------------------------------------------------
def _row_meta(kind: str, rec: Dict[str, Any]) -> List[Tuple[str, str]]:
    if kind == "visit":
        return [("Date", format_date(rec.get("date"))), ("Hospital", display(rec.get("hospital_name"))),
                ("Department", display(rec.get("department"))), ("Doctor", display(rec.get("attending_physician")))]
    if kind == "diagnostic":
        return [("Date", format_date(rec.get("date"))), ("Category", display(rec.get("category"))),
                ("Facility", display(rec.get("facility"))), ("Ordered by", display(rec.get("ordering_doctor")))]
    if kind == "prescription":
        refills = rec.get("refills_remaining")
        return [("Dose & frequency", f"{display(rec.get('dosage'))} · {display(rec.get('frequency'))}"),
                ("Prescribed by", display(rec.get("prescribing_doctor"))),
                ("Dates", f"{format_date(rec.get('start_date'))} → {format_date(rec.get('end_date')) if not is_missing(rec.get('end_date')) else 'No end date'}"),
                ("Refills left", display(refills, "Not recorded"))]
    if kind == "history":
        return [("Dose", display(rec.get("dosage"))), ("Recorded reason", display(rec.get("reason"))),
                ("Dates", f"{format_date(rec.get('start_date'))} → {format_date(rec.get('end_date'))}"),
                ("Prescribed by", display(rec.get("prescribed_by")))]
    if kind == "appointment":
        return [("Date & time", f"{format_date(rec.get('date'))} · {display(rec.get('time'), 'Time not set')}"),
                ("Doctor", display(rec.get("doctor"))), ("Department", display(rec.get("department"))),
                ("Facility", display(rec.get("facility")))]
    if kind == "vital":
        return [("Date", format_date(rec.get("date"))), ("Measurements", vitals_summary(rec)),
                ("Measured with", display(rec.get("recorded_by")))]
    return []


def record_row(kind: str, rec: Dict[str, Any], key_prefix: str, show_edit: bool = True, extra_note: str = ""):
    rt = RECORD_TYPES[kind]
    rid = rec[rt.id_col]
    meta = "".join(
        f'<div class="cv-row-meta"><span class="cv-row-meta-label">{html.escape(lbl)}</span>'
        f'<span class="cv-row-meta-value">{html.escape(val)}</span></div>'
        for lbl, val in _row_meta(kind, rec)
    )
    when = relative_day(rec.get(rt.date_col)) if kind == "appointment" and rec.get("status") == "Upcoming" else ""
    when_html = f'<span class="cv-when">{html.escape(when)}</span>' if when else ""
    if kind == "vital" and (parse_date(rec.get("date")) or date.min) > date.today():
        when_html += '<span class="cv-badge badge-processing"><span aria-hidden="true">!</span>Future date — not in charts</span>'
    note_html = f'<div class="cv-row-note">{extra_note}</div>' if extra_note else ""
    with st.container(border=True, key=f"cvrow_{key_prefix}_{slug(rid)}"):
        left, right = st.columns([5, 1.35], vertical_alignment="center", gap="small")
        with left:
            html_block(
                f"""
                <div class="cv-row">
                    <div class="cv-row-icon tone-{KIND_TONE[kind]}">{icon(KIND_ICON[kind])}</div>
                    <div class="cv-row-main">
                        <div class="cv-row-top">
                            <span class="cv-row-title">{esc(record_title(kind, rec))}</span>
                            {render_badge(record_status(kind, rec)) if kind != 'vital' else ''}{when_html}
                        </div>
                        <div class="cv-row-grid">{meta}</div>
                        {note_html}
                    </div>
                </div>
                """
            )
        with right:
            st.button("View details", key=f"{key_prefix}_view_{rid}", on_click=open_dialog, args=(kind, rid, "view"),
                      icon=":material/visibility:", width="stretch",
                      help=f"Open the full {rt.label.lower()} record")
            if show_edit:
                st.button("Edit", key=f"{key_prefix}_edit_{rid}", on_click=open_dialog, args=(kind, rid, "edit"),
                          icon=":material/edit:", type="tertiary", width="stretch")


def paginate(df: pd.DataFrame, key: str, page_size: int = 10) -> pd.DataFrame:
    """Return the visible slice; renders a 'Show more' control below the list when needed."""
    limit_key = f"_cv_limit_{key}"
    limit = st.session_state.get(limit_key, page_size)
    return df.head(limit)


def show_more(df_len: int, key: str, page_size: int = 10):
    limit_key = f"_cv_limit_{key}"
    limit = st.session_state.get(limit_key, page_size)
    if df_len > limit:
        def _more():
            st.session_state[limit_key] = limit + page_size
        st.button(f"Show more ({df_len - limit} remaining)", key=f"{key}_more", on_click=_more,
                  icon=":material/expand_more:", width="stretch")


def render_record_list(kind: str, df: pd.DataFrame, key: str, empty_title: str, empty_message: str,
                       page_size: int = 10, show_edit: bool = True):
    from utils.helpers import render_empty_state
    if df.empty:
        render_empty_state(empty_title, empty_message, "🗂️")
        return
    visible = paginate(df, key, page_size)
    for rec in visible.to_dict(orient="records"):
        record_row(kind, rec, key, show_edit=show_edit)
    show_more(len(df), key, page_size)


def results_bar(shown: int, total: int, noun: str, extra: str = ""):
    html_block(
        f'<div class="cv-results-bar" role="status" aria-live="polite"><span>Showing <strong>{shown}</strong> of {total} {html.escape(noun)}</span>'
        f'<span class="cv-results-extra">{html.escape(extra)}</span></div>'
    )
