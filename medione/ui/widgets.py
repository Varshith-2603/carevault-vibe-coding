"""Reusable display helpers. All user content is HTML-escaped before it is rendered."""
from __future__ import annotations

import html
from datetime import date
from typing import Callable, Iterable, Optional

import streamlit as st

from medione.models import RECORD_TYPES, SOURCES, type_label
from medione.services import directory
from medione.ui.state import open_record

NR = '<span class="tm-nr">Not recorded</span>'


def esc(v) -> str:
    return html.escape(str(v))


def fmt_date(value: Optional[str], empty: str = "Not recorded") -> str:
    if not value:
        return empty
    try:
        return date.fromisoformat(value[:10]).strftime("%d %b %Y")
    except ValueError:
        return value


def badge(text: str, tone: str = "gray") -> str:
    return f'<span class="tm-badge tm-{tone}">{esc(text)}</span>'


def source_badge(source: str) -> str:
    label, tone = SOURCES.get(source, (source, "gray"))
    return badge(label, tone)


def md(html_text: str) -> None:
    st.markdown(html_text, unsafe_allow_html=True)


def kv(rows: Iterable[tuple[str, Optional[str]]]) -> None:
    items = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v) if v not in (None, '') else NR}</dd>" for k, v in rows)
    md(f'<dl class="tm-kv">{items}</dl>')


_SVG = {
    "calendar": '<rect x="3" y="4.5" width="18" height="16" rx="2.5"/><path d="M3 9.5h18M8 2.5v4M16 2.5v4"/>',
    "clipboard": '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1M9 11l2 2 4-4M9 17h6"/>',
    "pulse": '<path d="M3 12h4l2-5 4 10 2-5h6"/>',
    "pill": '<rect x="2.5" y="8.5" width="19" height="7" rx="3.5" transform="rotate(-45 12 12)"/><path d="m8.5 8.5 7 7"/>',
    "heart": '<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10Z"/>',
    "shield": '<path d="M12 3 4.5 6v6c0 4.5 3.2 7.8 7.5 9 4.3-1.2 7.5-4.5 7.5-9V6L12 3Z"/><path d="M12 9v6M9 12h6"/>',
    "file": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
    "timeline": '<path d="M12 3v18M12 7h6M6 12h6M12 17h5"/><circle cx="12" cy="7" r="1"/><circle cx="12" cy="12" r="1"/>',
    "flask": '<path d="M9 3h6M10 3v6L4.5 18.5A1.7 1.7 0 0 0 6 21h12a1.7 1.7 0 0 0 1.5-2.5L14 9V3"/><path d="M7 15h10"/>',
    "bell": '<path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15L6 16Z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
    "stethoscope": '<path d="M6 3v6a4 4 0 0 0 8 0V3"/><path d="M10 13v3a4 4 0 0 0 8 0v-2"/><circle cx="18" cy="12" r="2"/>',
    "share": '<circle cx="18" cy="5" r="2.5"/><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="19" r="2.5"/><path d="m8.2 10.8 7.6-4.6M8.2 13.2l7.6 4.6"/>',
    "sparkle": '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><circle cx="17" cy="9" r="2.5"/><path d="M16 14a5 5 0 0 1 5.5 5"/>',
    "gear": '<circle cx="12" cy="12" r="3"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6v.6M12 17h.01"/>',
    "plus": '<circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/>',
    "alert": '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/>',
}


def svg(name: str, size: int = 22) -> str:
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{_SVG.get(name, _SVG["file"])}</svg>')


_TITLE_ICONS = {"Medical timeline": "timeline", "Records": "folder", "Add record": "plus", "Medicines": "pill",
                "Lab results": "flask", "Reminders": "bell", "Doctors & facilities": "stethoscope",
                "Share with a doctor": "share", "AI assistant": "sparkle", "Family profiles": "users",
                "Settings": "gear", "Help & privacy": "help"}


