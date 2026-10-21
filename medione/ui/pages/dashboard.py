"""Dashboard: the first screen after sign-in. Appointments, pending to-dos, health watch, today's reminders."""
from __future__ import annotations

from datetime import datetime

import plotly.graph_objects as go_
import streamlit as st
import streamlit.components.v1 as components

from medione.models import APPOINTMENT_KINDS, SEVERITY
from medione.services import dashboard, health, reminders, search, summary, visit_prep
from medione.ui.state import Ctx, flash, go, open_record
from medione.ui.widgets import (badge, date_block, disclaimer, empty_state, esc, fmt_date, md, record_row, section,
                                tile)

TONE_DOT = {"amber": "dot-amber", "red": "dot-red", "blue": "dot-blue", "gray": "dot-gray"}
SEV_TONE = {1: "teal", 2: "amber", 3: "red"}
TREND = {"worse": ("▲ getting worse", "red"), "better": ("▼ improving", "green"), "same": ("● no change", "gray"),
         "new": ("● new", "blue")}


def _greeting() -> str:
    h = datetime.now().hour
    return "Good morning" if h < 12 else "Good afternoon" if h < 17 else "Good evening"


def _done(uid: int, rid: int) -> None:
    reminders.mark_done(uid, rid)
    flash("Marked as done.")


def _dismiss(uid: int, pid: int, key: str) -> None:
    _, a, b = key.split("_")
    search.dismiss_duplicate(uid, pid, int(a), int(b))
    flash("Okay — these won't be flagged again.", "info")


def _hero(ctx: Ctx, d: dict) -> None:
    p = ctx.profile
    is_self = p["relationship"] == "self"
    title = f"{_greeting()}, {ctx.user.display_name}" if is_self else f"{p['full_name']}'s health"
    who = "Here's what needs your attention today." if is_self else \
        f"You're viewing the {p['relationship']} profile you manage."
    allergies = ", ".join(d["allergies"]) or "None recorded"
    conds = ", ".join(d["conditions"]) or "None recorded"
    md(f"""<div class="tm-hero"><div style="z-index:1"><div class="date">{d['today'].strftime('%A, %d %B %Y')}</div>
<h1>{esc(title)}</h1><div class="who">{esc(who)}</div></div>
<div class="facts"><div class="tm-chip"><b>Blood group</b>{esc(p['blood_group'] or 'Not recorded')}</div>
<div class="tm-chip {'alert' if d['allergies'] else ''}"><b>Allergies</b>{esc(allergies)}</div>
<div class="tm-chip"><b>Conditions</b>{esc(conds)}</div></div></div>""")


def _quick_actions() -> None:
    cols = st.columns(5)
    actions = [("Upload a record", ":material/upload_file:", "Add record", {}),
               ("Book appointment", ":material/event_available:", "Appointments", {"appt_new_open": True}),
               ("Log a symptom", ":material/sick:", "Symptoms", {"conc_new_open": True}),
               ("Log a reading", ":material/monitor_heart:", "Vitals", {}),
               ("Emergency card", ":material/emergency:", "Emergency card", {})]
    for col, (label, icon, page, extra) in zip(cols, actions):
        col.button(label, icon=icon, key=f"qa_{page}", on_click=go, args=(page,), kwargs=extra, width="stretch")


def _tiles(d: dict) -> None:
    nxt = d["next_appointments"][0] if d["next_appointments"] else None
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(tile("Upcoming appointments", d["upcoming_count"],
                     f"Next: {fmt_date(nxt['starts_on'])}" if nxt else "Nothing booked", "calendar", "teal"),
                unsafe_allow_html=True)
    pending = len(d["todos"])
    c2.markdown(tile("Pending for you", pending, "All caught up" if not pending else "See the list below",
                     "clipboard", "amber" if pending else "teal"), unsafe_allow_html=True)
    active = len(d["concerns"])
    c3.markdown(tile("Health concerns", active,
                     "None active" if not active else ("Includes a severe one" if d["severe_concern"] else "Being tracked"),
                     "heart", "red" if d["severe_concern"] else "violet" if active else "teal"), unsafe_allow_html=True)
    c4.markdown(tile("Current medicines", len(d["medicines"]), f"{len(d['due_today'])} reminder(s) due today",
                     "pill", "blue"), unsafe_allow_html=True)


