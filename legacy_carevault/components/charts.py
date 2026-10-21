from datetime import date, timedelta
from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from components.ui import html_block
from utils.data_loader import past_records_only
from utils.helpers import format_date

FONT = "Inter, -apple-system, 'Segoe UI', sans-serif"
BLUE, TEAL, SLATE = "#2563EB", "#0D9488", "#64748B"

VITAL_METRICS = {
    "Heart rate": {"cols": [("heart_rate", "Heart rate", BLUE)], "unit": "bpm", "fmt": "{:.0f}",
                   "ref": (60, 100, "General adult resting range 60–100 bpm")},
    "Blood pressure": {"cols": [("systolic_bp", "Systolic (top)", BLUE), ("diastolic_bp", "Diastolic (bottom)", TEAL)],
                       "unit": "mmHg", "fmt": "{:.0f}", "ref": None},
    "Weight": {"cols": [("weight_kg", "Weight", TEAL)], "unit": "kg", "fmt": "{:.1f}", "ref": None},
    "Blood oxygen": {"cols": [("spo2", "SpO₂", BLUE)], "unit": "%", "fmt": "{:.0f}",
                     "ref": (95, 100, "General adult range 95–100%")},
}
RANGES = {"1 month": 31, "3 months": 92, "6 months": 183, "All": None}


def _base_layout(fig: go.Figure, height: int = 300):
    fig.update_layout(
        margin=dict(l=4, r=8, t=8, b=4),
        height=height,
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        font=dict(family=FONT, color="#172033", size=12),
        xaxis=dict(showgrid=False, linecolor="#E2E8F0", tickfont=dict(size=11, color=SLATE), fixedrange=True),
        yaxis=dict(showgrid=True, gridcolor="#EEF2F7", zeroline=False, tickfont=dict(size=11, color=SLATE), fixedrange=True),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, font=dict(size=11, color="#334155")),
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor="#E2E8F0", font=dict(family=FONT, size=12, color="#172033")),
        hovermode="x unified",
    )


def _latest_pair(df: pd.DataFrame, col: str):
    s = df[["date", col]].dropna().sort_values("date")
    if s.empty:
        return None, None
    latest = s.iloc[-1]
    prev = s.iloc[-2] if len(s) > 1 else None
    return latest, prev


def render_vital_summary(df: pd.DataFrame, metric: str):
    """Latest reading, the one before it, and the change — no interpretation."""
    spec = VITAL_METRICS[metric]
    cells = []
    if metric == "Blood pressure":
        s = df[["date", "systolic_bp", "diastolic_bp"]].dropna().sort_values("date")
        if s.empty:
            html_block('<div class="cv-empty-inline">No blood pressure readings recorded in this period.</div>')
            return
        last = s.iloc[-1]
        cells.append(("Latest reading", f"{last['systolic_bp']:.0f}/{last['diastolic_bp']:.0f} mmHg", f"on {format_date(last['date'])}"))
        if len(s) > 1:
            prev = s.iloc[-2]
            cells.append(("Previous reading", f"{prev['systolic_bp']:.0f}/{prev['diastolic_bp']:.0f} mmHg", f"on {format_date(prev['date'])}"))
    else:
        col = spec["cols"][0][0]
        latest, prev = _latest_pair(df, col)
        if latest is None:
            html_block(f'<div class="cv-empty-inline">No {metric.lower()} readings recorded in this period.</div>')
            return
        fmt, unit = spec["fmt"], spec["unit"]
        cells.append(("Latest reading", f"{fmt.format(latest[col])} {unit}", f"on {format_date(latest['date'])}"))
        if prev is not None:
            cells.append(("Previous reading", f"{fmt.format(prev[col])} {unit}", f"on {format_date(prev['date'])}"))
            diff = latest[col] - prev[col]
            arrow = "▲" if diff > 0 else ("▼" if diff < 0 else "■")
            word = "higher" if diff > 0 else ("lower" if diff < 0 else "no change")
            change = f"{arrow} {fmt.format(abs(diff))} {unit}" if diff else "■ Same"
            cells.append(("Change", change, f"{word} than previous" if diff else "as previous"))
    cells.append(("Readings shown", str(len(df[[c for c, _, _ in spec["cols"]]].dropna(how="all"))), "in selected period"))
    html_block('<div class="cv-vital-summary">' + "".join(
        f'<div class="cv-vital-cell"><div class="cv-vital-label">{a}</div><div class="cv-vital-value">{b}</div>'
        f'<div class="cv-vital-sub">{c}</div></div>' for a, b, c in cells) + "</div>")


