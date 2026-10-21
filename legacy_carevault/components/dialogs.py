"""Record dialogs: details, report viewer, add/edit forms and confirmations.

Pages never open dialogs directly. They call ``components.state.open_dialog``
(usually as a button ``on_click``) and ``render_active_dialog`` draws exactly
one dialog at the end of the run. Closing with the X, the Close button or Esc
clears the state, so a dialog never reopens by surprise.
"""
from datetime import date
from typing import Any, Dict

import streamlit as st

from components.forms import render_record_form
from components.state import active_dialog, close_dialog, flash, open_dialog
from components.ui import KIND_ICON, KIND_TONE, Raw, html_block, icon, info_grid, notice, text_panel
from utils.data_loader import get_patient_info, refill_prescription
from utils.exports import appointment_ics, printable_record
from utils.helpers import display, esc, format_date, is_missing, parse_date, relative_day, render_badge
from utils.records import (
    RECORD_TYPES, delete_record, get_record, linked_records, record_status, record_subtitle,
    record_title, update_record, visit_label,
)

ADD_ORDER = ("visit", "diagnostic", "prescription", "history", "appointment", "vital")
MEDICAL_NOTE = ("CareVault only keeps a copy of what was recorded. Check medical information with a qualified "
                "healthcare professional, and don't change how you take a medicine without speaking to your "
                "doctor or pharmacist.")


def render_active_dialog():
    state = active_dialog()
    if not state:
        return
    kind, mode = state.get("kind"), state.get("mode", "view")
    if kind not in RECORD_TYPES:
        close_dialog()
        return
    rt = RECORD_TYPES[kind]
    titles = {
        "view": rt.label,
        "edit": f"Edit {rt.label.lower()}",
        "add": "Add a health record",
        "delete": f"Delete {rt.label.lower()}?",
        "cancel_appointment": "Cancel this appointment?",
    }
    width = "small" if mode in ("delete", "cancel_appointment") else "large"
    body = {"view": _view_body, "edit": _edit_body, "add": _add_body, "delete": _delete_body,
            "cancel_appointment": _cancel_body}.get(mode, _view_body)
    st.dialog(titles.get(mode, rt.label), width=width, on_dismiss=close_dialog)(body)(state)


# --------------------------------------------------------------------------
# Shared pieces
# --------------------------------------------------------------------------
def _go(kind: str, record_id: str = None, mode: str = "view"):
    open_dialog(kind, record_id, mode)
    st.rerun()


def _missing_record():
    html_block(notice("This record is no longer available. It may have been deleted.", "warning"))
    if st.button("Close", key="dlg_missing_close", width="stretch"):
        close_dialog()
        st.rerun()


def _source_label(kind: str, rid: str) -> str:
    added = (kind, rid) in st.session_state.get("_cv_session_added", set())
    return ('<span class="cv-demo-pill is-user">Added by you</span>' if added
            else '<span class="cv-demo-pill">Demo record</span>')


def _header(kind: str, rec: Dict[str, Any]):
    rt = RECORD_TYPES[kind]
    rid = rec[rt.id_col]
    status = record_status(kind, rec)
    badge = render_badge(status) if kind != "vital" else ""
    html_block(
        f"""
        <div class="cv-detail-head">
            <div class="cv-row-icon tone-{KIND_TONE[kind]} is-lg">{icon(KIND_ICON[kind], 22)}</div>
            <div class="cv-detail-head-main">
                <div class="cv-detail-eyebrow">{esc(rt.label)} · <span class="cv-mono">{esc(rid)}</span> {_source_label(kind, rid)}</div>
                <div class="cv-detail-title">{esc(record_title(kind, rec))}</div>
                <div class="cv-detail-sub">{esc(record_subtitle(kind, rec), '')}</div>
            </div>
            <div class="cv-detail-badge">{badge}</div>
        </div>
        """
    )