def _appointments(ctx: Ctx, d: dict) -> None:
    with st.container(border=True):
        section("Upcoming appointments", "calendar", d["upcoming_count"])
        if not d["next_appointments"]:
            st.caption("No appointments booked.")
            st.button("Book an appointment", key="dash_book", on_click=go, args=("Appointments",),
                      kwargs={"appt_new_open": True}, icon=":material/add:")
            return
        for a in d["next_appointments"]:
            when = "Today" if a["days_away"] == 0 else "Tomorrow" if a["days_away"] == 1 else f"In {a['days_away']} days"
            who = " · ".join(esc(x) for x in (a["doctor_name"], a["facility_name"]) if x)
            c1, c2 = st.columns([5, 2], vertical_alignment="center")
            c1.markdown(f'<div class="tm-appt">{date_block(a["starts_on"])}<div><div class="tm-row-title">{esc(a["purpose"])}</div>'
                        f'<div class="tm-row-meta">{badge(when, "teal" if a["days_away"] > 1 else "amber")} '
                        f'{esc(a["time_of_day"] or "")} · {esc(APPOINTMENT_KINDS.get(a["kind"], ""))}'
                        f'{("<br>" + who) if who else ""}</div></div></div>', unsafe_allow_html=True)
            c2.download_button("Visit sheet", visit_prep.visit_prep_html(ctx.uid, a["id"]),
                               f"visit-prep-{a['starts_on']}.html", "text/html", key=f"dash_prep_{a['id']}",
                               icon=":material/assignment:", width="stretch",
                               help="One page with your questions, symptoms, medicines and readings to take along.")
        st.button("All appointments", key="dash_all_appts", on_click=go, args=("Appointments",), type="tertiary")


def _today(ctx: Ctx, d: dict) -> None:
    with st.container(border=True):
        section("Today's reminders", "bell", len(d["due_today"]))
        if not d["due_today"]:
            st.caption("Nothing due today. 🎉")
        for r in d["due_today"]:
            c1, c2 = st.columns([3, 1.4], vertical_alignment="center")
            late = badge("Overdue", "red") if r["overdue"] else badge(r["time_of_day"] or "Today", "teal")
            c1.markdown(f'<div class="tm-row-title">{esc(r["title"])}</div><div class="tm-row-meta">{late}</div>',
                        unsafe_allow_html=True)
            c2.button("Done", key=f"dash_done_{r['id']}", on_click=_done, args=(ctx.uid, r["id"]), width="stretch")
        st.button("All reminders", key="dash_rem", on_click=go, args=("Reminders",), type="tertiary")


def _todos(ctx: Ctx, d: dict) -> None:
    with st.container(border=True):
        section("Pending for you", "clipboard", len(d["todos"]))
        if not d["todos"]:
            st.caption("All caught up — nothing pending.")
        for t in d["todos"][:8]:
            c1, c2 = st.columns([4, 1.3], vertical_alignment="center")
            c1.markdown(f'<div class="tm-todo"><span class="dot {TONE_DOT.get(t["tone"], "dot-amber")}"></span><div>'
                        f'<div class="tm-row-title">{esc(t["title"])}</div><div class="tm-row-meta">{esc(t["detail"])}</div>'
                        f'</div></div>', unsafe_allow_html=True)
            if t["kind"] == "duplicate":
                with c2.popover("Review", width="stretch"):
                    st.button("Open record", key=f"td_open_{t['key']}", on_click=open_record, args=(t["record_id"],))
                    st.button("They're different", key=f"td_dismiss_{t['key']}", on_click=_dismiss,
                              args=(ctx.uid, ctx.pid, t["key"]))
            elif t["record_id"]:
                c2.button("Open", key=f"td_{t['key']}", on_click=open_record, args=(t["record_id"],), width="stretch")
            elif t["page"]:
                c2.button("Go", key=f"td_{t['key']}", on_click=go, args=(t["page"],), width="stretch")
        if len(d["todos"]) > 8:
            st.caption(f"+ {len(d['todos']) - 8} more")


