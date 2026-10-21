"""One record form for adding, reviewing AI extractions and editing."""
from __future__ import annotations

import math
from datetime import date
from typing import Optional

import pandas as pd
import streamlit as st

from medione.models import CATEGORIES, MED_STATUSES, RECORD_TYPES, type_label
from medione.services import directory
from medione.ui.state import Ctx
from medione.ui.widgets import doctor_options, facility_options, label_for

MIN_DATE, MAX_DATE = date(1900, 1, 1), date(2100, 12, 31)
MED_COLS = ["name", "dosage", "frequency", "duration", "instructions", "status", "uncertain", "uncertain_note"]
LAB_COLS = ["test_name", "value_text", "unit", "ref_low", "ref_high", "ref_text", "uncertain"]


def to_date(value) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _clean_rows(df: pd.DataFrame) -> list[dict]:
    out = []
    for row in df.to_dict("records"):
        clean = {k: (None if (isinstance(v, float) and math.isnan(v)) else v) for k, v in row.items()}
        if any(v not in (None, "", False) for v in clean.values()):
            out.append(clean)
    return out


def type_picker(key: str, current: Optional[str] = None, disabled: bool = False) -> str:
    keys = list(RECORD_TYPES)
    labels = {k: f"{CATEGORIES[RECORD_TYPES[k].category]} › {type_label(k)}" for k in keys}
    index = keys.index(current) if current in keys else 0
    return st.selectbox("Record type", keys, index=index, format_func=labels.get, key=key, disabled=disabled)


