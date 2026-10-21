"""All Records: one place to search, browse and export every record type."""
import html

import streamlit as st

from components.filters import SORT_OPTIONS, date_range_value, filter_key, reset_filters
from components.header import render_top_header
from components.state import open_dialog
from components.ui import KIND_ICON, KIND_TONE, html_block, icon, paginate, section_header, show_more, slug
from utils.data_loader import get_patient_info, past_records_only
from utils.exports import printable_summary, to_csv
from utils.filters import filter_index
from utils.helpers import esc, format_date, render_badge, render_disclaimer, render_empty_state
from utils.records import RECORD_TYPES, build_record_index, get_df, sort_df

PAGE = "records"
KIND_ORDER = ["visit", "diagnostic", "prescription", "history", "appointment", "vital"]


def _result_row(item: dict):
    kind = item["kind"]
    with st.container(border=True, key=f"cvrow_{PAGE}_{slug(item['record_id'])}"):
        c1, c2 = st.columns([5, 1.35], vertical_alignment="center", gap="small")
        with c1:
            badge = render_badge(item["status"]) if kind != "vital" else ""
            html_block(
                f"""
                <div class="cv-row">
                    <div class="cv-row-icon tone-{KIND_TONE[kind]}">{icon(KIND_ICON[kind])}</div>
                    <div class="cv-row-main">
                        <div class="cv-row-top"><span class="cv-chip">{esc(RECORD_TYPES[kind].label)}</span>
                            <span class="cv-row-title">{esc(item['title'])}</span>{badge}</div>
                        <div class="cv-row-sub"><strong>{esc(format_date(item['date']))}</strong> · {esc(item['details'], '')}</div>
                    </div>
                </div>
                """
            )
        with c2:
            st.button("Open record", key=f"{PAGE}_open_{item['record_id']}", on_click=open_dialog,
                      args=(kind, item["record_id"]), icon=":material/open_in_new:", width="stretch")


def _clear_search():
    st.session_state[filter_key(PAGE, "q")] = ""
    st.session_state.global_search_query = ""


def render_records_page():
    render_top_header(
        title="All Records",
        subtitle="Search, browse and export every record in one place.",
    )
    index = build_record_index()

    with st.container(border=True, key=f"cvfilters_{PAGE}"):
        c1, c2 = st.columns([4, 1.3], vertical_alignment="bottom", gap="small")
        with c1:
            q = st.text_input("Search all records", key=filter_key(PAGE, "q"), icon=":material/search:",
                              placeholder="Try 'Mitchell', 'MRI', 'Metoprolol', 'Apollo' or 'Oct 2026'",
                              persist_state="session",
                              help="Searches hospitals, doctors, departments, reasons, tests, medicines, appointments and dates.")
        with c2:
            st.button("Clear search", key=f"{PAGE}_clear_q", on_click=_clear_search, icon=":material/close:",
                      width="stretch", disabled=not q)
        kinds = st.pills("Record types", KIND_ORDER, selection_mode="multi", key=filter_key(PAGE, "kinds"),
                         format_func=lambda k: RECORD_TYPES[k].plural, persist_state="session",
                         help="Pick one or more types. Leave all unselected to include every type.")
        c3, c4, c5 = st.columns([2, 1.6, 1.2], vertical_alignment="bottom", gap="small")
        with c3:
            raw = st.date_input("Date range", value=(), key=filter_key(PAGE, "dates"), format="DD/MM/YYYY",
                                persist_state="session")
            start, end = date_range_value(raw)
        with c4:
            sort = st.selectbox("Sort by date", SORT_OPTIONS, key=filter_key(PAGE, "sort"), persist_state="session")
        with c5:
            st.button("Reset filters", key=f"{PAGE}_reset", icon=":material/restart_alt:", width="stretch",
                      on_click=reset_filters, args=(PAGE, ["kinds"]))

    results = filter_index(index, q, kinds or None, start, end)
    results = results.sort_values(["date", "record_id"], ascending=(sort == SORT_OPTIONS[1]), kind="stable")

    counts = results["kind"].value_counts().to_dict()
    breakdown = " · ".join(f"{RECORD_TYPES[k].plural}: {counts[k]}" for k in KIND_ORDER if counts.get(k))
    heading = f'Results for “{html.escape(q)}”' if q else "All your records"
    html_block(f'<div class="cv-results-bar" role="status" aria-live="polite"><span>{heading} — <strong>{len(results)}</strong> '
               f'of {len(index)} records</span><span class="cv-results-extra">{html.escape(breakdown)}</span></div>')

    if results.empty:
        render_empty_state(
            "No matching records",
            "Check the spelling, try fewer words, or search by a doctor, hospital, test or medicine name. "
            "You can also clear the record-type and date filters.", "🔍")
    else:
        for item in paginate(results, PAGE, 15).to_dict(orient="records"):
            _result_row(item)
        show_more(len(results), PAGE, 15)

    st.divider()
    section_header("Export your records", "Download what you see above, or a printable health summary.")
    e1, e2 = st.columns(2, gap="large")
    with e1:
        with st.container(border=True, key="cv_export_csv"):
            st.markdown("**Search results (CSV)**")
            st.caption(f"Includes the {len(results)} records listed above: type, date, title, details, status and "
                       "record ID. Opens in Excel, Numbers or Google Sheets.")
            st.download_button("Download CSV", data=to_csv(results, {"type": "Record type", "date": "Date", "title": "Title",
                                                                       "details": "Details", "status": "Status",
                                                                       "record_id": "Record ID"}),
                               file_name="CareVault_records.csv", mime="text/csv", key=f"{PAGE}_csv",
                               icon=":material/download:", on_click="ignore", disabled=results.empty)
    with e2:
        with st.container(border=True, key="cv_export_summary"):
            st.markdown("**Printable health summary**")
            st.caption("Always includes your name, patient ID and emergency details. Choose what else to add:")
            include = st.pills("Sections", ["prescription", "appointment", "visit", "diagnostic", "history", "vital"],
                               selection_mode="multi", default=["prescription", "appointment"],
                               format_func=lambda k: {"prescription": "Active prescriptions",
                                                      "appointment": "Upcoming appointments"}.get(k, RECORD_TYPES[k].plural),
                               key=f"{PAGE}_summary_sections", label_visibility="collapsed")
            frames = {}
            for k in include or []:
                df = get_df(k)
                if k == "prescription":
                    df = df[df["status"] == "Active"]
                elif k == "appointment":
                    df = sort_df(k, df[df["status"] == "Upcoming"], ascending=True)
                elif k == "vital":
                    df = past_records_only(df)
                frames[k] = df
            st.download_button("Download summary", data=printable_summary(get_patient_info(), frames, list(include or [])),
                               file_name="CareVault_health_summary.html", mime="text/html", key=f"{PAGE}_summary",
                               icon=":material/print:", on_click="ignore",
                               help="An HTML file: open it in your browser, then Print or 'Save as PDF'.")
    render_disclaimer()
