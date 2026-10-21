import streamlit as st

from components.charts import render_department_visits_chart
from components.filters import Select, apply_sort, filter_panel, options_from
from components.header import render_top_header
from components.page import list_toolbar, render_results
from components.ui import stat_card, stat_grid
from utils.data_loader import get_hospital_visits, past_records_only
from utils.filters import filter_hospital_visits
from utils.helpers import esc, format_date, relative_day, render_disclaimer


def render_hospital_visits_page():
    """Hospital visits: summary, combined filters, list/table view, details and record management."""
    render_top_header(
        title="Hospital Visits",
        subtitle="Every hospital and clinic visit, with notes and follow-up instructions.",
        add_kind="visit",
    )
    df = get_hospital_visits()
    past = past_records_only(df)
    latest = past.iloc[0] if not past.empty else None

    with stat_grid("visits"):
        stat_card("v_total", "Total visits", len(df), "All recorded visits", "hospital", "teal")
        stat_card("v_last", "Most recent visit", format_date(latest["date"]) if latest is not None else "None",
                  f"{esc(latest['hospital_name'])} · {esc(relative_day(latest['date']))}" if latest is not None else "No visits recorded",
                  "calendar", "blue")
        stat_card("v_fac", "Facilities", df["hospital_name"].replace("", None).nunique(),
                  "Hospitals and clinics in your records", "folder", "slate")
        stat_card("v_dept", "Departments", df["department"].replace("", None).nunique(),
                  "Specialties you have visited", "user", "amber")

    f = filter_panel(
        "visits",
        [Select("hospital", "Hospital", options_from(df, "hospital_name"), "All hospitals"),
         Select("department", "Department", options_from(df, "department"), "All departments"),
         Select("doctor", "Doctor", options_from(df, "attending_physician"), "All doctors"),
         Select("status", "Visit status", options_from(df, "status"), "All statuses")],
        search_placeholder="Search reason, doctor, hospital, diagnosis…",
    )
    filtered = filter_hospital_visits(df, hospital=f["hospital"], department=f["department"], doctor=f["doctor"],
                                      status=f["status"], search_query=f["q"], start=f["start"], end=f["end"])
    filtered = apply_sort(filtered, "date", f["sort"], "visit_id")

    view = list_toolbar("visit", "visits", filtered, len(df), "visits", f["active"], "Add visit", "CareVault_hospital_visits")
    render_results("visit", "visits", filtered, view, "No hospital visits found",
                   "No visits match your filters. Try 'Reset filters' or a different search.")

    with st.expander("Visits by department", icon=":material/bar_chart:"):
        render_department_visits_chart(filtered)
        st.caption("Counts follow the filters above.")

    render_disclaimer()
