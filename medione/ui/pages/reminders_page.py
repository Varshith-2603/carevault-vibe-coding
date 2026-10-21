"""Reminders the user creates; exported to the phone calendar for real notifications."""
from __future__ import annotations

from datetime import date, time

import streamlit as st

from medione.models import REMINDER_KINDS, REPEATS
from medione.services import records, reminders, search
from medione.ui.state import Ctx, flash, open_record
from medione.ui.widgets import badge, disclaimer, esc, fmt_date, md, page_header


def _prefill(ctx: Ctx) -> dict:
    """Start from a record or medicine, copying only what is written there."""
    rid = st.session_state.pop("rem_from_record", None)
    mid = st.session_state.pop("rem_from_med", None)
    if mid:
        med = next((m for m in records.list_medications(ctx.uid, ctx.pid) if m["id"] == mid), None)
        if med:
            return {"kind": "medication", "title": f"{med['name']} {med['dosage'] or ''}".strip(),
                    "notes": "As written: " + ", ".join(x for x in (med["frequency"], med["instructions"], med["duration"]) if x),
                    "source_record_id": med["record_id"], "hint": med["frequency"]}
    if rid:
        rec = records.get_record(ctx.uid, rid)
        if rec["profile_id"] == ctx.pid:
            if rec["follow_up_date"]:
                return {"kind": "appointment", "title": f"Follow-up: {rec['title']}", "due_date": rec["follow_up_date"],
                        "source_record_id": rid}
            if rec["medications"]:
                m = rec["medications"][0]
                return {"kind": "medication", "title": f"{m['name']} {m['dosage'] or ''}".strip(),
                        "notes": "As written: " + ", ".join(x for x in (m["frequency"], m["instructions"]) if x),
                        "source_record_id": rid, "hint": m["frequency"]}
    return st.session_state.get("rem_prefill", {})


def _form(ctx: Ctx, pre: dict, key: str = "rem_form", reminder_id: int | None = None) -> None:
    linkable = {"— None —": None, **{f"{fmt_date(r['record_date'])} · {r['title']}": r["id"]
                                    for r in search.search_records(ctx.uid, ctx.pid)}}
    link_label = next((k for k, v in linkable.items() if v == pre.get("source_record_id") and v), "— None —")
    if pre.get("hint"):
        st.info(f"The prescription says: “{pre['hint']}”. Choose the times yourself — Thought Medione doesn't "
                "work out dosing schedules. If you're unsure, check with your doctor or pharmacist.")
    with st.form(key, clear_on_submit=reminder_id is None):
        kinds = list(REMINDER_KINDS)
        c1, c2 = st.columns(2)
        kind = c1.selectbox("For", kinds, index=kinds.index(pre.get("kind", "medication")), format_func=REMINDER_KINDS.get)
        title = c2.text_input("Title *", value=pre.get("title", ""), max_chars=120)
        c3, c4, c5 = st.columns(3)
        due_default = date.fromisoformat(pre["due_date"]) if pre.get("due_date") else date.today()
        due = c3.date_input("Date (first date if repeating) *", value=due_default, format="DD/MM/YYYY")
        use_time = c4.checkbox("At a set time", value=bool(pre.get("time_of_day")) if reminder_id else kind == "medication")
        at = c4.time_input("Time", value=time.fromisoformat(pre["time_of_day"]) if pre.get("time_of_day") else time(9, 0),
                           step=300)
        repeats = list(REPEATS)
        repeat = c5.selectbox("Repeat", repeats, index=repeats.index(pre.get("repeat") or "none"), format_func=REPEATS.get)
        until = c5.date_input("Until (optional)", value=date.fromisoformat(pre["until_date"]) if pre.get("until_date")
                              else None, format="DD/MM/YYYY")
        link = st.selectbox("Linked record", list(linkable), index=list(linkable).index(link_label))
        notes = st.text_area("Notes", value=pre.get("notes") or "", height=70)
        if st.form_submit_button("Save changes" if reminder_id else "Save reminder", type="primary"):
            try:
                reminders.save_reminder(ctx.uid, ctx.pid, {
                    "kind": kind, "title": title, "due_date": due, "time_of_day": at.strftime("%H:%M") if use_time else "",
                    "repeat": repeat, "until_date": until, "source_record_id": linkable[link], "notes": notes},
                    reminder_id)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state.pop("rem_prefill", None)
                flash("Reminder updated." if reminder_id else "Reminder saved.")
                st.rerun()