def _date_with_relative(value: Any) -> Raw:
    if is_missing(value):
        return Raw('<span class="is-missing">Not recorded</span>')
    rel = relative_day(value)
    return Raw(f"{esc(format_date(value))} <span class='cv-muted'>({esc(rel)})</span>" if rel else esc(format_date(value)))


def _related_visit_section(kind: str, rec: Dict[str, Any]):
    vid = rec.get("visit_id")
    html_block('<div class="cv-subhead">Related hospital visit</div>')
    if is_missing(vid):
        html_block('<p class="cv-muted cv-small">No visit is linked. Use <strong>Edit</strong> to link the visit this record came from.</p>')
        return
    if get_record("visit", vid) is None:
        html_block(f'<p class="cv-muted cv-small">The linked visit ({esc(vid)}) is no longer available.</p>')
        return
    rid = rec[RECORD_TYPES[kind].id_col]
    if st.button(visit_label(vid), key=f"dlg_rel_visit_{rid}", icon=":material/local_hospital:", width="stretch",
                 help="Open the linked hospital visit"):
        _go("visit", vid)


def _action_bar(kind: str, rec: Dict[str, Any], extra=None):
    """Edit / printable copy / delete / close. ``extra`` draws kind-specific actions first."""
    rt = RECORD_TYPES[kind]
    rid = rec[rt.id_col]
    st.divider()
    if extra:
        extra()
    c1, c2, c3, c4 = st.columns(4, gap="small")
    with c1:
        if st.button("Edit", key=f"dlg_edit_{rid}", icon=":material/edit:", width="stretch", type="primary"):
            _go(kind, rid, "edit")
    with c2:
        st.download_button(
            "Printable copy", data=printable_record(kind, rec, get_patient_info()),
            file_name=f"CareVault_{rid}.html", mime="text/html", key=f"dlg_print_{rid}",
            icon=":material/print:", width="stretch", on_click="ignore",
            help="Downloads an HTML file you can open in a browser and print or save as PDF.",
        )
    with c3:
        if st.button("Delete", key=f"dlg_delete_{rid}", icon=":material/delete:", width="stretch"):
            _go(kind, rid, "delete")
    with c4:
        if st.button("Close", key=f"dlg_close_{rid}", icon=":material/close:", width="stretch"):
            close_dialog()
            st.rerun()


# --------------------------------------------------------------------------
# View bodies
# --------------------------------------------------------------------------
def _view_body(state: Dict[str, Any]):
    kind, rid = state["kind"], state.get("id")
    rec = get_record(kind, rid)
    if rec is None:
        _missing_record()
        return
    _header(kind, rec)
    {"visit": _view_visit, "diagnostic": _view_diagnostic, "prescription": _view_prescription,
     "history": _view_history, "appointment": _view_appointment, "vital": _view_vital}[kind](rec)


def _view_visit(rec: Dict[str, Any]):
    html_block(info_grid([
        ("Visit date", _date_with_relative(rec.get("date"))),
        ("Visit type", rec.get("visit_type")),
        ("Hospital", rec.get("hospital_name")),
        ("Department", rec.get("department")),
        ("Doctor", rec.get("attending_physician")),
        ("Diagnosis or code", rec.get("diagnosis_code")),
    ]))
    html_block(text_panel("Reason for visit", rec.get("reason_for_visit")))
    html_block(text_panel("Visit notes", rec.get("summary")))
    html_block(text_panel("Follow-up instructions (as recorded)", rec.get("discharge_instructions"), tone="teal"))

    html_block('<div class="cv-subhead">Linked records</div>')
    links = linked_records(rec["visit_id"])
    if not links:
        html_block('<p class="cv-muted cv-small">No reports, prescriptions or appointments are linked to this visit. '
                   'To link one, open it, choose <strong>Edit</strong>, and pick this visit under '
                   '<em>Related hospital visit</em>.</p>')
    for lkind, lrec in links:
        lrt = RECORD_TYPES[lkind]
        lid = lrec[lrt.id_col]
        label = f"{lrt.label}: {record_title(lkind, lrec)} · {format_date(lrec.get(lrt.date_col))}"
        if st.button(label, key=f"dlg_link_{rec['visit_id']}_{lid}", icon=":material/link:", width="stretch"):
            _go(lkind, lid)
    _action_bar("visit", rec)


