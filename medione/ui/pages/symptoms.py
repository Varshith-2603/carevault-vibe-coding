"""Track health concerns and symptoms over time, to show a doctor how things have changed."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from medione.models import SEVERITY
from medione.services import health
from medione.ui.state import Ctx, flash
from medione.ui.widgets import badge, disclaimer, esc, fmt_date, md, page_header

SEV_TONE = {1: "teal", 2: "amber", 3: "red"}
TREND = {"worse": ("▲ getting worse", "red"), "better": ("▼ improving", "green"), "same": ("● no change", "gray"),
         "new": ("● new", "blue")}
RED_FLAGS = ("chest pain or pressure", "trouble breathing", "sudden weakness or numbness of face, arm or leg",
             "confusion or trouble speaking", "fainting", "severe bleeding", "a seizure")


def _resolve(uid: int, cid: int, resolved: bool) -> None:
    health.set_concern_status(uid, cid, resolved)
    flash("Marked as resolved." if resolved else "Moved back to active.")


def render(ctx: Ctx) -> None:
    page_header("Symptoms & concerns", "Note how you feel over time. Doctors find a symptom diary very useful.", "heart")
    md('<div class="tm-callout red"><b>Emergency?</b> Call <b>112</b> (or 108 for an ambulance) for '
       + ", ".join(RED_FLAGS) + ". Don't wait to log it here.</div>")
    st.write("")
    with st.expander("Add a new concern", expanded=bool(st.session_state.pop("conc_new_open", None)),
                     icon=":material/add_circle:"):
        with st.form("conc_new", clear_on_submit=True):
            c1, c2 = st.columns(2)
            title = c1.text_input("What's bothering you? *", placeholder="e.g. Headaches, Back pain, Cough")
            area = c2.text_input("Where (if relevant)", placeholder="e.g. Lower back, Left knee")
            c3, c4 = st.columns(2)
            started = c3.date_input("Started on", value=None, max_value=date.today(), format="DD/MM/YYYY")
            severity = c4.radio("How bad is it today?", list(SEVERITY), format_func=SEVERITY.get, horizontal=True)
            note = st.text_area("Details (what makes it better or worse, timing, triggers)", height=80)
            if st.form_submit_button("Start tracking", type="primary"):
                try:
                    health.save_concern(ctx.uid, ctx.pid, {"title": title, "body_area": area, "started_on": started,
                                                           "severity": severity, "notes": note})
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    flash("Concern added. Log how it feels every few days.")
                    st.rerun()

    concerns = health.list_concerns(ctx.uid, ctx.pid)
    active = [c for c in concerns if c["status"] == "active"]
    resolved = [c for c in concerns if c["status"] != "active"]
    st.markdown(f"#### Active ({len(active)})")
    if not active:
        st.caption("No active concerns. That's good news!")
    for c in active:
        trend_text, trend_tone = TREND[c["trend"]]
        with st.container(border=True):
            md(f'<div class="tm-row-title">{esc(c["title"])} {badge(SEVERITY[c["severity"]], SEV_TONE[c["severity"]])} '
               f'{badge(trend_text, trend_tone)}</div><div class="tm-row-meta">'
               f'{(esc(c["body_area"]) + " · ") if c["body_area"] else ""}since {esc(fmt_date(c["started_on"]))} · '
               f'{len(c["logs"])} update(s)</div>')
            if c["notes"]:
                st.caption(c["notes"])
            if c["severity"] >= 3:
                st.error("Marked severe. If it's getting worse quickly, contact a doctor today or call 112.")
            if len(c["logs"]) > 1:
                df = pd.DataFrame({"Date": [l["logged_on"] for l in c["logs"]], "Severity": [l["severity"] for l in c["logs"]]})
                st.line_chart(df, x="Date", y="Severity", height=140, color="#0F766E")
            with st.expander("Diary"):
                for l in reversed(c["logs"]):
                    md(f"{badge(SEVERITY[l['severity']], SEV_TONE[l['severity']])} <b>{esc(fmt_date(l['logged_on']))}</b>"
                       f"{(' — ' + esc(l['note'])) if l['note'] else ''}")
            c1, c2, c3 = st.columns([3, 1, 1])
            with c1.popover("Log how it is today", icon=":material/edit_note:"):
                with st.form(f"conc_log_{c['id']}", clear_on_submit=True):
                    sev = st.radio("Severity", list(SEVERITY), format_func=SEVERITY.get, horizontal=True,
                                   index=c["severity"] - 1)
                    n = st.text_input("Note")
                    if st.form_submit_button("Save", type="primary"):
                        health.log_concern(ctx.uid, c["id"], sev, n)
                        flash("Logged.")
                        st.rerun()
            c2.button("Resolved", key=f"conc_res_{c['id']}", on_click=_resolve, args=(ctx.uid, c["id"], True),
                      icon=":material/check_circle:")
            with c3.popover("Delete", icon=":material/delete:"):
                if st.checkbox("Confirm", key=f"conc_del_ok_{c['id']}"):
                    if st.button("Delete", key=f"conc_del_{c['id']}"):
                        health.delete_concern(ctx.uid, c["id"])
                        flash("Deleted.", "info")
                        st.rerun()
    if resolved:
        with st.expander(f"Resolved ({len(resolved)})"):
            for c in resolved:
                c1, c2 = st.columns([4, 1])
                c1.markdown(f"**{c['title']}** — resolved {fmt_date(c['resolved_on'])}")
                c2.button("Reopen", key=f"conc_reopen_{c['id']}", on_click=_resolve, args=(ctx.uid, c["id"], False))
    disclaimer()
