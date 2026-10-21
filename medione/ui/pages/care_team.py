"""Doctors and facilities (shared across the account's family profiles)."""
from __future__ import annotations

import streamlit as st

from medione.models import FACILITY_KINDS
from medione.services import directory, search
from medione.ui.state import Ctx, flash
from medione.ui.widgets import fmt_date, kv, md, page_header, record_row


def _doctor_form(ctx: Ctx, key: str, d: dict | None = None) -> None:
    facs = {"— Not recorded —": None, **{f["name"]: f["id"] for f in directory.list_facilities(ctx.uid)}}
    d = d or {}
    current = next((k for k, v in facs.items() if v == d.get("facility_id") and v), "— Not recorded —")
    with st.form(key):
        name = st.text_input("Name *", value=d.get("name") or "")
        c1, c2 = st.columns(2)
        specialty = c1.text_input("Specialty", value=d.get("specialty") or "", help="Only if you know it.")
        facility = c2.selectbox("Hospital / clinic", list(facs), index=list(facs).index(current))
        phone = c1.text_input("Phone", value=d.get("phone") or "")
        email = c2.text_input("Email", value=d.get("email") or "")
        notes = st.text_area("Notes", value=d.get("notes") or "", height=70)
        if st.form_submit_button("Save", type="primary"):
            try:
                directory.save_doctor(ctx.uid, {"name": name, "specialty": specialty, "facility_id": facs[facility],
                                                "phone": phone, "email": email, "notes": notes}, d.get("id"))
            except ValueError as exc:
                st.error(str(exc))
            else:
                flash("Saved.")
                st.rerun()


def _facility_form(ctx: Ctx, key: str, f: dict | None = None) -> None:
    f = f or {}
    with st.form(key):
        name = st.text_input("Name *", value=f.get("name") or "")
        c1, c2 = st.columns(2)
        kind = c1.selectbox("Type", FACILITY_KINDS, index=FACILITY_KINDS.index(f["kind"]) if f.get("kind") in FACILITY_KINDS else 0)
        phone = c2.text_input("Phone", value=f.get("phone") or "")
        address = st.text_input("Address", value=f.get("address") or "")
        notes = st.text_area("Notes", value=f.get("notes") or "", height=70)
        if st.form_submit_button("Save", type="primary"):
            try:
                directory.save_facility(ctx.uid, {"name": name, "kind": kind, "phone": phone, "address": address,
                                                  "notes": notes}, f.get("id"))
            except ValueError as exc:
                st.error(str(exc))
            else:
                flash("Saved.")
                st.rerun()


def render(ctx: Ctx) -> None:
    page_header("Doctors & facilities", "The people and places in your records. Shared by all family profiles.")
    tab_d, tab_f = st.tabs(["Doctors", "Hospitals, clinics & labs"])
    with tab_d:
        with st.expander("Add a doctor", icon=":material/person_add:"):
            _doctor_form(ctx, "dir_new_doc")
        doctors = directory.list_doctors(ctx.uid)
        if not doctors:
            st.caption("No doctors yet. They're added automatically when you name one on a record.")
        for d in doctors:
            with st.expander(f"{d['name']}" + (f" — {d['specialty']}" if d["specialty"] else "")
                             + f" · {d['record_count']} record(s)"):
                kv([("Specialty", d["specialty"]), ("Hospital / clinic", d["facility_name"]), ("Phone", d["phone"]),
                    ("Email", d["email"]), ("Last record", fmt_date(d["last_seen"], "")), ("Notes", d["notes"])])
                linked = search.search_records(ctx.uid, ctx.pid, doctor_id=d["id"])
                if linked:
                    st.markdown(f"**Records in {ctx.profile['full_name']}'s profile**")
                    for r in linked:
                        record_row(r, f"dir_doc_{d['id']}")
                if st.toggle("Edit", key=f"dir_edit_doc_{d['id']}"):
                    _doctor_form(ctx, f"dir_doc_form_{d['id']}", d)
                    if st.checkbox("Remove this doctor from the list (records are kept)", key=f"dir_del_doc_ok_{d['id']}"):
                        if st.button("Remove", key=f"dir_del_doc_{d['id']}"):
                            directory.delete_doctor(ctx.uid, d["id"])
                            flash("Removed. Linked records now show the doctor as not recorded.", "info")
                            st.rerun()
    with tab_f:
        with st.expander("Add a facility", icon=":material/add_business:"):
            _facility_form(ctx, "dir_new_fac")
        facilities = directory.list_facilities(ctx.uid)
        if not facilities:
            st.caption("No facilities yet.")
        for f in facilities:
            with st.expander(f"{f['name']} · {f['kind']} · {f['record_count']} record(s)"):
                kv([("Type", f["kind"]), ("Address", f["address"]), ("Phone", f["phone"]), ("Notes", f["notes"])])
                if st.toggle("Edit", key=f"dir_edit_fac_{f['id']}"):
                    _facility_form(ctx, f"dir_fac_form_{f['id']}", f)
                    if st.checkbox("Remove from the list (records are kept)", key=f"dir_del_fac_ok_{f['id']}"):
                        if st.button("Remove", key=f"dir_del_fac_{f['id']}"):
                            directory.delete_facility(ctx.uid, f["id"])
                            flash("Removed.", "info")
                            st.rerun()
    md("<br>")
    st.caption("Only details you enter (or that are written on your documents) are stored. "
               "Thought Medione doesn't look up or verify doctors' credentials.")