def _view_diagnostic(rec: Dict[str, Any]):
    status = display(rec.get("status"), "")
    if "final" in status.lower() or "ready" in status.lower():
        html_block(notice("Final report recorded.", "success", "file"))
    elif "unavailable" in status.lower():
        html_block(notice("No report is available for this test. Any text below is what was recorded about it.", "neutral", "file"))
    else:
        html_block(notice(f"<strong>{esc(status)}:</strong> this report is not final. Results may change when the facility "
                          "releases the final report.", "warning", "clock"))

    patient = get_patient_info()
    html_block(info_grid([
        ("Patient", patient.get("name")),
        ("Patient ID", patient.get("patient_id")),
        ("Test date", _date_with_relative(rec.get("date"))),
        ("Category", rec.get("category")),
        ("Facility", rec.get("facility")),
        ("Ordered by", rec.get("ordering_doctor")),
        ("Reference number", rec.get("accession_no")),
        ("Reference range", rec.get("normal_range")),
    ]))
    html_block(text_panel("Result summary", rec.get("summary")))
    html_block(text_panel("Detailed findings", rec.get("findings")))
    html_block(text_panel("Conclusion / impression", rec.get("impression"), tone="blue"))

    html_block('<div class="cv-subhead">Report file</div>')
    att = st.session_state.get("attachments", {}).get(("diagnostic", rec["record_id"]))
    if att:
        if str(att.get("type", "")).startswith("image/"):
            st.image(att["data"], caption=att["name"])
        st.download_button(f"Download {att['name']}", data=att["data"], file_name=att["name"],
                           mime=att.get("type") or "application/octet-stream", key=f"dlg_att_{rec['record_id']}",
                           icon=":material/download:", on_click="ignore")
    else:
        html_block('<div class="cv-placeholder">' + icon("file", 28) +
                   '<div><strong>No report file attached</strong><br><span class="cv-muted">'
                   'The details above are the recorded text only. Use Edit to attach a PDF or photo of the report.'
                   '</span></div></div>')
    _related_visit_section("diagnostic", rec)
    _action_bar("diagnostic", rec)


def _view_prescription(rec: Dict[str, Any]):
    refills = rec.get("refills_remaining")
    end = rec.get("end_date")
    html_block(info_grid([
        ("Dose / strength", rec.get("dosage")),
        ("How often (as prescribed)", rec.get("frequency")),
        ("How it is taken", rec.get("route")),
        ("Prescribing doctor", rec.get("prescribing_doctor")),
        ("Start date", _date_with_relative(rec.get("start_date"))),
        ("End date", _date_with_relative(end) if not is_missing(end) else Raw('<span class="is-missing">No end date recorded</span>')),
        ("Refills remaining", refills),
        ("Pharmacy", rec.get("pharmacy")),
    ]))
    html_block(text_panel("Directions on the label", rec.get("instructions")))
    html_block(text_panel("Warnings on the label", rec.get("warnings"), tone="amber"))
    html_block(notice(MEDICAL_NOTE, "info", "shield"))
    _related_visit_section("prescription", rec)

    def refill_action():
        rid = rec["rx_id"]
        can_refill = not is_missing(refills) and int(refills) > 0 and rec.get("status") == "Active"
        if st.button("Log a refill collected", key=f"dlg_refill_{rid}", icon=":material/autorenew:", width="stretch",
                     disabled=not can_refill,
                     help="Reduces 'Refills remaining' by one. It does not contact your pharmacy."):
            if refill_prescription(rid):
                flash(f"Refill logged. {int(refills) - 1} refill(s) remaining for {rec.get('medication')}.")
                _go("prescription", rid)
        if not can_refill:
            reason = ("only active prescriptions can log refills" if rec.get("status") != "Active"
                      else "no refills remaining are recorded")
            html_block(f'<p class="cv-muted cv-small">Logging a refill isn\'t available: {reason}.</p>')
        else:
            html_block('<p class="cv-muted cv-small">This only updates your record — it does not contact a pharmacy.</p>')

    _action_bar("prescription", rec, extra=refill_action)


