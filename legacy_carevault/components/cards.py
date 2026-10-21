import html
from typing import Dict, Any

import pandas as pd
import streamlit as st

from components.filters import filter_key
from components.state import navigate, open_dialog
from components.ui import (
    KIND_ICON, KIND_TONE, html_block, icon, slug, stat_card, stat_grid,
)
from utils.filters import diagnostic_group
from utils.helpers import display, esc, format_date, is_missing, relative_day, render_badge
from utils.records import RECORD_TYPES


def render_dashboard_summary_cards(metrics: Dict[str, Any]):
    """Five summary cards; each opens the matching page."""
    next_apt = metrics.get("next_appointment")
    upcoming_n = metrics.get("upcoming_count", 0)
    if next_apt is not None:
        apt_sub = f"Next: <strong>{esc(format_date(next_apt.get('date')))}</strong> · {esc(next_apt.get('doctor'))}"
    else:
        apt_sub = "No upcoming appointments"

    last_v = metrics.get("last_visit")
    visit_sub = (f"Latest: <strong>{esc(format_date(last_v.get('date')))}</strong> · {esc(last_v.get('hospital_name'))}"
                 if last_v is not None else "No visits recorded")

    pending = metrics.get("pending_reports", 0)
    report_sub = (f"<strong>{pending}</strong> not final yet · {metrics.get('final_reports', 0)} final"
                  if pending else f"All {metrics.get('final_reports', 0)} final")

    with stat_grid("dashboard"):
        stat_card("apts", "Upcoming appointments", upcoming_n, apt_sub, "calendar", "blue",
                  "View appointments", navigate, ("Appointments", {"appointments_tab": "Upcoming"}))
        stat_card("visits", "Hospital visits", metrics.get("total_visits", 0), visit_sub, "hospital", "teal",
                  "View visits", navigate, ("Hospital Visits",))
        stat_card("rx", "Active prescriptions", metrics.get("active_rx_count", 0),
                  "Currently marked active in your records", "pill", "amber",
                  "View medicines", navigate, ("Prescriptions & Medicines", {filter_key("rx", "status"): "Active",
                                                                             "rx_tab": "Active prescriptions"}))
        stat_card("reports", "Diagnostic reports", metrics.get("total_reports", 0), report_sub, "flask", "blue",
                  "View reports", navigate, ("Scans & Diagnostics",))
        stat_card("all", "All health records", metrics.get("all_records_count", 0),
                  "Visits, reports, medicines, appointments & vitals", "folder", "slate",
                  "Browse all", navigate, ("All Records",))


def render_appointment_list(apts: pd.DataFrame, key_prefix: str, limit: int = 3):
    """Compact upcoming-appointment rows with a details button each."""
    if apts.empty:
        html_block('<div class="cv-empty-inline">No upcoming appointments. Use <strong>Add record</strong> to add one.</div>')
        return
    for apt in apts.head(limit).to_dict(orient="records"):
        rid = apt["apt_id"]
        with st.container(border=True, key=f"cvapt_{key_prefix}_{slug(rid)}"):
            c1, c2 = st.columns([4.2, 1.4], vertical_alignment="center", gap="small")
            with c1:
                html_block(
                    f"""
                    <div class="cv-apt">
                        <div class="cv-apt-date" aria-hidden="true">
                            <span class="cv-apt-month">{esc(format_date(apt.get('date'))[3:6])}</span>
                            <span class="cv-apt-day">{esc(format_date(apt.get('date'))[:2])}</span>
                        </div>
                        <div class="cv-apt-main">
                            <div class="cv-row-top">
                                <span class="cv-row-title">{esc(apt.get('type'), 'Appointment')}</span>
                                {render_badge(apt.get('status'))}
                                <span class="cv-when">{esc(relative_day(apt.get('date')), '')}</span>
                            </div>
                            <div class="cv-apt-line"><strong>{esc(format_date(apt.get('date')))}</strong> · {esc(apt.get('time'), 'Time not set')}</div>
                            <div class="cv-apt-line">{esc(apt.get('doctor'))} · {esc(apt.get('department'))}</div>
                            <div class="cv-apt-line cv-muted">{esc(apt.get('facility'))}{(' · ' + esc(apt.get('room'))) if not is_missing(apt.get('room')) else ''}</div>
                        </div>
                    </div>
                    """
                )
            with c2:
                st.button("Details", key=f"{key_prefix}_apt_{rid}", on_click=open_dialog, args=("appointment", rid),
                          icon=":material/visibility:", width="stretch", help="See appointment details and actions")


