import streamlit as st

# Configure the Streamlit application layout and metadata
st.set_page_config(
    page_title="CareVault — Personal Health Records",
    page_icon=":material/health_and_safety:",
    layout="wide",
    initial_sidebar_state="auto",
)

from utils.data_loader import init_session_data
from utils.helpers import load_custom_css
from components.dialogs import render_active_dialog
from components.sidebar import ALL_PAGES, render_mobile_nav, render_sidebar
from components.state import show_flash
from pages.dashboard import render_dashboard_page
from pages.appointments import render_appointments_page
from pages.hospital_visits import render_hospital_visits_page
from pages.diagnostics import render_diagnostics_page
from pages.prescriptions import render_prescriptions_page
from pages.vitals import render_vitals_page
from pages.records import render_records_page
from pages.settings import render_settings_page
from pages.help_support import render_help_support_page

PAGES = {
    "Dashboard": render_dashboard_page,
    "Appointments": render_appointments_page,
    "Hospital Visits": render_hospital_visits_page,
    "Scans & Diagnostics": render_diagnostics_page,
    "Prescriptions & Medicines": render_prescriptions_page,
    "Health Vitals": render_vitals_page,
    "All Records": render_records_page,
    "Settings": render_settings_page,
    "Help & Support": render_help_support_page,
}
assert set(PAGES) == set(ALL_PAGES)


def main():
    # Inject CareVault Design System CSS
    load_custom_css()

    # Initialize demo health data in session state
    init_session_data()

    # Persistent sidebar (desktop) and compact page picker (phones)
    render_sidebar()
    render_mobile_nav()

    # Route to active page based on session state
    current_page = st.session_state.get("current_page", "Dashboard")
    if current_page not in PAGES:
        current_page = st.session_state.current_page = "Dashboard"
    PAGES[current_page]()

    # Exactly one dialog per run, drawn after the page so it sits on top
    render_active_dialog()
    show_flash()


if __name__ == "__main__":
    main()