def page_header(title: str, subtitle: str = "", icon: str = "") -> None:
    icon = icon or _TITLE_ICONS.get(title, "file")
    md(f'<div class="tm-page"><div class="ic">{svg(icon, 24)}</div><div><h2>{esc(title)}</h2>'
       + (f'<div class="sub">{esc(subtitle)}</div>' if subtitle else "") + "</div></div>")


def tile(label: str, value, hint: str = "", icon: str = "file", tone: str = "teal") -> str:
    return (f'<div class="tm-tile"><div class="ic ic-{tone}">{svg(icon)}</div><div><div class="lbl">{esc(label)}</div>'
            f'<div class="val">{esc(value)}</div><div class="hint">{esc(hint)}</div></div></div>')


def section(title: str, icon: str = "", count: int | None = None) -> None:
    md(f'<div class="tm-sec">{svg(icon, 19) if icon else ""}<span>{esc(title)}</span>'
       + (f'<span class="count">{count}</span>' if count is not None else "") + "</div>")


def date_block(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return (f'<div class="tm-date"><div class="m">{d.strftime("%b").upper()}</div><div class="d">{d.day}</div>'
            f'<div class="w">{d.strftime("%a")}</div></div>')


def empty_state(title: str, text: str, action_label: str = "", on_click: Optional[Callable] = None,
                args: tuple = (), key: str = "") -> None:
    with st.container(border=True):
        st.markdown(f"**{title}**")
        st.caption(text)
        if action_label and on_click:
            st.button(action_label, on_click=on_click, args=args, key=key or f"empty_{title}", type="primary")


def record_row(r: dict, key_prefix: str, show_type: bool = True) -> None:
    """One record in a list: icon, title, date, who, provenance and an Open button."""
    rtype = RECORD_TYPES.get(r["type"])
    with st.container(border=True):
        c1, c2 = st.columns([6, 1], vertical_alignment="center")
        with c1:
            who = " · ".join(esc(x) for x in (r.get("doctor_name"), r.get("facility_name")) if x)
            bits = [esc(fmt_date(r.get("record_date"), "No date"))]
            if show_type:
                bits.append(esc(type_label(r["type"])))
            if who:
                bits.append(who)
            if r.get("doc_count"):
                bits.append(f"📎 {r['doc_count']}")
            extra = " " + source_badge(r["source"]) if r.get("source") and r["source"] != "patient" else ""
            md(f'<div class="tm-row-title">{esc(r["title"])}{extra}</div>'
               f'<div class="tm-row-meta">{" · ".join(bits)}</div>')
        with c2:
            st.button("Open", key=f"{key_prefix}_{r['id']}", on_click=open_record, args=(r["id"],),
                      width="stretch", help=rtype.label if rtype else None)


def ai_block(title: str, body_md: str) -> None:
    md(f'<div class="tm-ai"><div class="tm-ai-label">✦ AI-GENERATED · {esc(title.upper())} · '
       f'NOT A MEDICAL OPINION — CHECK AGAINST YOUR ORIGINAL DOCUMENTS</div></div>')
    st.markdown(body_md)


def doctor_options(uid: int) -> dict[str, Optional[int]]:
    opts: dict[str, Optional[int]] = {"— Not recorded —": None}
    for d in directory.list_doctors(uid):
        label = d["name"] + (f" ({d['specialty']})" if d["specialty"] else "")
        opts[label] = d["id"]
    return opts


def facility_options(uid: int) -> dict[str, Optional[int]]:
    opts: dict[str, Optional[int]] = {"— Not recorded —": None}
    for f in directory.list_facilities(uid):
        opts[f["name"]] = f["id"]
    return opts


def label_for(options: dict, value) -> str:
    return next((k for k, v in options.items() if v == value and v is not None), next(iter(options)))


def disclaimer() -> None:
    st.caption("Thought Medione stores and organises your records. It does not give medical advice, "
               "diagnose, or change treatment. Always follow your doctor's instructions. In an emergency call 112.")