def render_upcoming_appointment_card(apt: Any):
    """Backward-compatible single appointment card."""
    if apt is None:
        render_appointment_list(pd.DataFrame(), "single")
        return
    render_appointment_list(pd.DataFrame([dict(apt)]), "single", limit=1)


def render_emergency_id_card(patient: Dict[str, Any]):
    """Emergency Medical ID — shows 'Not provided' for anything missing."""
    def val(key):
        return esc(patient.get(key), "Not provided")

    def cls(key):
        return " is-missing" if is_missing(patient.get(key)) else ""

    with st.container(border=True, key="cv_emergency"):
        html_block(
            f"""
            <div class="emergency-header">
                <div class="emergency-title">{icon('alert', 18)}<span>Emergency Medical ID</span></div>
                <span class="cv-demo-pill">Demo data</span>
            </div>
            <dl class="emergency-grid">
                <div><dt class="emergency-field-label">Blood type</dt><dd class="emergency-field-val is-blood{cls('blood_type')}">{val('blood_type')}</dd></div>
                <div><dt class="emergency-field-label">Known allergies</dt><dd class="emergency-field-val{cls('allergies')}">{'<span class="cv-badge badge-danger"><span aria-hidden="true">!</span>' + val('allergies') + '</span>' if not is_missing(patient.get('allergies')) else val('allergies')}</dd></div>
                <div><dt class="emergency-field-label">Medical conditions</dt><dd class="emergency-field-val{cls('primary_condition')}">{val('primary_condition')}</dd></div>
                <div><dt class="emergency-field-label">Organ donor</dt><dd class="emergency-field-val{cls('organ_donor')}">{val('organ_donor')}</dd></div>
                <div><dt class="emergency-field-label">Emergency contact</dt><dd class="emergency-field-val{cls('emergency_contact')}">{val('emergency_contact')}</dd></div>
                <div><dt class="emergency-field-label">Emergency phone</dt><dd class="emergency-field-val cv-mono{cls('emergency_phone')}">{val('emergency_phone')}</dd></div>
            </dl>
            """
        )
        st.button("Update emergency details", key="emergency_edit_btn", type="tertiary", icon=":material/edit:",
                  on_click=navigate, args=("Settings", {"_cv_settings_tab": "profile"}))


def render_recent_activity(index: pd.DataFrame = None, key_prefix: str = "activity"):
    """Chronological feed of the latest dated records; each item opens its record."""
    if index is None:
        from utils.data_loader import recent_activity
        index = recent_activity()
    if index.empty:
        html_block('<div class="cv-empty-inline">No records yet.</div>')
        return
    added = st.session_state.get("_cv_session_added", set())
    for item in index.to_dict(orient="records"):
        kind = item["kind"]
        new_tag = '<span class="cv-demo-pill is-user">Added by you</span>' if (kind, item["record_id"]) in added else ""
        with st.container(key=f"cvfeed_{key_prefix}_{slug(item['record_id'])}"):
            c1, c2 = st.columns([5, 1.3], vertical_alignment="center", gap="small")
            with c1:
                html_block(
                    f"""
                    <div class="cv-feed-item">
                        <div class="cv-row-icon tone-{KIND_TONE[kind]} is-sm">{icon(KIND_ICON[kind], 15)}</div>
                        <div>
                            <div class="cv-feed-meta">{esc(format_date(item['date']))} · {esc(RECORD_TYPES[kind].label)} {new_tag}</div>
                            <div class="cv-feed-title">{esc(item['title'])}</div>
                            <div class="cv-feed-sub">{esc(item['details'], '')}</div>
                        </div>
                    </div>
                    """
                )
            with c2:
                st.button("Open", key=f"{key_prefix}_open_{item['record_id']}", type="tertiary",
                          on_click=open_dialog, args=(kind, item["record_id"]), icon=":material/chevron_right:",
                          icon_position="right", help=f"Open this {RECORD_TYPES[kind].label.lower()}")