def _health_watch(ctx: Ctx, d: dict) -> None:
    with st.container(border=True):
        section("Health watch", "heart")
        if d["severe_concern"]:
            md('<div class="tm-callout red"><b>A concern is marked severe.</b> If it is sudden or getting worse quickly '
               '— for example chest pain, trouble breathing, fainting or confusion — call <b>112</b> or go to the '
               'nearest emergency department.</div>')
        if not (d["concerns"] or d["flagged_vitals"] or d["lab_flags"]):
            st.caption("No active concerns or readings to watch.")
        for c in d["concerns"]:
            trend_text, trend_tone = TREND[c["trend"]]
            md(f'<div class="tm-row-title">{esc(c["title"])} {badge(SEVERITY[c["severity"]], SEV_TONE[c["severity"]])} '
               f'{badge(trend_text, trend_tone)}</div><div class="tm-row-meta">Since {esc(fmt_date(c["started_on"]))} · '
               f'last logged {esc(fmt_date(c["last_logged"]))}</div>')
        for v in d["flagged_vitals"]:
            spec, last = v["spec"], v["latest"]
            md(f'<div class="tm-row-title">{esc(spec.label)}: {esc(health.format_vital(last))} '
               f'{badge(("Above" if last["flag"] == "high" else "Below") + " general range", "amber")}</div>'
               f'<div class="tm-row-meta">Measured {esc(fmt_date(last["measured_on"]))}. Worth mentioning to your doctor.</div>')
        for l in d["lab_flags"][:4]:
            md(f'<div class="tm-row-title">{esc(l["test_name"])}: {esc(l["value_text"] or l["value_num"])} {esc(l["unit"] or "")} '
               f'{badge(l["direction"].title() + " report range", "amber")}</div>'
               f'<div class="tm-row-meta">Lab report of {esc(fmt_date(l["record_date"]))}.</div>')
        c1, c2 = st.columns(2)
        c1.button("Track symptoms", key="dash_conc", on_click=go, args=("Symptoms",), type="tertiary")
        c2.button("Lab results", key="dash_labs", on_click=go, args=("Lab results",), type="tertiary")


