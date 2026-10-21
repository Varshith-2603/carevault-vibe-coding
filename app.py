"""Thought Medione — entry point. Run with: streamlit run app.py"""
import streamlit as st

st.set_page_config(page_title="Thought Medione", page_icon=":material/health_and_safety:", layout="wide",
                   initial_sidebar_state="auto")

from medione import APP_NAME  # noqa: E402
from medione.db import init_db  # noqa: E402
from medione.ui import theme  # noqa: E402
from medione.ui import chatbot  # noqa: E402
from medione.ui.pages import (add_record, appointments_page, auth_page, care_team, dashboard,  # noqa: E402
                              emergency_page, family, help_page, labs, library, medicines, record_view,
                              reminders_page, settings_page, shared_view, sharing_page, symptoms, timeline,
                              vitals_page)
from medione.ui.state import check_timeout, current_context, go, show_flash, sign_out, switch_profile  # noqa: E402

NAV_GROUPS = {
    "Overview": {
        "Dashboard": (dashboard.render, ":material/space_dashboard:"),
        "Timeline": (timeline.render, ":material/timeline:"),
    },
    "My health": {
        "Appointments": (appointments_page.render, ":material/event:"),
        "Symptoms": (symptoms.render, ":material/sick:"),
        "Vitals": (vitals_page.render, ":material/monitor_heart:"),
        "Medicines": (medicines.render, ":material/medication:"),
        "Lab results": (labs.render, ":material/biotech:"),
        "Reminders": (reminders_page.render, ":material/alarm:"),
    },
    "Records": {
        "Add record": (add_record.render, ":material/upload_file:"),
        "Records": (library.render, ":material/folder_open:"),
        "Doctors & facilities": (care_team.render, ":material/stethoscope:"),
    },
    "Safety & sharing": {
        "Emergency card": (emergency_page.render, ":material/emergency:"),
        "Share": (sharing_page.render, ":material/share:"),
    },
    "Account": {
        "Family": (family.render, ":material/family_restroom:"),
        "Settings": (settings_page.render, ":material/settings:"),
        "Help": (help_page.render, ":material/help:"),
    },
}
PAGES = {name: spec for group in NAV_GROUPS.values() for name, spec in group.items()}
HIDDEN_PAGES = {"Record": record_view.render}
HOME = "Dashboard"


def _sidebar(ctx) -> None:
    with st.sidebar:
        st.markdown(f'<div class="tm-brand"><span class="dot">✚</span>{APP_NAME}</div>'
                    '<div class="tm-tagline">Your family\'s health, in one place</div>', unsafe_allow_html=True)
        options = {p["id"]: p["full_name"] + (" (you)" if p["relationship"] == "self" else f" · {p['relationship']}")
                   for p in ctx.profiles}
        chosen = st.selectbox("Viewing records of", list(options), index=list(options).index(ctx.pid),
                              format_func=options.get, key="sidebar_profile")
        if chosen != ctx.pid:
            switch_profile(chosen)
            st.rerun()
        current = st.session_state.get("page", HOME)
        for group, pages in NAV_GROUPS.items():
            st.markdown(f'<div class="tm-nav-group">{group}</div>', unsafe_allow_html=True)
            for name, (_, icon) in pages.items():
                st.button(name, icon=icon, key=f"nav_{name}", on_click=go, args=(name,), width="stretch",
                          type="primary" if name == current else "tertiary")
        st.write("")
        st.caption(f"Signed in as {ctx.user.email}")
        if st.button("Sign out", icon=":material/logout:", key="nav_signout", width="stretch"):
            sign_out("You have signed out.")
            st.rerun()


def _mobile_nav() -> None:
    """Compact page picker shown only on narrow screens (CSS), where the sidebar is collapsed."""
    names = list(PAGES)
    current = st.session_state.get("page", HOME)

    def _pick() -> None:
        go(st.session_state["mobile_nav_pick"])

    st.session_state["mobile_nav_pick"] = current if current in names else None
    with st.container(key="mobile_nav"):
        st.selectbox("Go to", names, key="mobile_nav_pick", on_change=_pick, label_visibility="collapsed",
                     placeholder="Go to…")


def main() -> None:
    theme.inject()
    init_db()
    token = st.query_params.get("share")
    if token:
        shared_view.render(token)
        return
    em_token = st.query_params.get("emergency")
    if em_token:
        emergency_page.render_public(em_token)
        return
    check_timeout()
    ctx = current_context()
    if ctx is None:
        auth_page.render()
        return
    _sidebar(ctx)
    _mobile_nav()
    show_flash()
    page = st.session_state.get("page", HOME)
    renderer = HIDDEN_PAGES.get(page) or PAGES.get(page, PAGES[HOME])[0]
    renderer(ctx)
    chatbot.render(ctx)


main()