def _report_ready(status: str) -> bool:
    s = str(status).lower()
    return "final" in s or "ready" in s


def render_diagnostic_card(rec: Dict[str, Any], key_prefix: str = ""):
    """Report-library card. The main button says 'View report' only when a final report is recorded."""
    rid = rec.get("record_id")
    status = display(rec.get("status"), "Not recorded")
    group = diagnostic_group(rec.get("category", ""))
    summary = display(rec.get("summary"), "")
    summary_html = (f'<div class="cv-card-summary">{html.escape(summary)}</div>' if summary
                    else '<div class="cv-card-summary is-missing">No result summary recorded</div>')
    with st.container(border=True, key=f"cvcard_{key_prefix}_{slug(rid)}"):
        html_block(
            f"""
            <div class="cv-card-top">
                <span class="cv-card-date">{esc(format_date(rec.get('date')))}</span>
                {render_badge(status)}
            </div>
            <div class="cv-card-title-row">
                <div class="cv-row-icon tone-blue is-sm">{icon('flask', 15)}</div>
                <div class="cv-card-title">{esc(rec.get('scan_type'))}</div>
            </div>
            <div class="cv-chip">{esc(group)}</div>
            <div class="cv-card-line">{esc(rec.get('facility'))}</div>
            <div class="cv-card-line cv-muted">Ordered by {esc(rec.get('ordering_doctor'))}</div>
            {summary_html}
            """
        )
        c1, c2 = st.columns([1.6, 1], gap="small")
        with c1:
            st.button("View report" if _report_ready(status) else "View status", key=f"{key_prefix}_diag_btn_{rid}",
                      on_click=open_dialog, args=("diagnostic", rid), icon=":material/description:", width="stretch",
                      help="Open the report viewer")
        with c2:
            st.button("Edit", key=f"{key_prefix}_diag_edit_{rid}", on_click=open_dialog, args=("diagnostic", rid, "edit"),
                      icon=":material/edit:", type="tertiary", width="stretch")


def render_prescription_card(rx: Dict[str, Any], key_prefix: str = ""):
    """Prescription card with view and edit actions."""
    rid = rx.get("rx_id")
    refills = rx.get("refills_remaining")
    low = not is_missing(refills) and int(refills) <= 1 and rx.get("status") == "Active"
    refill_html = (f'<span class="cv-refill {"is-low" if low else ""}">{"⚠ " if low else ""}{esc(refills)} refill{"s" if is_missing(refills) or int(refills) != 1 else ""} left</span>'
                   if not is_missing(refills) else '<span class="cv-refill is-missing">Refills not recorded</span>')
    end = rx.get("end_date")
    with st.container(border=True, key=f"cvcard_{key_prefix}_{slug(rid)}"):
        html_block(
            f"""
            <div class="cv-card-top">
                <span class="cv-card-date cv-mono">{esc(rid)}</span>
                {render_badge(rx.get('status'))}
            </div>
            <div class="cv-card-title-row">
                <div class="cv-row-icon tone-amber is-sm">{icon('pill', 15)}</div>
                <div class="cv-card-title">{esc(rx.get('medication'))}</div>
            </div>
            <div class="cv-card-emph">{esc(rx.get('dosage'))} · {esc(rx.get('frequency'))}</div>
            <div class="cv-card-line">Prescribed by {esc(rx.get('prescribing_doctor'))}</div>
            <div class="cv-card-line cv-muted">{esc(format_date(rx.get('start_date')))} → {esc(format_date(end)) if not is_missing(end) else 'No end date recorded'}</div>
            <div class="cv-card-footer">{refill_html}</div>
            """
        )
        c1, c2 = st.columns([1.6, 1], gap="small")
        with c1:
            st.button("View medication", key=f"{key_prefix}_rx_view_{rid}", on_click=open_dialog,
                      args=("prescription", rid), icon=":material/visibility:", width="stretch")
        with c2:
            st.button("Edit", key=f"{key_prefix}_rx_edit_{rid}", on_click=open_dialog,
                      args=("prescription", rid, "edit"), icon=":material/edit:", type="tertiary", width="stretch")


def card_grid(key: str):
    """Wrapping grid: cards flow into as many columns as fit (one column on phones)."""
    return st.container(horizontal=True, gap="small", key=f"cvcards_{key}")
