import html
import streamlit as st

from components.state import navigate
from utils.data_loader import get_patient_info
from utils.helpers import display, initials

MAIN_NAV = [
    ("Dashboard", ":material/home:"),
    ("Appointments", ":material/event:"),
    ("Hospital Visits", ":material/local_hospital:"),
    ("Scans & Diagnostics", ":material/biotech:"),
    ("Prescriptions & Medicines", ":material/medication:"),
    ("Health Vitals", ":material/monitor_heart:"),
    ("All Records", ":material/folder_open:"),
]
SUPPORT_NAV = [
    ("Settings", ":material/settings:"),
    ("Help & Support", ":material/help:"),
]
ALL_PAGES = [p for p, _ in MAIN_NAV + SUPPORT_NAV]


def _nav_group(items, current):
    for page_key, icon in items:
        is_active = current == page_key
        st.button(
            page_key,
            key=f"nav_btn_{page_key}",
            icon=icon,
            type="primary" if is_active else "tertiary",
            width="stretch",
            on_click=navigate,
            args=(page_key,),
        )


def render_sidebar():
    """Persistent sidebar navigation with the patient's profile card."""
    patient = get_patient_info()
    current = st.session_state.get("current_page", "Dashboard")

    with st.sidebar:
        st.markdown(
            """
            <div class="brand-container">
                <div class="brand-icon-box" aria-hidden="true">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
                </div>
                <div>
                    <div class="brand-text-title">CareVault</div>
                    <div class="brand-text-sub">Personal Health Records</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.container(key="cv_nav"):
            st.markdown('<div class="cv-nav-label">Your records</div>', unsafe_allow_html=True)
            _nav_group(MAIN_NAV, current)
            st.markdown('<div class="cv-nav-label">Account & help</div>', unsafe_allow_html=True)
            _nav_group(SUPPORT_NAV, current)

        name = display(patient.get("name"), "Patient")
        st.markdown(
            f"""
            <div class="patient-badge-card">
                <div class="patient-avatar" aria-hidden="true">{html.escape(initials(name))}</div>
                <div style="flex:1; min-width:0;">
                    <div class="patient-info-name">{html.escape(name)}</div>
                    <div class="patient-info-id">{html.escape(display(patient.get('patient_id'), ''))}</div>
                    <div class="patient-info-meta">Blood type {html.escape(display(patient.get('blood_type'), 'not provided'))}
                    · Age {html.escape(display(patient.get('age'), '—'))}</div>
                </div>
            </div>
            <div class="cv-sidebar-note">Demo patient — all data is fictional and is reset when you reload the page.</div>
            """,
            unsafe_allow_html=True,
        )


def _mobile_nav_changed():
    navigate(st.session_state["cv_mobile_nav"])


def render_mobile_nav():
    """Compact page picker shown only on narrow screens (the sidebar is collapsed there)."""
    current = st.session_state.get("current_page", "Dashboard")
    st.session_state["cv_mobile_nav"] = current
    with st.container(key="cv_mobile_nav_wrap"):
        st.selectbox("Go to page", ALL_PAGES, key="cv_mobile_nav", on_change=_mobile_nav_changed,
                     help="Choose a section of your health record.")
