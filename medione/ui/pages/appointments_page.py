"""Book, prepare for and follow up on doctor appointments."""
from __future__ import annotations

from datetime import date, time

import streamlit as st

from medione.models import APPOINTMENT_KINDS, APPOINTMENT_STATUSES
from medione.services import appointments, directory, visit_prep
from medione.ui.state import Ctx, flash, go, open_record
from medione.ui.widgets import (badge, date_block, disclaimer, doctor_options, esc, facility_options,
                                label_for, md, page_header, section)


def _form(ctx: Ctx, key: str, a: dict | None = None) -> None:
    a = a or {}
    docs, facs = doctor_options(ctx.uid), facility_options(ctx.uid)
    with st.form(key, clear_on_submit=not a):
        c1, c2, c3 = st.columns(3)
        starts = c1.date_input("Date *", value=date.fromisoformat(a["starts_on"]) if a.get("starts_on") else date.today(),
                               format="DD/MM/YYYY")
        has_time = bool(a.get("time_of_day")) if a else True
        t_val = time.fromisoformat(a["time_of_day"]) if a.get("time_of_day") else time(10, 0)
        at = c2.time_input("Time", value=t_val, step=900)
        use_time = c2.checkbox("Time is fixed", value=has_time)
        kinds = list(APPOINTMENT_KINDS)
        kind = c3.selectbox("Type", kinds, index=kinds.index(a.get("kind", "consultation")), format_func=APPOINTMENT_KINDS.get)
        purpose = st.text_input("What is it for? *", value=a.get("purpose") or "",
                                placeholder="e.g. Diabetes review, Dental check-up, MRI knee")
        c4, c5 = st.columns(2)
        doc = c4.selectbox("Doctor", list(docs), index=list(docs).index(label_for(docs, a.get("doctor_id"))))
        new_doc = c4.text_input("…or a new doctor", placeholder="Name")
        fac = c5.selectbox("Hospital / clinic / lab", list(facs), index=list(facs).index(label_for(facs, a.get("facility_id"))))
        new_fac = c5.text_input("…or a new place", placeholder="Name")
        questions = st.text_area("Questions to ask the doctor (one per line)", value=a.get("questions") or "", height=100,
                                 help="Write them down now so you don't forget during the visit. They go on your visit sheet.")
        notes = st.text_area("Notes (preparation, fasting, documents to carry…)", value=a.get("notes") or "", height=70)
        if st.form_submit_button("Save appointment" if a else "Book appointment", type="primary"):
            try:
                fac_id = directory.find_or_create_facility(ctx.uid, new_fac) if new_fac.strip() else facs[fac]
                doc_id = directory.find_or_create_doctor(ctx.uid, new_doc, fac_id) if new_doc.strip() else docs[doc]
                appointments.save_appointment(ctx.uid, ctx.pid, {
                    "starts_on": starts, "time_of_day": at.strftime("%H:%M") if use_time else "", "kind": kind,
                    "purpose": purpose, "doctor_id": doc_id, "facility_id": fac_id, "questions": questions,
                    "notes": notes, "status": a.get("status", "upcoming")}, a.get("id"))
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state.pop("appt_new_open", None)
                flash("Appointment saved." if a else "Appointment booked. Add it to your calendar so you get a reminder.")
                st.rerun()


def _status(uid: int, aid: int, status: str, outcome: str = "") -> None:
    appointments.set_status(uid, aid, status, outcome)
    flash(f"Marked as {APPOINTMENT_STATUSES[status].lower()}.")


