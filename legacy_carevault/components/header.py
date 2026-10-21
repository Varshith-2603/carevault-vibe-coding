import html
import streamlit as st

from components.filters import filter_key
from components.state import navigate, open_dialog
from utils.data_loader import get_alerts

RECORDS_PAGE = "All Records"


def _launch_search():
    """Header search is global: it opens All Records with the query in its search box."""
    q = st.session_state.get("header_search_input", "").strip()
    st.session_state.global_search_query = q
    if q:
        navigate(RECORDS_PAGE, {filter_key("records", "q"): q})
        st.session_state.pop("_cv_limit_records", None)
        st.session_state.header_search_input = ""


def _dismiss_all(alert_ids):
    st.session_state.setdefault("dismissed_alerts", set()).update(alert_ids)


def _open_alert(alert):
    st.session_state.setdefault("dismissed_alerts", set()).add(alert["id"])
    open_dialog(alert["kind"], alert["record_id"], "view")


def render_alerts_popover():
    alerts = get_alerts()
    unread = [a for a in alerts if a["unread"]]
    label = f"Alerts · {len(unread)}" if unread else "Alerts"
    with st.popover(label, icon=":material/notifications:", width="content",
                    help="Reminders worked out from your records"):
        st.markdown("**Alerts from your records**")
        st.caption("Worked out from your appointments, reports and prescriptions. Change them in Settings.")
        if not alerts:
            st.caption("Nothing needs your attention right now.")
        for a in alerts:
            dot = "●" if a["unread"] else "○"
            new_tag = ' <span class="cv-sr">(new)</span>' if a["unread"] else ""
            with st.container(key=f"cvalert_{a['id'].replace(':', '_').replace(' ', '_')}"):
                st.markdown(
                    f'<div class="cv-alert {"is-unread" if a["unread"] else ""}"><span class="cv-alert-dot" aria-hidden="true">{dot}</span>'
                    f'<div><div class="cv-alert-title">{html.escape(a["title"])}{new_tag}</div>'
                    f'<div class="cv-alert-desc">{html.escape(a["desc"])}</div></div></div>',
                    unsafe_allow_html=True,
                )
                st.button("Open", key=f"alert_open_{a['id']}", on_click=_open_alert, args=(a,), type="tertiary",
                          icon=":material/open_in_new:")
        c1, c2 = st.columns(2)
        with c1:
            st.button("Mark all as read", key="mark_read_btn", on_click=_dismiss_all,
                      args=([a["id"] for a in alerts],), disabled=not unread, width="stretch")
        with c2:
            st.button("Alert settings", key="alert_settings_btn", on_click=navigate, args=("Settings", {"_cv_settings_tab": "alerts"}),
                      width="stretch")


def render_top_header(title: str, subtitle: str, add_kind: str = "visit") -> str:
    """
    Page header: title, global search, alerts and the primary Add Record action.
    Returns the last global search query (kept for backward compatibility).
    """
    with st.container(key="cv_header"):
        left, right = st.columns([1.05, 1], vertical_alignment="center", gap="medium")
        with left:
            st.markdown(
                f'<h1 class="cv-page-title">{html.escape(title)}</h1>'
                f'<p class="cv-page-subtitle">{html.escape(subtitle)}</p>',
                unsafe_allow_html=True,
            )
        with right:
            with st.container(horizontal=True, vertical_alignment="center", gap="small", key="cv_header_actions"):
                st.text_input(
                    "Search all records",
                    placeholder="Search all records…",
                    key="header_search_input",
                    on_change=_launch_search,
                    label_visibility="collapsed",
                    icon=":material/search:",
                    help="Search every record type. Press Enter to see results.",
                    width="stretch",
                )
                render_alerts_popover()
                st.button("Add record", type="primary", key="header_add_btn", icon=":material/add:",
                          on_click=open_dialog, args=(add_kind, None, "add"),
                          help="Add a visit, report, prescription, appointment or vitals reading")
    return st.session_state.get("global_search_query", "")