def _spark(series: list[dict], two: bool) -> go_.Figure:
    fig = go_.Figure()
    x = [s["measured_on"] for s in series]
    fig.add_trace(go_.Scatter(x=x, y=[s["value1"] for s in series], mode="lines", line=dict(color="#0F766E", width=2),
                              hoverinfo="skip"))
    if two:
        fig.add_trace(go_.Scatter(x=x, y=[s["value2"] for s in series], mode="lines", line=dict(color="#0EA5E9", width=2),
                                  hoverinfo="skip"))
    fig.update_layout(height=60, margin=dict(l=0, r=0, t=4, b=0), showlegend=False, xaxis=dict(visible=False),
                      yaxis=dict(visible=False), plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    return fig


def _vitals(ctx: Ctx, d: dict) -> None:
    with st.container(border=True):
        section("Latest readings", "pulse")
        if not d["vitals"]:
            st.caption("No home readings yet. Log blood pressure, sugar, weight and more.")
        cols = st.columns(max(1, min(4, len(d["vitals"]))))
        for col, v in zip(cols, d["vitals"][:4]):
            with col:
                last, prev = v["latest"], v["previous"]
                change = ""
                if prev:
                    delta = last["value1"] - prev["value1"]
                    change = f"{'▲' if delta > 0 else '▼' if delta < 0 else '●'} {abs(delta):g} vs previous"
                flag = badge("Check", "amber") if last["flag"] else ""
                md(f'<div class="tm-row-meta">{esc(v["spec"].label)}</div><div class="tm-row-title" style="font-size:1.15rem">'
                   f'{esc(health.format_vital(last))} {flag}</div><div class="tm-row-meta">{esc(fmt_date(last["measured_on"]))}'
                   f'{(" · " + esc(change)) if change else ""}</div>')
                if len(v["series"]) > 2:
                    st.plotly_chart(_spark(v["series"], v["spec"].two_values), width="stretch",
                                    key=f"spark_{v['kind']}", config={"displayModeBar": False, "staticPlot": True})
        st.button("Log a reading", key="dash_vitals", on_click=go, args=("Vitals",), type="tertiary",
                  icon=":material/add:")


def _medicines(d: dict) -> None:
    with st.container(border=True):
        section("Current medicines", "pill", len(d["medicines"]))
        if not d["medicines"]:
            st.caption("No current medicines recorded.")
        for m in d["medicines"]:
            flag = " " + badge("Needs checking", "amber") if m["uncertain"] else ""
            md(f'<div class="tm-row-title">{esc(m["name"])} <span class="tm-row-meta">{esc(m["dosage"] or "")}</span>{flag}</div>'
               f'<div class="tm-row-meta">{esc(m["frequency"] or "Frequency not recorded")}</div>')
        st.button("All medicines", key="dash_meds", on_click=go, args=("Medicines",), type="tertiary")


@st.dialog("Health summary — review before downloading", width="large")
def _summary_dialog(ctx: Ctx, s: dict) -> None:
    html = summary.summary_html(s)
    st.caption("Check the summary below. It lists only what your records say — nothing is interpreted. If something "
               "is wrong, fix the record first, then come back.")
    if s["unreviewed_ai"]:
        st.warning(f"{s['unreviewed_ai']} record(s) read by AI haven't been checked yet. They are marked in the summary.")
    components.html(html, height=520, scrolling=True)
    st.download_button("Download summary (HTML — print or save as PDF)", html,
                       f"medical-summary-{ctx.profile['full_name'].replace(' ', '-').lower()}.html", "text/html",
                       key="dash_summary_dl", icon=":material/download:", type="primary")


def render(ctx: Ctx) -> None:
    d = dashboard.build(ctx.uid, ctx.pid)
    _hero(ctx, d)
    st.write("")
    _quick_actions()
    if d["record_count"] == 0 and not d["vitals"] and not d["next_appointments"] and not d["concerns"]:
        st.write("")
        empty_state("Let's set up your health record",
                    "Upload a prescription or report, book an appointment, or log a reading — the dashboard fills up "
                    "as you go.", "Upload the first record", go, ("Add record",), key="dash_empty")
        disclaimer()
        return
    st.write("")
    _tiles(d)
    st.write("")
    left, right = st.columns([7, 5])
    with left:
        _appointments(ctx, d)
        _todos(ctx, d)
    with right:
        _today(ctx, d)
        _health_watch(ctx, d)
    left, right = st.columns([7, 5])
    with left:
        _vitals(ctx, d)
    with right:
        _medicines(d)
    with st.container(border=True):
        section("Recent records", "folder")
        for r in d["recent"]:
            record_row(r, "dash_recent")
        c1, c2, c3 = st.columns(3)
        c1.button("Open timeline", on_click=go, args=("Timeline",), key="dash_tl", icon=":material/timeline:")
        if c3.button("Health summary (for a doctor)", key="dash_summary", icon=":material/summarize:",
                     help="Preview a factual one-page summary built from your records, then download it. No AI is used."):
            _summary_dialog(ctx, d["summary"])
    disclaimer()
