"""Medicines from prescriptions: current list and history."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from medione.services import records
from medione.ui.state import Ctx, flash, go, open_record
from medione.ui.widgets import badge, disclaimer, empty_state, esc, fmt_date, md, page_header


def _set_status(uid: int, mid: int, status: str) -> None:
    records.set_medication_status(uid, mid, status)
    flash("Updated your record. This doesn't change any prescription.", "info")


def render(ctx: Ctx) -> None:
    page_header("Medicines", "Taken from prescriptions exactly as written. Thought Medione never suggests changes.")
    meds = records.list_medications(ctx.uid, ctx.pid)
    if not meds:
        empty_state("No medicines recorded", "Medicines appear here when you add a prescription.",
                    "Add a prescription", go, ("Add record",), key="med_empty")
        return
    active = [m for m in meds if m["status"] == "active"]
    st.markdown(f"#### Current ({len(active)})")
    if not active:
        st.caption("No medicines marked as current.")
    for m in active:
        with st.container(border=True):
            flag = " " + badge("Needs checking", "orange") if m["uncertain"] else ""
            md(f"<b>{esc(m['name'])}</b> {esc(m['dosage'] or '')}{flag}<br>"
               f"<span class='tm-row-meta'>{esc(m['frequency'] or 'Frequency not recorded')}"
               f"{(' · ' + esc(m['instructions'])) if m['instructions'] else ''}"
               f"{(' · for ' + esc(m['duration'])) if m['duration'] else ''} · prescribed "
               f"{esc(fmt_date(m['prescribed_on']))}{(' by ' + esc(m['doctor_name'])) if m['doctor_name'] else ''}</span>")
            if m["uncertain"] and m["uncertain_note"]:
                st.caption(f"⚠ {m['uncertain_note']}")
            c1, c2, c3 = st.columns(3)
            if m["record_id"]:
                c1.button("Open prescription", key=f"med_open_{m['id']}", on_click=open_record, args=(m["record_id"],))
            c2.button("Set up a reminder", key=f"med_rem_{m['id']}", on_click=go, args=("Reminders",),
                      kwargs={"rem_from_med": m["id"]})
            with c3.popover("Update status"):
                st.caption("Record what has actually happened. Never stop a medicine without asking your doctor.")
                st.button("Course finished", key=f"med_done_{m['id']}", on_click=_set_status,
                          args=(ctx.uid, m["id"], "completed"))
                st.button("Stopped by my doctor", key=f"med_stop_{m['id']}", on_click=_set_status,
                          args=(ctx.uid, m["id"], "stopped"))
    past = [m for m in meds if m["status"] != "active"]
    st.markdown(f"#### History ({len(past)})")
    if past:
        df = pd.DataFrame([{"Medicine": m["name"], "Dose": m["dosage"], "How often": m["frequency"],
                            "Prescribed": m["prescribed_on"], "Ended": m["end_date"], "Status": m["status"].title(),
                            "Doctor": m["doctor_name"]} for m in past])
        st.dataframe(df, hide_index=True, width="stretch")
    else:
        st.caption("No past medicines recorded.")
    disclaimer()
