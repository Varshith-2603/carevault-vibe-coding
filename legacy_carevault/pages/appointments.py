from datetime import date

import streamlit as st

from components.filters import Select, apply_sort, filter_panel, options_from
from components.header import render_top_header
from components.page import list_toolbar, render_results
from components.ui import stat_card, stat_grid
from utils.data_loader import get_appointments, upcoming_appointments
from utils.filters import filter_appointments
from utils.helpers import esc, format_date, parse_date, relative_day, render_disclaimer

TABS = ["Upcoming", "Past", "Cancelled", "All"]


def render_appointments_page():
    render_top_header(
        title="Appointments",
        subtitle="Keep track of upcoming and past appointments.",
        add_kind="appointment",
    )
    df = get_appointments()
    upcoming = upcoming_appointments()
    nxt = upcoming.iloc[0] if not upcoming.empty else None

    with stat_grid("appointments"):
        stat_card("apt_up", "Upcoming", len(upcoming), "Scheduled from today onward", "calendar", "blue")
        stat_card("apt_next", "Next appointment", format_date(nxt["date"]) if nxt is not None else "None",
                  f"{esc(nxt['doctor'])} · {esc(relative_day(nxt['date']))}" if nxt is not None else "Nothing scheduled",
                  "clock", "teal")
        stat_card("apt_done", "Completed", int((df["status"] == "Completed").sum()), "Marked as completed", "history", "slate")
        stat_card("apt_cancel", "Cancelled", int((df["status"] == "Cancelled").sum()), "Marked as cancelled", "alert", "amber")

    tab = st.segmented_control("Show", TABS, default="Upcoming", required=True, key="appointments_tab",
                               persist_state="session", help="Choose which appointments to list.") or "Upcoming"

    f = filter_panel(
        "appointments",
        [Select("doctor", "Doctor", options_from(df, "doctor"), "All doctors"),
         Select("facility", "Facility", options_from(df, "facility"), "All facilities")],
        search_placeholder="Search doctor, facility, type…",
        default_sort=1,
    )

    today = date.today()
    base = df
    if tab == "Upcoming":
        base = df[df["status"].eq("Upcoming") & df["date"].map(lambda v: (parse_date(v) or today) >= today)]
    elif tab == "Past":
        base = df[df["status"].eq("Completed") | (df["status"].eq("Upcoming") &
                                                   df["date"].map(lambda v: (parse_date(v) or today) < today))]
    elif tab == "Cancelled":
        base = df[df["status"].eq("Cancelled")]

    filtered = filter_appointments(base, doctor=f["doctor"], search_query=f["q"], start=f["start"], end=f["end"])
    if f["facility"] != "All":
        filtered = filtered[filtered["facility"] == f["facility"]]
    filtered = apply_sort(filtered, "date", f["sort"], "apt_id")

    view = list_toolbar("appointment", "appointments", filtered, len(base), f"{tab.lower()} appointments" if tab != "All" else "appointments",
                        f["active"], "Add appointment", "CareVault_appointments")
    render_results("appointment", "appointments", filtered, view, f"No {tab.lower()} appointments",
                   "Nothing matches. Try another tab, clear the filters, or add an appointment.")
    render_disclaimer()