def _view_history(rec: Dict[str, Any]):
    html_block(info_grid([
        ("Dose / strength", rec.get("dosage")),
        ("Status", rec.get("status")),
        ("Start date", _date_with_relative(rec.get("start_date"))),
        ("End date", _date_with_relative(rec.get("end_date"))),
        ("Prescribed by", rec.get("prescribed_by")),
        ("Recorded reason", rec.get("reason")),
    ]))
    html_block(text_panel("Notes", rec.get("notes")))
    html_block(notice(MEDICAL_NOTE, "info", "shield"))
    _related_visit_section("history", rec)
    _action_bar("history", rec)


def _view_appointment(rec: Dict[str, Any]):
    rid = rec["apt_id"]
    d = parse_date(rec.get("date"))
    if rec.get("status") == "Upcoming" and d and d < date.today():
        html_block(notice("This appointment's date has passed but it is still marked Upcoming. "
                          "Use <strong>Mark as completed</strong> or <strong>Edit</strong> to update it.", "warning", "clock"))
    html_block(info_grid([
        ("Date", _date_with_relative(rec.get("date"))),
        ("Time", rec.get("time")),
        ("Doctor", rec.get("doctor")),
        ("Department", rec.get("department")),
        ("Facility", rec.get("facility")),
        ("Room / location", rec.get("room")),
        ("Appointment type", rec.get("type")),
        ("Status", rec.get("status")),
    ]))
    html_block(text_panel("Preparation notes", rec.get("instructions"), tone="blue"))
    _related_visit_section("appointment", rec)

    def appointment_actions():
        if rec.get("status") != "Upcoming":
            return
        c1, c2, c3 = st.columns(3, gap="small")
        with c1:
            st.download_button("Add to calendar", data=appointment_ics(rec), file_name=f"{rid}.ics",
                               mime="text/calendar", key=f"dlg_ics_{rid}", icon=":material/event:",
                               width="stretch", on_click="ignore",
                               help="Downloads a calendar file (.ics) you can open in Outlook, Google or Apple Calendar.")
        with c2:
            if st.button("Mark as completed", key=f"dlg_done_{rid}", icon=":material/task_alt:", width="stretch"):
                update_record("appointment", rid, {"status": "Completed"})
                flash("Appointment marked as completed.")
                _go("appointment", rid)
        with c3:
            if st.button("Cancel appointment", key=f"dlg_cancel_{rid}", icon=":material/event_busy:", width="stretch"):
                _go("appointment", rid, "cancel_appointment")
        html_block('<p class="cv-muted cv-small">These actions update your record only. CareVault does not contact the clinic.</p>')

    _action_bar("appointment", rec, extra=appointment_actions)


def _view_vital(rec: Dict[str, Any]):
    d = parse_date(rec.get("date"))
    if d and d > date.today():
        html_block(notice("This reading is dated in the future, so it is left out of charts and latest values. "
                          "Use Edit to correct the date.", "warning", "clock"))

    def measure(col, unit, fmt="{:g}"):
        v = rec.get(col)
        return None if is_missing(v) else f"{fmt.format(float(v))} {unit}"
    bp = (f"{display(rec.get('systolic_bp'))}/{display(rec.get('diastolic_bp'))} mmHg"
          if not is_missing(rec.get("systolic_bp")) and not is_missing(rec.get("diastolic_bp")) else None)
    html_block(info_grid([
        ("Date measured", _date_with_relative(rec.get("date"))),
        ("Measured with / by", rec.get("recorded_by")),
        ("Heart rate", measure("heart_rate", "bpm")),
        ("Blood pressure", bp),
        ("Weight", measure("weight_kg", "kg", "{:.1f}")),
        ("Blood oxygen (SpO₂)", measure("spo2", "%")),
    ]))
    html_block(text_panel("Notes", rec.get("notes")))
    _action_bar("vital", rec)