def _card(ctx: Ctx, a: dict, mode: str) -> None:
    with st.container(border=True):
        who = " · ".join(esc(x) for x in (a["doctor_name"] + (f" ({a['doctor_specialty']})" if a["doctor_specialty"] else "")
                                          if a["doctor_name"] else None, a["facility_name"]) if x)
        if mode == "upcoming":
            d = a["days_away"]
            when = badge("Today" if d == 0 else "Tomorrow" if d == 1 else f"In {d} days", "amber" if d <= 1 else "teal")
        elif mode == "needs_update":
            when = badge("Needs update", "amber")
        else:
            when = badge(APPOINTMENT_STATUSES[a["status"]],
                         {"completed": "green", "cancelled": "gray", "missed": "red"}[a["status"]])
        md(f'<div class="tm-appt">{date_block(a["starts_on"])}<div><div class="tm-row-title">{esc(a["purpose"])} {when}</div>'
           f'<div class="tm-row-meta">{esc(a["time_of_day"] or "Time not set")} · {esc(APPOINTMENT_KINDS[a["kind"]])}'
           f'{("<br>" + who) if who else ""}</div></div></div>')
        if a["questions"] and mode != "history":
            md("<div class='tm-row-meta' style='margin-top:.5rem'><b>Questions to ask:</b></div>")
            for q in a["questions"].splitlines():
                if q.strip():
                    md(f"<div class='tm-row-meta'>• {esc(q.strip('-• '))}</div>")
        if a["notes"]:
            st.caption(f"📝 {a['notes']}")
        if a["outcome"]:
            st.caption(f"Outcome: {a['outcome']}")
        if mode == "upcoming":
            c1, c2, c3, c4 = st.columns(4)
            c1.download_button("Visit sheet", visit_prep.visit_prep_html(ctx.uid, a["id"]), f"visit-prep-{a['starts_on']}.html",
                               "text/html", key=f"ap_prep_{a['id']}", icon=":material/assignment:", width="stretch")
            c2.download_button("Add to calendar", appointments.appointment_ics(a), f"appointment-{a['starts_on']}.ics",
                               "text/calendar", key=f"ap_ics_{a['id']}", icon=":material/event:", width="stretch")
            with c3.popover("Edit", icon=":material/edit:", width="stretch"):
                _form(ctx, f"ap_edit_{a['id']}", a)
            with c4.popover("Cancel", icon=":material/event_busy:", width="stretch"):
                st.caption("This only updates your records. Please also tell the clinic.")
                st.button("Yes, cancel it", key=f"ap_cancel_{a['id']}", on_click=_status,
                          args=(ctx.uid, a["id"], "cancelled"))
        elif mode == "needs_update":
            outcome = st.text_input("What happened? (optional)", key=f"ap_out_{a['id']}",
                                    placeholder="e.g. Doctor changed dose, ordered tests")
            c1, c2, c3 = st.columns(3)
            c1.button("Completed", key=f"ap_done_{a['id']}", on_click=_status, args=(ctx.uid, a["id"], "completed", outcome),
                      type="primary", width="stretch")
            c2.button("Missed", key=f"ap_miss_{a['id']}", on_click=_status, args=(ctx.uid, a["id"], "missed", outcome),
                      width="stretch")
            c3.button("Cancelled", key=f"ap_canc_{a['id']}", on_click=_status,
                      args=(ctx.uid, a["id"], "cancelled", outcome), width="stretch")
        else:
            c1, c2 = st.columns(2)
            if a["status"] == "completed":
                if a["record_id"]:
                    c1.button("Open visit record", key=f"ap_rec_{a['id']}", on_click=open_record, args=(a["record_id"],))
                else:
                    c1.button("Upload the prescription / notes", key=f"ap_up_{a['id']}", on_click=go,
                              args=("Add record",), icon=":material/upload_file:")
            with c2.popover("Delete", icon=":material/delete:"):
                if st.checkbox("Confirm delete", key=f"ap_del_ok_{a['id']}"):
                    if st.button("Delete appointment", key=f"ap_del_{a['id']}"):
                        appointments.delete_appointment(ctx.uid, a["id"])
                        flash("Appointment deleted.", "info")
                        st.rerun()


def render(ctx: Ctx) -> None:
    page_header("Appointments", "Plan visits, write down your questions, and keep track of what happened.", "calendar")
    data = appointments.list_appointments(ctx.uid, ctx.pid)
    with st.expander("Book a new appointment", expanded=bool(st.session_state.get("appt_new_open")),
                     icon=":material/event_available:"):
        _form(ctx, "ap_new")
    tabs = st.tabs([f"Upcoming ({len(data['upcoming'])})", f"Needs update ({len(data['needs_update'])})",
                    f"Past ({len(data['history'])})"])
    for tab, mode in zip(tabs, ["upcoming", "needs_update", "history"]):
        with tab:
            items = data[mode]
            if not items:
                st.caption({"upcoming": "No upcoming appointments. Book one above.",
                            "needs_update": "Nothing to update.", "history": "No past appointments yet."}[mode])
            for a in items:
                _card(ctx, a, mode)
    section("Tip", "sparkle")
    st.caption("Download the visit sheet before you go: it has your questions, current medicines, symptoms and recent "
               "readings on one page, so nothing is forgotten in a short consultation.")
    disclaimer()