def record_form(ctx: Ctx, key: str, rtype: str, initial: Optional[dict] = None, meds: Optional[list] = None,
                labs: Optional[list] = None, uncertain_fields: tuple = (), submit_label: str = "Save record",
                show_review_confirm: bool = False) -> Optional[dict]:
    """Render the form; on submit return {'data', 'meds', 'labs', 'reviewed'} (or None)."""
    initial = initial or {}
    details = initial.get("details") or {}
    t = RECORD_TYPES[rtype]
    docs, facs = doctor_options(ctx.uid), facility_options(ctx.uid)

    def mark(field: str, label: str) -> str:
        return f"{label} ⚠ check this" if field in uncertain_fields else label

    with st.form(key, enter_to_submit=False):
        title = st.text_input(mark("title", "Title *"), value=initial.get("title") or "", max_chars=160,
                              placeholder="e.g. Complete blood count, Prescription – Dr. Iyer")
        c1, c2 = st.columns(2)
        record_date = c1.date_input(mark("record_date", t.date_label), value=to_date(initial.get("record_date")),
                                    min_value=MIN_DATE, max_value=MAX_DATE, format="DD/MM/YYYY")
        end_date = None
        if t.end_date_label:
            end_date = c2.date_input(mark("end_date", t.end_date_label), value=to_date(initial.get("end_date")),
                                     min_value=MIN_DATE, max_value=MAX_DATE, format="DD/MM/YYYY")
        follow_up = (c2 if not t.end_date_label else c1).date_input(
            mark("follow_up_date", "Follow-up date (if written)"), value=to_date(initial.get("follow_up_date")),
            min_value=MIN_DATE, max_value=MAX_DATE, format="DD/MM/YYYY")

        c3, c4 = st.columns(2)
        doctor_label = c3.selectbox(mark("doctor_name", "Doctor"), list(docs),
                                    index=list(docs).index(label_for(docs, initial.get("doctor_id"))))
        new_doctor = c3.text_input("…or add a new doctor", value=initial.get("new_doctor") or "",
                                   placeholder="Name exactly as written")
        facility_label = c4.selectbox(mark("facility_name", "Hospital / clinic / lab"), list(facs),
                                      index=list(facs).index(label_for(facs, initial.get("facility_id"))))
        new_facility = c4.text_input("…or add a new facility", value=initial.get("new_facility") or "",
                                     placeholder="Name exactly as written")

        condition = st.text_input(mark("condition", "Condition / diagnosis (only if written by a doctor)"),
                                  value=initial.get("condition") or "")
        extras = {}
        for e in t.extras:
            label = mark(e.name, e.label)
            current = details.get(e.name)
            if e.kind == "textarea":
                extras[e.name] = st.text_area(label, value=current or "", height=90, help=e.help or None)
            elif e.kind == "select":
                opts = list(e.options)
                idx = opts.index(current) if current in opts else None
                extras[e.name] = st.selectbox(label, opts, index=idx, placeholder="Choose…", help=e.help or None)
            elif e.kind == "date":
                extras[e.name] = st.date_input(label, value=to_date(current), min_value=MIN_DATE, max_value=MAX_DATE,
                                               format="DD/MM/YYYY")
            else:
                extras[e.name] = st.text_input(label, value=current or "", help=e.help or None)

        meds_df = labs_df = None
        if t.has_medications or meds:
            st.markdown("**Medicines (copy exactly as written)**")
            st.caption("Add one row per medicine. Tick *Needs checking* if any part is unclear.")
            meds_df = st.data_editor(
                pd.DataFrame(meds or [], columns=MED_COLS), num_rows="dynamic", width="stretch",
                key=f"{key}_meds", hide_index=True,
                column_config={
                    "name": st.column_config.TextColumn("Medicine *", required=True),
                    "dosage": "Dose", "frequency": "How often", "duration": "For how long",
                    "instructions": "Instructions",
                    "status": st.column_config.SelectboxColumn("Status", options=list(MED_STATUSES), default="active"),
                    "uncertain": st.column_config.CheckboxColumn("Needs checking", default=False),
                    "uncertain_note": "What's unclear",
                })
        if t.has_lab_results or labs:
            st.markdown("**Test results (as printed on the report)**")
            labs_df = st.data_editor(
                pd.DataFrame(labs or [], columns=LAB_COLS), num_rows="dynamic", width="stretch",
                key=f"{key}_labs", hide_index=True,
                column_config={
                    "test_name": st.column_config.TextColumn("Test *", required=True),
                    "value_text": "Result", "unit": "Unit",
                    "ref_low": st.column_config.NumberColumn("Range low", format="%g"),
                    "ref_high": st.column_config.NumberColumn("Range high", format="%g"),
                    "ref_text": "Range (as text)",
                    "uncertain": st.column_config.CheckboxColumn("Needs checking", default=False),
                })

        summary = st.text_area(mark("summary", "Summary"), value=initial.get("summary") or "", height=80,
                               help="A short description of what the document says.")
        notes = st.text_area("Your notes", value=initial.get("notes") or "", height=70)
        reviewed = False
        if show_review_confirm:
            reviewed = st.checkbox("I have checked these details against the original document",
                                   help="Leave unticked to keep the record marked 'AI-extracted · not yet reviewed'.")
        submitted = st.form_submit_button(submit_label, type="primary")

    if not submitted:
        return None
    data = {
        "type": rtype, "title": title, "record_date": record_date, "end_date": end_date,
        "follow_up_date": follow_up, "doctor_id": docs[doctor_label], "facility_id": facs[facility_label],
        "condition": condition, "summary": summary, "notes": notes, "details": extras,
        "new_doctor": new_doctor.strip(), "new_facility": new_facility.strip(),
    }
    return {"data": data, "meds": _clean_rows(meds_df) if meds_df is not None else None,
            "labs": _clean_rows(labs_df) if labs_df is not None else None, "reviewed": reviewed}


def resolve_people(ctx: Ctx, data: dict) -> dict:
    """Create directory entries for newly typed doctor/facility names (names only — nothing is guessed)."""
    data = dict(data)
    new_fac, new_doc = data.pop("new_facility", ""), data.pop("new_doctor", "")
    if not data["title"] or not str(data["title"]).strip():
        return data  # let validation report the missing title before creating anything
    if new_fac:
        data["facility_id"] = directory.find_or_create_facility(ctx.uid, new_fac)
    if new_doc:
        data["doctor_id"] = directory.find_or_create_doctor(ctx.uid, new_doc, data.get("facility_id"))
    return data