# --------------------------------------------------------------------------
# Add / edit / confirm bodies
# --------------------------------------------------------------------------
def _edit_body(state: Dict[str, Any]):
    render_record_form(state["kind"], "edit", state.get("id"))


def _add_body(state: Dict[str, Any]):
    key = "frm_add_kind"
    if key not in st.session_state:
        st.session_state[key] = state.get("kind", "visit")
    kind = st.selectbox(
        "What would you like to add?", ADD_ORDER, key=key,
        format_func=lambda k: RECORD_TYPES[k].label,
        help="Only the fields for this kind of record will be shown.",
    )
    render_record_form(kind, "add", preset=state.get("preset"))


def _delete_body(state: Dict[str, Any]):
    kind, rid = state["kind"], state.get("id")
    rt = RECORD_TYPES[kind]
    rec = get_record(kind, rid)
    if rec is None:
        _missing_record()
        return
    html_block(
        f'<div class="cv-confirm-target"><div class="cv-detail-eyebrow">{esc(rt.label)} · <span class="cv-mono">{esc(rid)}</span></div>'
        f'<div class="cv-detail-title">{esc(record_title(kind, rec))}</div>'
        f'<div class="cv-muted">{esc(format_date(rec.get(rt.date_col)))} · {esc(record_subtitle(kind, rec), "")}</div></div>'
    )
    html_block(notice("This permanently removes the record from CareVault. It can't be undone.", "danger", "alert"))
    if kind == "visit":
        links = linked_records(rid)
        if links:
            html_block(notice(f"{len(links)} linked record(s) will be kept, but they will no longer be linked to this visit.",
                              "warning", "alert"))
    c1, c2 = st.columns(2, gap="small")
    with c1:
        if st.button("Keep record", key=f"dlg_keep_{rid}", width="stretch", icon=":material/undo:"):
            _go(kind, rid, "view")
    with c2:
        with st.container(key="cv_danger_action"):
            if st.button("Delete permanently", key=f"dlg_confirm_delete_{rid}", type="primary", width="stretch",
                         icon=":material/delete_forever:"):
                if delete_record(kind, rid):
                    flash(f"{rt.label} deleted.", ":material/delete:")
                close_dialog()
                st.rerun()


def _cancel_body(state: Dict[str, Any]):
    rid = state.get("id")
    rec = get_record("appointment", rid)
    if rec is None:
        _missing_record()
        return
    html_block(
        f'<div class="cv-confirm-target"><div class="cv-detail-title">{esc(record_title("appointment", rec))}</div>'
        f'<div class="cv-muted">{esc(format_date(rec.get("date")))} · {esc(rec.get("time"), "Time not set")} · '
        f'{esc(rec.get("doctor"))}</div></div>'
    )
    html_block(notice("The appointment will be marked <strong>Cancelled</strong> in your records. "
                      "CareVault does not contact the clinic — please call them to cancel.", "warning", "alert"))
    c1, c2 = st.columns(2, gap="small")
    with c1:
        if st.button("Keep appointment", key=f"dlg_keep_apt_{rid}", width="stretch", icon=":material/undo:"):
            _go("appointment", rid, "view")
    with c2:
        with st.container(key="cv_danger_action"):
            if st.button("Yes, cancel it", key=f"dlg_confirm_cancel_{rid}", type="primary", width="stretch",
                         icon=":material/event_busy:"):
                update_record("appointment", rid, {"status": "Cancelled"})
                flash("Appointment marked as cancelled.", ":material/event_busy:")
                _go("appointment", rid)
