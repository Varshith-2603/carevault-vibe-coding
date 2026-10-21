"""Page-level building blocks shared by the record pages."""
import html
from typing import List

import pandas as pd
import streamlit as st

from components.state import open_dialog
from components.tables import csv_download, render_table_view
from components.ui import html_block, render_record_list


def list_toolbar(kind: str, page: str, shown: pd.DataFrame, total: int, noun: str, active: List[str],
                 add_label: str, file_stem: str) -> str:
    """Result count, active-filter summary, list/table switch, CSV export and Add button. Returns the view mode."""
    with st.container(key=f"cvtoolbar_{page}"):
        c1, c2 = st.columns([1.4, 1], vertical_alignment="center", gap="small")
        with c1:
            filters = (f'<span class="cv-results-extra">Filtered by {html.escape(" · ".join(active))}</span>'
                       if active else '<span class="cv-results-extra">No filters applied</span>')
            html_block(f'<div class="cv-results-bar" role="status" aria-live="polite"><span>Showing '
                       f'<strong>{len(shown)}</strong> of {total} {html.escape(noun)}</span>{filters}</div>')
        with c2:
            with st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center", gap="small"):
                view = st.segmented_control("View as", ["List", "Table"], default="List", required=True,
                                            key=f"{page}_view", label_visibility="collapsed", persist_state="session",
                                            help="List is easier to read; Table lets you sort and compare.")
                csv_download(kind, shown, file_stem, key=f"{page}_csv")
                st.button(add_label, key=f"{page}_add", icon=":material/add:", on_click=open_dialog,
                          args=(kind, None, "add"))
    return view or "List"


def render_results(kind: str, page: str, df: pd.DataFrame, view: str, empty_title: str, empty_message: str,
                   page_size: int = 10):
    if view == "Table" and not df.empty:
        render_table_view(kind, df, page)
    else:
        render_record_list(kind, df, page, empty_title, empty_message, page_size=page_size)
