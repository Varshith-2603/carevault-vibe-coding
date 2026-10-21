import streamlit as st

from components.charts import render_vitals_chart
from components.filters import apply_sort, filter_panel
from components.header import render_top_header
from components.page import list_toolbar, render_results
from components.ui import section_header, stat_card, stat_grid
from utils.data_loader import get_vitals, past_records_only
from utils.filters import filter_by_date
from utils.helpers import format_date, is_missing, render_disclaimer
from utils.records import match_query, row_search_text


def _latest(df, col, fmt, unit):
    s = df[df[col].map(lambda v: not is_missing(v))]
    if s.empty:
        return "Not recorded", "No readings yet"
    row = s.iloc[0]
    return f"{fmt.format(row[col])} {unit}", f"on {format_date(row['date'])}"


def render_vitals_page():
    render_top_header(
        title="Health Vitals",
        subtitle="Heart rate, blood pressure, weight and blood oxygen you have recorded.",
        add_kind="vital",
    )
    df = get_vitals()
    past = past_records_only(df)

    hr = _latest(past, "heart_rate", "{:.0f}", "bpm")
    wt = _latest(past, "weight_kg", "{:.1f}", "kg")
    sp = _latest(past, "spo2", "{:.0f}", "%")
    bp_rows = past[past["systolic_bp"].map(lambda v: not is_missing(v)) & past["diastolic_bp"].map(lambda v: not is_missing(v))]
    bp = (f"{bp_rows.iloc[0]['systolic_bp']:.0f}/{bp_rows.iloc[0]['diastolic_bp']:.0f} mmHg",
          f"on {format_date(bp_rows.iloc[0]['date'])}") if not bp_rows.empty else ("Not recorded", "No readings yet")

    with stat_grid("vitals"):
        stat_card("vt_hr", "Latest heart rate", hr[0], hr[1], "heart", "rose")
        stat_card("vt_bp", "Latest blood pressure", bp[0], bp[1], "heart", "blue")
        stat_card("vt_wt", "Latest weight", wt[0], wt[1], "user", "teal")
        stat_card("vt_sp", "Latest blood oxygen", sp[0], sp[1], "heart", "slate")

    with st.container(border=True, key="cv_vitals_chart"):
        section_header("Trends", "Pick a measurement and a time period. Hover over a point to see its exact value.")
        render_vitals_chart(df, key="page_vitals", height=340)

    section_header("All readings", "Every vitals reading you have recorded, including any dated in the future.")
    f = filter_panel("vitals", [], search_placeholder="Search notes or device…")
    filtered = filter_by_date(df, "date", f["start"], f["end"])
    if f["q"] and not filtered.empty:
        filtered = filtered[match_query(row_search_text("vital", filtered), f["q"])]
    filtered = apply_sort(filtered, "date", f["sort"], "vital_id")
    view = list_toolbar("vital", "vitals", filtered, len(df), "readings", f["active"], "Add reading", "CareVault_vitals")
    render_results("vital", "vitals", filtered, view, "No readings found",
                   "Nothing matches your filters. Try 'Reset filters' or add a reading.")
    render_disclaimer()
