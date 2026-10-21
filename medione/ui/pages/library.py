"""Records library: keyword search plus filters (and AI-assisted search when enabled)."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from medione.ai import tasks as ai_tasks
from medione.ai.client import AIError, AIUnavailable, is_configured
from medione.models import CATEGORIES, SOURCES, types_in, type_label
from medione.services import directory, nlsearch, search
from medione.ui.state import Ctx, go
from medione.ui.widgets import empty_state, page_header, record_row


def _reset_filters() -> None:
    for k in list(st.session_state):
        if k.startswith("flt_lib_"):
            del st.session_state[k]


def render(ctx: Ctx) -> None:
    page_header("Records", "Search everything: titles, doctors, hospitals, conditions, medicines, tests and document text.")
    known = search.distinct_values(ctx.uid, ctx.pid)
    doctors = {d["name"]: d["id"] for d in directory.list_doctors(ctx.uid)}
    facilities = {f["name"]: f["id"] for f in directory.list_facilities(ctx.uid)}

    query = st.text_input("Search", key="flt_lib_q", placeholder="e.g. HbA1c, Dr. Iyer, ultrasound 2026, metformin",
                          label_visibility="collapsed")
    with st.expander("Filters", expanded=False):
        c1, c2, c3 = st.columns(3)
        cats = c1.multiselect("Category", list(CATEGORIES), format_func=CATEGORIES.get, key="flt_lib_cats")
        type_opts = [t for c in (cats or CATEGORIES) for t in types_in(c)]
        types = c1.multiselect("Record type", type_opts, format_func=type_label, key="flt_lib_types")
        d_from = c2.date_input("From", value=None, key="flt_lib_from", format="DD/MM/YYYY",
                               min_value=date(1900, 1, 1))
        d_to = c2.date_input("To", value=None, key="flt_lib_to", format="DD/MM/YYYY", min_value=date(1900, 1, 1))
        doctor = c3.selectbox("Doctor", list(doctors), index=None, key="flt_lib_doc", placeholder="Any")
        facility = c3.selectbox("Hospital / clinic / lab", list(facilities), index=None, key="flt_lib_fac",
                                placeholder="Any")
        c4, c5, c6, c7 = st.columns(4)
        condition = c4.selectbox("Condition", known["conditions"], index=None, key="flt_lib_cond", placeholder="Any")
        medication = c5.selectbox("Medicine", known["medications"], index=None, key="flt_lib_med", placeholder="Any")
        test = c6.selectbox("Test", known["tests"], index=None, key="flt_lib_test", placeholder="Any")
        sources = c7.multiselect("Source", list(SOURCES), format_func=lambda s: SOURCES[s][0], key="flt_lib_src")
        st.button("Clear filters", on_click=_reset_filters, key="lib_clear")

    ai_ready = is_configured() and ctx.user.ai_consent_at
    with st.expander("Ask in your own words", icon=":material/auto_awesome:",
                     expanded=bool(st.session_state.get("flt_nl_q"))):
        st.caption("e.g. *latest blood test*, *prescriptions from last year*, *MRI from March*, *records from "
                   "Dr. Iyer*, *LDL results*. Results always come from your stored records.")
        st.text_input("Question", key="flt_nl_q", placeholder="Find my latest blood test report",
                      label_visibility="collapsed")
        nl_q = st.session_state.get("flt_nl_q", "").strip()
        if nl_q:
            f, nl_results = nlsearch.run(ctx.uid, ctx.pid, nl_q)
            st.info("Looked for: " + ("; ".join(f["explain"]) if f["explain"] else "all records") +
                    (" — some words didn't match, so they were left out." if f.get("relaxed") else ""))
            if not nl_results:
                st.warning("No matching record was found. Nothing is stored that fits this question.")
            for r in nl_results[:30]:
                record_row(r, "nl_lib")
        if ai_ready:
            st.divider()
            st.caption("Not quite right? Let the AI interpret the question instead.")
            question = nl_q
            if st.button("Interpret with AI", key="ai_lib_go", disabled=not question):
                try:
                    with st.spinner("Working out the filters…"):
                        st.session_state["ai_lib_filters"] = ai_tasks.interpret_search(question, {
                            **known, "doctors": list(doctors), "facilities": list(facilities)})
                except (AIError, AIUnavailable) as exc:
                    st.error(str(exc))
            f = st.session_state.get("ai_lib_filters")
            if f:
                st.info(f"AI filters: {f['explanation']}")
                try:
                    results = search.search_records(
                        ctx.uid, ctx.pid, f.get("keywords") or "", f.get("record_types") or None,
                        _d(f.get("date_from")), _d(f.get("date_to")), doctors.get(f.get("doctor") or ""),
                        facilities.get(f.get("facility") or ""), f.get("condition") or "",
                        f.get("medication") or "", f.get("test") or "")
                except ValueError:
                    results = []
                if not results:
                    st.warning("No stored records match. The AI never makes up records — try different words.")
                for r in results:
                    record_row(r, "ai_lib")
            st.divider()

    results = search.search_records(
        ctx.uid, ctx.pid, query, types or ([t for c in cats for t in types_in(c)] if cats else None),
        d_from, d_to, doctors.get(doctor) if doctor else None, facilities.get(facility) if facility else None,
        condition or "", medication or "", test or "", sources)
    total = search.search_records(ctx.uid, ctx.pid)
    if not total:
        empty_state("No records yet", "Upload a document or type in a record to get started.",
                    "Add record", go, ("Add record",), key="lib_add")
        return
    c1, c2 = st.columns([3, 1], vertical_alignment="center")
    c1.caption(f"{len(results)} of {len(total)} records")
    if results:
        export = pd.DataFrame([{"Date": r["record_date"], "Type": type_label(r["type"]), "Title": r["title"],
                                "Doctor": r["doctor_name"], "Facility": r["facility_name"],
                                "Condition": r["condition"], "Source": SOURCES.get(r["source"], (r["source"],))[0]}
                               for r in results])
        c2.download_button("Export list (CSV)", export.to_csv(index=False), "records.csv", "text/csv",
                           key="lib_csv", width="stretch")
    if not results:
        st.info("No records match your search. Check the spelling or clear some filters.")
    for r in results[:200]:
        record_row(r, "lib")
    if len(results) > 200:
        st.caption("Showing the first 200 results. Narrow the search to see others.")


def _d(value):
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None