def render_vitals_chart(df_vitals: pd.DataFrame, key: str = "vitals", height: int = 300, show_summary: bool = True,
                        compact: bool = False):
    """Interactive vitals chart: metric selector, period selector, reference ranges and latest values."""
    metric = st.segmented_control("Measurement", list(VITAL_METRICS), default="Heart rate", required=True,
                                  key=f"{key}_metric", persist_state="session", width="stretch")
    period = st.segmented_control("Time period", list(RANGES), default="All", required=True,
                                  key=f"{key}_period", persist_state="session") or "All"
    metric = metric or "Heart rate"
    spec = VITAL_METRICS[metric]

    total = len(df_vitals)
    df = past_records_only(df_vitals).copy()
    future_n = total - len(df)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")
    days = RANGES.get(period)
    if days and not df.empty:
        df = df[df["date"] >= pd.Timestamp(date.today() - timedelta(days=days))]

    if show_summary:
        render_vital_summary(df.assign(date=df["date"].dt.date.astype(str)), metric)

    plot_cols = [c for c, _, _ in spec["cols"]]
    if df[plot_cols].dropna(how="all").empty:
        html_block(f'<div class="empty-state-box"><div class="empty-state-title">No {metric.lower()} readings</div>'
                   f'<div class="empty-state-text">Nothing was recorded for this period. Try a longer period or add a reading.</div></div>')
    else:
        fig = go.Figure()
        ref = spec["ref"]
        show_ref = st.session_state.get(f"{key}_ref", True)
        if ref and show_ref:
            fig.add_hrect(y0=ref[0], y1=ref[1], fillcolor="#ECFDF5", opacity=0.6, layer="below", line_width=0)
        if metric == "Blood pressure" and show_ref:
            for y, txt in ((120, "120"), (80, "80")):
                fig.add_hline(y=y, line=dict(color="#94A3B8", width=1, dash="dot"),
                              annotation_text=f"{txt} mmHg reference", annotation_position="top left",
                              annotation_font=dict(size=10, color=SLATE))
        for col, name, color in spec["cols"]:
            s = df[["date", col]].dropna()
            fig.add_trace(go.Scatter(
                x=s["date"], y=s[col], mode="lines+markers", name=name,
                line=dict(color=color, width=2.5), marker=dict(size=7, color=color, line=dict(color="#FFFFFF", width=1.5)),
                hovertemplate=f"{name}: %{{y}} {spec['unit']}<extra></extra>",
            ))
        _base_layout(fig, height)
        fig.update_layout(yaxis_title=f"{metric} ({spec['unit']})", showlegend=len(spec["cols"]) > 1)
        fig.update_xaxes(tickformat="%d %b", hoverformat="%d %b %Y")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False, "responsive": True}, key=f"{key}_chart")

    notes = []
    if spec["ref"] or metric == "Blood pressure":
        notes.append("Shaded band / dotted lines show general adult reference values, not personal targets.")
    if future_n:
        notes.append(f"{future_n} reading{'s are' if future_n != 1 else ' is'} dated after today and not shown.")
    notes.append("Readings are as recorded. Ask a healthcare professional what they mean for you.")
    c_note, c_toggle = st.columns([4, 1.4], vertical_alignment="center")
    with c_note:
        st.caption(" ".join(notes))
    with c_toggle:
        if spec["ref"] or metric == "Blood pressure":
            st.toggle("Reference", value=True, key=f"{key}_ref", help="Show or hide general reference values")


def render_department_visits_chart(visits_df: pd.DataFrame):
    """Horizontal bar chart of visits by department."""
    if visits_df.empty:
        st.caption("No visits to chart.")
        return
    dept_counts = visits_df["department"].replace("", "Not recorded").value_counts().reset_index()
    dept_counts.columns = ["Department", "Visits"]
    fig = px.bar(dept_counts, x="Visits", y="Department", orientation="h", text="Visits",
                 color_discrete_sequence=[BLUE])
    _base_layout(fig, max(180, 34 * len(dept_counts) + 40))
    fig.update_traces(textposition="outside", cliponaxis=False, hovertemplate="%{y}: %{x} visit(s)<extra></extra>")
    fig.update_layout(xaxis=dict(dtick=1, showgrid=True, gridcolor="#EEF2F7"), yaxis=dict(autorange="reversed", showgrid=False),
                      hovermode="closest")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key="dept_chart")


def render_diagnostics_category_chart(diag_df: pd.DataFrame):
    """Bar chart of diagnostic reports by category."""
    if diag_df.empty:
        st.caption("No reports to chart.")
        return
    cat_counts = diag_df["category"].replace("", "Not recorded").value_counts().reset_index()
    cat_counts.columns = ["Category", "Reports"]
    fig = px.bar(cat_counts, x="Reports", y="Category", orientation="h", text="Reports",
                 color_discrete_sequence=[TEAL])
    _base_layout(fig, max(160, 40 * len(cat_counts) + 40))
    fig.update_traces(textposition="outside", cliponaxis=False, hovertemplate="%{y}: %{x} report(s)<extra></extra>")
    fig.update_layout(xaxis=dict(dtick=2, showgrid=True, gridcolor="#EEF2F7"), yaxis=dict(autorange="reversed", showgrid=False),
                      hovermode="closest")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key="diag_cat_chart")
