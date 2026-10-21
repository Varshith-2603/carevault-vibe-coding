import streamlit as st

from components.cards import card_grid, render_prescription_card
from components.filters import Select, apply_sort, filter_key, filter_panel, options_from
from components.header import render_top_header
from components.page import list_toolbar, render_results
from components.ui import html_block, notice, paginate, show_more, stat_card, stat_grid
from utils.data_loader import get_medication_history, get_prescriptions
from utils.filters import filter_medication_history, filter_prescriptions
from utils.helpers import is_missing, render_disclaimer, render_empty_state

TABS = ["Active prescriptions", "Medication history"]


def _show_tab(tab: str):
    st.session_state["rx_tab"] = tab


def render_prescriptions_page():
    """Active prescriptions and past medication history, kept as separate lists."""
    render_top_header(
        title="Prescriptions & Medicines",
        subtitle="What you are taking now and what you have taken before, as recorded.",
        add_kind="prescription",
    )
    rx_df = get_prescriptions()
    hist_df = get_medication_history()
    active = rx_df[rx_df["status"] == "Active"]
    low = active[active["refills_remaining"].map(lambda v: not is_missing(v) and v <= 1)]

    with stat_grid("rx"):
        stat_card("rx_active", "Active prescriptions", len(active), f"{len(rx_df)} prescriptions in total", "pill", "amber",
                  "View active", _show_tab, ("Active prescriptions",))
        stat_card("rx_low", "1 refill or fewer", len(low), "Active prescriptions with few refills left", "alert", "amber")
        stat_card("rx_hist", "Past medicines", len(hist_df), "Completed or discontinued courses", "history", "slate",
                  "View history", _show_tab, ("Medication history",))
        stat_card("rx_docs", "Prescribing doctors", rx_df["prescribing_doctor"].replace("", None).nunique(),
                  "On current prescriptions", "user", "blue")

    html_block(notice("CareVault keeps a copy of what was prescribed — it isn't a prescribing tool. Check doses and "
                      "instructions with your doctor or pharmacist, and don't start, stop or change a medicine "
                      "based on this app.", "info", "shield"))

    st.session_state.setdefault("rx_tab", TABS[0])
    tab = st.segmented_control("Show", TABS, required=True, key="rx_tab", label_visibility="collapsed") or TABS[0]

    if tab == TABS[0]:
        st.session_state.setdefault(filter_key("rx", "status"), "Active")
        f = filter_panel(
            "rx",
            [Select("status", "Status", ["Active", "On Hold", "Completed", "Discontinued"] +
                    [s for s in options_from(rx_df, "status") if s not in ("Active", "On Hold", "Completed", "Discontinued")],
                    "All statuses"),
             Select("doctor", "Prescribing doctor", options_from(rx_df, "prescribing_doctor"), "All doctors")],
            search_placeholder="Search medicine, doctor, pharmacy…",
        )
        filtered = filter_prescriptions(rx_df, status=f["status"], doctor=f["doctor"], search_query=f["q"],
                                        start=f["start"], end=f["end"])
        filtered = apply_sort(filtered, "start_date", f["sort"], "rx_id")
        view = list_toolbar("prescription", "rx", filtered, len(rx_df), "prescriptions", f["active"],
                            "Add prescription", "CareVault_prescriptions")
        if view == "Table" and not filtered.empty:
            render_results("prescription", "rx", filtered, view, "", "")
        elif filtered.empty:
            render_empty_state("No prescriptions found",
                               "Nothing matches your filters. Try 'Reset filters' or another status.", "💊")
        else:
            visible = paginate(filtered, "rx", 12)
            with card_grid("rx"):
                for rec in visible.to_dict(orient="records"):
                    render_prescription_card(rec, key_prefix="rx")
            show_more(len(filtered), "rx", 12)
    else:
        f = filter_panel(
            "history",
            [Select("status", "Status", options_from(hist_df, "status"), "All statuses"),
             Select("doctor", "Prescribed by", options_from(hist_df, "prescribed_by"), "All doctors")],
            search_placeholder="Search medicine, reason, doctor…",
        )
        filtered = filter_medication_history(hist_df, status=f["status"], doctor=f["doctor"], search_query=f["q"],
                                             start=f["start"], end=f["end"])
        filtered = apply_sort(filtered, "start_date", f["sort"], "history_id")
        view = list_toolbar("history", "history", filtered, len(hist_df), "past medicines", f["active"],
                            "Add past medicine", "CareVault_medication_history")
        render_results("history", "history", filtered, view, "No medication history found",
                       "Nothing matches your filters. Try 'Reset filters' or a different search.")

    render_disclaimer()
