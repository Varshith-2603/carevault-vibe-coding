from datetime import date

import streamlit as st

from components.cards import (
    render_appointment_list,
    render_dashboard_summary_cards,
    render_emergency_id_card,
    render_recent_activity,
)
from components.charts import render_vitals_chart
from components.header import render_top_header
from components.state import navigate
from components.ui import demo_pill, html_block, section_header
from utils.data_loader import (
    get_dashboard_metrics,
    get_patient_info,
    get_vitals,
    recent_activity,
    upcoming_appointments,
)
from utils.helpers import display, greeting, render_disclaimer


def render_dashboard_page():
    """Dashboard overview: summary, next appointments, vitals, emergency ID and recent records."""
    patient = get_patient_info()
    first_name = display(patient.get("name"), "there").split()[0]
    render_top_header(
        title=f"{greeting()}, {first_name}",
        subtitle="Your health information, organized in one place.",
    )
    html_block(f'<div class="cv-dash-meta">{demo_pill()}<span>Today is {date.today().strftime("%A, %d %B %Y")}</span></div>')

    metrics = get_dashboard_metrics()
    render_dashboard_summary_cards(metrics)

    left_col, right_col = st.columns([7, 5], gap="large")

    with left_col:
        with st.container(border=True, key="cv_dash_apts"):
            section_header("Upcoming appointments", "Your next scheduled visits, soonest first.")
            render_appointment_list(upcoming_appointments(), "dash", limit=3)
            st.button("See all appointments", key="dash_all_apts", type="tertiary", icon=":material/arrow_forward:",
                      icon_position="right", on_click=navigate, args=("Appointments",))

        with st.container(border=True, key="cv_dash_vitals"):
            section_header("Health vitals", "Measurements you have recorded over time.")
            render_vitals_chart(get_vitals(), key="dash_vitals", height=260)
            st.button("Open Health Vitals", key="dash_open_vitals", type="tertiary", icon=":material/arrow_forward:",
                      icon_position="right", on_click=navigate, args=("Health Vitals",))

    with right_col:
        render_emergency_id_card(patient)
        with st.container(border=True, key="cv_dash_activity"):
            section_header("Recent activity", "Your latest records by date.")
            render_recent_activity(recent_activity(6), key_prefix="dash_feed")
            st.button("Browse all records", key="dash_all_records", type="tertiary", icon=":material/arrow_forward:",
                      icon_position="right", on_click=navigate, args=("All Records",))

    render_disclaimer()