def _act(fn, *args, msg: str = "") -> None:
    fn(*args)
    if msg:
        flash(msg)


def render(ctx: Ctx) -> None:
    page_header("Reminders", "Reminders you set up for medicines, follow-ups, tests and vaccinations.")
    st.caption("Reminders show here and on the Dashboard when you open the app. For phone notifications, download them to your "
               "calendar. A reminder is not medical advice — it only repeats what you entered.")
    pre = _prefill(ctx)
    if pre:
        st.session_state["rem_prefill"] = pre
    with st.expander("New reminder", expanded=bool(pre), icon=":material/add_alarm:"):
        _form(ctx, pre)
    items = reminders.list_reminders(ctx.uid, ctx.pid)
    if not items:
        st.caption("No reminders yet.")
        return
    st.download_button("Add all to my calendar (.ics)", reminders.to_ics(items), "thought-medione-reminders.ics",
                       "text/calendar", key="rem_ics", icon=":material/event:")
    for r in items:
        with st.container(border=True):
            c1, c2 = st.columns([4, 2], vertical_alignment="center")
            with c1:
                if not r["active"]:
                    state = badge("Paused", "gray")
                elif r["next_due"] is None:
                    state = badge("Done" if r["last_done_on"] else "Finished", "green")
                elif r["overdue"]:
                    state = badge(f"Overdue · {fmt_date(r['next_due'])}", "red")
                elif r["due_today"]:
                    state = badge("Due today", "orange")
                else:
                    state = badge(f"Next: {fmt_date(r['next_due'])}", "blue")
                md(f"<b>{esc(r['title'])}</b> {state}<br><span class='tm-row-meta'>{esc(REMINDER_KINDS[r['kind']])} · "
                   f"{esc(REPEATS[r['repeat']])}{(' at ' + esc(r['time_of_day'])) if r['time_of_day'] else ''}"
                   f"{(' · until ' + esc(fmt_date(r['until_date']))) if r['until_date'] else ''}"
                   f"{(' · last done ' + esc(fmt_date(r['last_done_on']))) if r['last_done_on'] else ''}</span>")
                if r["notes"]:
                    st.caption(r["notes"])
                with st.expander("Edit reminder", icon=":material/edit:"):
                    _form(ctx, r, key=f"rem_edit_{r['id']}", reminder_id=r["id"])
            with c2:
                b1, b2, b3 = st.columns(3)
                if r["active"] and r["next_due"] and r["next_due"] <= date.today().isoformat():
                    b1.button("Done", key=f"rem_done_{r['id']}", on_click=_act,
                              args=(reminders.mark_done, ctx.uid, r["id"]), kwargs={"msg": "Marked as done."})
                b2.button("Resume" if not r["active"] else "Pause", key=f"rem_pause_{r['id']}", on_click=_act,
                          args=(reminders.set_active, ctx.uid, r["id"], not r["active"]))
                with b3.popover("⋯"):
                    if r["source_record_id"]:
                        st.button("Open linked record", key=f"rem_open_{r['id']}", on_click=open_record,
                                  args=(r["source_record_id"],))
                    sure = st.checkbox("Confirm delete", key=f"rem_del_ok_{r['id']}")
                    st.button("Delete reminder", key=f"rem_del_{r['id']}", on_click=_act, disabled=not sure,
                              args=(reminders.delete_reminder, ctx.uid, r["id"]), kwargs={"msg": "Reminder deleted."})
    disclaimer()
