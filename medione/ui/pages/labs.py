"""Lab results compared across dates — only where units match."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go_
import streamlit as st

from medione.services import records, search
from medione.ui.state import Ctx, go, open_record
from medione.ui.widgets import badge, disclaimer, empty_state, fmt_date, md, page_header


def _chart(trend: dict) -> go_.Figure:
    rows = trend["results"]
    fig = go_.Figure()
    last = rows[-1]
    if last.get("ref_low") is not None or last.get("ref_high") is not None:
        lo = last.get("ref_low") if last.get("ref_low") is not None else min(r["value_num"] for r in rows) * 0.9
        hi = last.get("ref_high") if last.get("ref_high") is not None else max(r["value_num"] for r in rows) * 1.1
        fig.add_hrect(y0=lo, y1=hi, fillcolor="#0D9488", opacity=0.08, line_width=0,
                      annotation_text="Range on latest report", annotation_position="top left")
    fig.add_trace(go_.Scatter(x=[r["record_date"] for r in rows], y=[r["value_num"] for r in rows],
                              mode="lines+markers", line=dict(color="#2563EB", width=2), marker=dict(size=8),
                              hovertemplate="%{x}<br>%{y} " + (trend["unit"] or "") + "<extra></extra>"))
    fig.update_layout(height=260, margin=dict(l=10, r=10, t=30, b=10), showlegend=False,
                      yaxis_title=trend["unit"] or "", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#E2E8F0")
    return fig


def render(ctx: Ctx) -> None:
    page_header("Lab results", "Your test values over time, as printed on each report.")
    trends = search.lab_trends(records.list_lab_results(ctx.uid, ctx.pid))
    if not trends:
        empty_state("No test results yet", "Add a lab report and enter (or let the AI read) the values.",
                    "Add a lab report", go, ("Add record",), key="lab_empty")
        return
    st.caption("Shaded bands show the reference range printed on the most recent report. Values are only plotted "
               "together when every report uses the same unit. **This page describes how numbers changed — it is not "
               "a clinical interpretation.** Ask your doctor what the numbers mean for you.")
    for t in trends:
        latest = t["results"][-1]
        pos = latest.get("outside_report_range")
        tag = badge(f"Latest {pos} report range", "orange") if pos else ""
        with st.expander(f"{t['test_name']} — {len(t['results'])} result(s), latest "
                         f"{latest['value_text'] or latest['value_num']} {latest['unit'] or ''} "
                         f"({fmt_date(latest['record_date'])})", expanded=t["comparable"]):
            if tag:
                md(tag)
            if t["comparable"]:
                st.plotly_chart(_chart(t), width="stretch", key=f"lab_chart_{t['test_name']}",
                                config={"displayModeBar": False})
            elif t["reason"]:
                st.caption(t["reason"])
            rows = t["results"]
            table = []
            for i, r in enumerate(rows):
                prev = rows[i - 1] if i else None
                same_unit = prev is not None and (prev["unit"] or "").lower() == (r["unit"] or "").lower()
                change = ""
                if prev and same_unit and r["value_num"] is not None and prev["value_num"] is not None:
                    diff = r["value_num"] - prev["value_num"]
                    change = f"{'+' if diff > 0 else ''}{diff:g}"
                elif prev:
                    change = "Not comparable (different unit)" if not same_unit else "—"
                table.append({"Date": r["record_date"], "Result": r["value_text"] or r["value_num"], "Unit": r["unit"],
                              "Previous": (f"{prev['value_text'] or prev['value_num']} ({prev['record_date']})"
                                           if prev else "—"),
                              "Change": change, "Report range": r["ref_text"] or _rng(r),
                              "Compared with that range": {"above": "Above", "below": "Below"}.get(
                                  r["outside_report_range"] or "", ""),
                              "Source report": r["record_title"], "Lab": r["facility_name"],
                              "Needs checking": "Yes" if r["uncertain"] else ""})
            df = pd.DataFrame(list(reversed(table)))
            st.dataframe(df, hide_index=True, width="stretch")
            for r in reversed(t["results"]):
                st.button(f"Open report from {fmt_date(r['record_date'])}", key=f"lab_open_{r['id']}",
                          on_click=open_record, args=(r["record_id"],), type="tertiary")
    disclaimer()


def _rng(r: dict) -> str:
    lo, hi = r.get("ref_low"), r.get("ref_high")
    if lo is None and hi is None:
        return "Not printed"
    return f"{'' if lo is None else f'{lo:g}'} – {'' if hi is None else f'{hi:g}'}"
