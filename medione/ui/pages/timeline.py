"""Chronological view of the profile's medical history."""
from __future__ import annotations

from datetime import date

import streamlit as st

from medione.models import CATEGORIES, RECORD_TYPES, types_in
from medione.services import search
from medione.ui.state import Ctx, go, open_record
from medione.ui.widgets import badge, empty_state, esc, fmt_date, md, page_header, source_badge


def render(ctx: Ctx) -> None:
    page_header("Medical timeline", "Everything in date order, newest first. Open any entry to see its documents.")
    c1, c2 = st.columns([3, 1])
    cats = c1.multiselect("Show", list(CATEGORIES), format_func=CATEGORIES.get, key="flt_tl_cats",
                          placeholder="All record types")
    follow = c2.toggle("Show follow-up dates", value=True, key="flt_tl_follow")
    types = [t for c in cats for t in types_in(c)] or None
    events = search.timeline(ctx.uid, ctx.pid, types=types, include_follow_ups=follow)
    if not events:
        empty_state("Nothing to show", "No records match. Add a record or change the filter.",
                    "Add record", go, ("Add record",), key="tl_add")
        return
    today = date.today().isoformat()
    current_year = None
    for i, e in enumerate(events):
        year = (e["date"] or "Undated")[:4]
        if year != current_year:
            current_year = year
            md(f'<div class="tm-year">{esc(year)}</div>')
        with st.container(border=True):
            c1, c2 = st.columns([6, 1], vertical_alignment="center")
            with c1:
                if e["is_follow_up"]:
                    tone = "blue" if (e["date"] or "") >= today else "gray"
                    label = badge("Upcoming follow-up" if tone == "blue" else "Follow-up (past)", tone)
                    kind = "Follow-up date written in the record"
                else:
                    t = RECORD_TYPES.get(e["kind"])
                    label = badge(t.label if t else e["kind"], "gray")
                    kind = ""
                when = fmt_date(e["date"], "No date")
                if e.get("end_date"):
                    when += f" → {fmt_date(e['end_date'])}"
                who = " · ".join(esc(x) for x in (e["doctor_name"], e["facility_name"]) if x)
                src = " " + source_badge(e["source"]) if e["source"] != "patient" and not e["is_follow_up"] else ""
                clip = f" · 📎 {e['doc_count']}" if e["doc_count"] else ""
                md(f'<div class="tm-row-title">{esc(e["title"])}{src}</div>'
                   f'<div class="tm-row-meta">{esc(when)} · {label}{(" · " + who) if who else ""}{clip}'
                   f'{(" · " + esc(kind)) if kind else ""}</div>')
            with c2:
                st.button("Open", key=f"tl_{i}_{e['record_id']}", on_click=open_record, args=(e["record_id"],),
                          width="stretch")
