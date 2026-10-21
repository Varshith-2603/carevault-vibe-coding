import streamlit as st

from components.cards import card_grid, render_diagnostic_card
from components.charts import render_diagnostics_category_chart
from components.filters import Select, apply_sort, filter_key, filter_panel, options_from
from components.header import render_top_header
from components.page import list_toolbar, render_results
from components.ui import paginate, show_more, stat_card, stat_grid
from utils.data_loader import get_diagnostics
from utils.filters import DIAGNOSTIC_GROUPS, diagnostic_group, filter_diagnostics
from utils.helpers import render_disclaimer, render_empty_state


def _show_pending_only():
    st.session_state["diagnostics_pending_only"] = True


def _show_all_reports():
    st.session_state.pop("diagnostics_pending_only", None)


def render_diagnostics_page():
    """Report library: imaging, lab and other tests with a status-aware report viewer."""
    render_top_header(
        title="Scans & Diagnostics",
        subtitle="Your imaging, lab tests and other diagnostic reports.",
        add_kind="diagnostic",
    )
    df = get_diagnostics()
    groups = df["category"].map(diagnostic_group) if not df.empty else df["category"]
    not_final = int(df["status"].str.contains("Processing|Pending", case=False, na=False).sum())
    final = int(df["status"].str.contains("Final|Ready", case=False, na=False).sum())

    with stat_grid("diagnostics"):
        stat_card("d_total", "Total reports", len(df), "All recorded tests", "flask", "blue")
        stat_card("d_final", "Final reports", final, "Final report recorded", "file", "teal")
        stat_card("d_pending", "Not final yet", not_final, "Processing or pending review", "clock", "amber",
                  "Show these" if not_final else None, _show_pending_only)
        stat_card("d_img", "Imaging / Lab", f"{int((groups == 'Imaging').sum())} / {int((groups == 'Laboratory tests').sum())}",
                  "Scans and laboratory tests", "folder", "slate")

    group = st.segmented_control("Type of test", ["All"] + list(DIAGNOSTIC_GROUPS), default="All", required=True,
                                 key=filter_key("diagnostics", "group"), persist_state="session") or "All"

    f = filter_panel(
        "diagnostics",
        [Select("status", "Report status", options_from(df, "status"), "All statuses"),
         Select("facility", "Facility", options_from(df, "facility"), "All facilities"),
         Select("doctor", "Ordered by", options_from(df, "ordering_doctor"), "All doctors"),
         Select("test", "Test name", options_from(df, "scan_type"), "All tests")],
        search_placeholder="Search test, facility, doctor, result…",
        extra_reset=("diagnostics_pending_only",),
    )
    filtered = filter_diagnostics(df, group=group, status=f["status"], facility=f["facility"], doctor=f["doctor"],
                                  search_query=f["q"], start=f["start"], end=f["end"])
    if f["test"] != "All":
        filtered = filtered[filtered["scan_type"] == f["test"]]
    if st.session_state.get("diagnostics_pending_only"):
        filtered = filtered[filtered["status"].str.contains("Processing|Pending", case=False, na=False)]
        c1, c2 = st.columns([3, 1], vertical_alignment="center")
        c1.info("Showing only reports that are not final yet.", icon=":material/filter_alt:")
        c2.button("Show all reports", key="diag_clear_pending", width="stretch",
                  on_click=_show_all_reports)
    filtered = apply_sort(filtered, "date", f["sort"], "record_id")

    active = list(f["active"]) + ([f"Type: {group}"] if group != "All" else [])
    view = list_toolbar("diagnostic", "diagnostics", filtered, len(df), "reports", active, "Add report",
                        "CareVault_diagnostics")
    if view == "Table" and not filtered.empty:
        render_results("diagnostic", "diagnostics", filtered, view, "", "")
    elif filtered.empty:
        render_empty_state("No diagnostic reports found",
                           "Nothing matches your filters. Try 'Reset filters', another test type, or a different search.", "🔬")
    else:
        visible = paginate(filtered, "diagnostics", 12)
        with card_grid("diagnostics"):
            for rec in visible.to_dict(orient="records"):
                render_diagnostic_card(rec, key_prefix="diag")
        show_more(len(filtered), "diagnostics", 12)

    with st.expander("Reports by category", icon=":material/bar_chart:"):
        render_diagnostics_category_chart(filtered)
        st.caption("Counts follow the filters above.")

    render_disclaimer()
