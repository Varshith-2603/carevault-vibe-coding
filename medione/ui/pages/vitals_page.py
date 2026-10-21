"""Home readings: blood pressure, sugar, pulse, oxygen, temperature, weight."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go_
import streamlit as st

from medione.models import SUGAR_HIGH, VITAL_KINDS
from medione.services import health
from medione.ui.state import Ctx, flash
from medione.ui.widgets import badge, disclaimer, esc, fmt_date, md, page_header

PERIODS = {"30 days": 30, "90 days": 90, "1 year": 365, "All": None}


def _chart(rows: list[dict], kind: str) -> go_.Figure:
    spec = VITAL_KINDS[kind]
    fig = go_.Figure()
    x = [r["measured_on"] for r in rows]
    if kind == "bp":
        fig.add_hrect(y0=60, y1=89, fillcolor="#0EA5E9", opacity=0.06, line_width=0)
        fig.add_hrect(y0=90, y1=139, fillcolor="#0F766E", opacity=0.07, line_width=0)
        fig.add_trace(go_.Scatter(x=x, y=[r["value1"] for r in rows], name="Systolic (top)", mode="lines+markers",
                                  line=dict(color="#0F766E", width=2)))
        fig.add_trace(go_.Scatter(x=x, y=[r["value2"] for r in rows], name="Diastolic (bottom)", mode="lines+markers",
                                  line=dict(color="#0EA5E9", width=2)))
    else:
        if spec.low is not None or spec.high is not None:
            lo = spec.low if spec.low is not None else min(r["value1"] for r in rows)
            hi = spec.high if spec.high is not None else (SUGAR_HIGH["Fasting"] if kind == "sugar" else max(r["value1"] for r in rows))
            fig.add_hrect(y0=lo, y1=hi, fillcolor="#0F766E", opacity=0.07, line_width=0)
        fig.add_trace(go_.Scatter(x=x, y=[r["value1"] for r in rows], mode="lines+markers", name=spec.label,
                                  line=dict(color="#0F766E", width=2),
                                  marker=dict(color=["#DC2626" if r["flag"] else "#0F766E" for r in rows], size=7)))
    fig.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10), yaxis_title=spec.unit, legend=dict(orientation="h"),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig.update_yaxes(gridcolor="#D3E4E2")
    fig.update_xaxes(type="date", tickformat="%d %b", showgrid=False)
    return fig


def render(ctx: Ctx) -> None:
    page_header("Vitals", "Readings you take at home. Bring the trend to your next appointment.", "pulse")
    latest = health.latest_vitals(ctx.uid, ctx.pid)
    if latest:
        cols = st.columns(min(6, len(latest)))
        for col, v in zip(cols, latest):
            flag = v["latest"]["flag"]
            col.markdown(f'<div class="tm-tile" style="display:block"><div class="lbl">{esc(v["spec"].label)}</div>'
                         f'<div class="val" style="font-size:1.3rem">{esc(health.format_vital(v["latest"]))}</div>'
                         f'<div class="hint">{esc(fmt_date(v["latest"]["measured_on"]))} '
                         f'{badge("Check", "amber") if flag else ""}</div></div>', unsafe_allow_html=True)
        st.write("")

    with st.expander("Log a new reading", expanded=not latest, icon=":material/add_circle:"):
        kind = st.selectbox("What did you measure?", list(VITAL_KINDS), format_func=lambda k: VITAL_KINDS[k].label,
                            key="vit_kind")
        spec = VITAL_KINDS[kind]
        with st.form(f"vit_form_{kind}", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            if spec.two_values:
                v1 = c1.number_input("Top number (systolic)", min_value=0, max_value=300, value=None, step=1)
                v2 = c2.number_input("Bottom number (diastolic)", min_value=0, max_value=200, value=None, step=1)
            else:
                v1 = c1.number_input(f"Reading ({spec.unit})", min_value=0.0, max_value=1000.0, value=None, step=0.1,
                                     format="%g")
                v2 = None
            ctx_val = c2.selectbox("When", spec.contexts) if spec.contexts else None
            measured = c3.date_input("Date", value=date.today(), max_value=date.today(), format="DD/MM/YYYY")
            when = c3.time_input("Time", value=None, step=300)
            note = st.text_input("Note (optional)", placeholder="e.g. after walk, felt dizzy, missed dose")
            if st.form_submit_button("Save reading", type="primary"):
                try:
                    vid = health.save_vital(ctx.uid, ctx.pid, {"kind": kind, "value1": v1, "value2": v2, "context": ctx_val,
                                                               "measured_on": measured, "note": note,
                                                               "time_of_day": when.strftime("%H:%M") if when else None})
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    saved = [r for r in health.list_vitals(ctx.uid, ctx.pid, kind) if r["id"] == vid][0]
                    if saved["flag"]:
                        flash(f"Saved. This reading is {'above' if saved['flag'] == 'high' else 'below'} the general "
                              "reference range — consider mentioning it to your doctor, sooner if you feel unwell.", "warning")
                    else:
                        flash("Reading saved.")
                    st.rerun()
        st.caption(spec.reference or "Track the trend over time.")

    rows_all = health.list_vitals(ctx.uid, ctx.pid)
    if not rows_all:
        st.info("No readings yet. Regular home readings help your doctor see the full picture between visits.")
        disclaimer()
        return
    period = st.segmented_control("Show", list(PERIODS), default="90 days", key="vit_period", required=True)
    since = date.today() - timedelta(days=PERIODS[period]) if PERIODS[period] else None
    kinds = [k for k in VITAL_KINDS if any(r["kind"] == k for r in rows_all)]
    tabs = st.tabs([VITAL_KINDS[k].label for k in kinds])
    for tab, k in zip(tabs, kinds):
        with tab:
            rows = health.list_vitals(ctx.uid, ctx.pid, k, since)
            if not rows:
                st.caption("No readings in this period.")
                continue
            flagged = sum(1 for r in rows if r["flag"])
            md(f"<span class='tm-row-meta'>{len(rows)} readings · {flagged} outside the general range · "
               f"{esc(VITAL_KINDS[k].reference)}</span>")
            st.plotly_chart(_chart(rows, k), width="stretch", key=f"vit_chart_{k}", config={"displayModeBar": False})
            table = pd.DataFrame([{"Date": r["measured_on"], "Time": r["time_of_day"] or "",
                                   "Reading": health.format_vital(r), "When": r["context"] or "",
                                   "Flag": {"high": "Above range", "low": "Below range"}.get(r["flag"] or "", ""),
                                   "Note": r["note"] or ""} for r in reversed(rows)])
            st.dataframe(table, hide_index=True, width="stretch", height=min(320, 40 + 35 * len(rows)))
            with st.popover("Delete a reading", icon=":material/delete:"):
                options = {r["id"]: f"{r['measured_on']} {r['time_of_day'] or ''} — {health.format_vital(r)}"
                           for r in reversed(rows)}
                pick = st.selectbox("Reading", list(options), format_func=options.get, key=f"vit_del_pick_{k}")
                if st.button("Delete reading", key=f"vit_del_{k}"):
                    health.delete_vital(ctx.uid, pick)
                    flash("Reading deleted.", "info")
                    st.rerun()
    st.caption("Ranges shown are general adult references, not personal targets. Your doctor may set different "
               "targets for you. Highlighted readings are worth discussing — they are not a diagnosis.")
    disclaimer()
