"""Reusable search-and-filter panel.

Widget values persist for the whole session (``persist_state="session"``), so
filters survive opening a record, switching pages and coming back.
"""
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd
import streamlit as st

ALL = "All"
SORT_OPTIONS = ("Latest date first", "Earliest date first")


@dataclass
class Select:
    name: str
    label: str
    options: Sequence[str]
    all_label: str = "All"


def options_from(df: pd.DataFrame, column: str) -> List[str]:
    if df.empty or column not in df.columns:
        return []
    return sorted({str(v) for v in df[column].dropna() if str(v).strip()})


def filter_key(page: str, name: str) -> str:
    """Widget key for a page filter. The generation number changes on Reset, so every
    filter widget starts again from its default (persisted values can't come back)."""
    gen = st.session_state.get(f"_cv_filter_gen_{page}", 0)
    return f"{page}_f{gen}_{name}"


def reset_filters(page: str, names: Sequence[str] = (), extra_keys: Sequence[str] = ()):
    for name in list(names) + ["q", "dates", "sort"]:
        st.session_state.pop(filter_key(page, name), None)
    st.session_state[f"_cv_filter_gen_{page}"] = st.session_state.get(f"_cv_filter_gen_{page}", 0) + 1
    for key in extra_keys:
        st.session_state.pop(key, None)
    st.session_state.pop(f"_cv_limit_{page}", None)


def date_range_value(raw: Any):
    """Normalise st.date_input range output, which can be (), (start,) or (start, end)."""
    if not raw:
        return None, None
    if isinstance(raw, date):
        return raw, raw
    raw = tuple(raw)
    start = raw[0] if len(raw) > 0 else None
    end = raw[1] if len(raw) > 1 else None
    return start, end


def filter_panel(
    page: str,
    selects: Sequence[Select],
    search_placeholder: str,
    search_label: str = "Search",
    with_dates: bool = True,
    with_sort: bool = True,
    default_sort: int = 0,
    extra_reset: Sequence[str] = (),
) -> Dict[str, Any]:
    """Render the panel and return the current values: q, start, end, sort, and each select by name."""
    values: Dict[str, Any] = {}
    names = [s.name for s in selects]
    with st.container(border=True, key=f"cvfilters_{page}"):
        top = st.columns([4, 1.6, 1.3] if with_sort else [5, 1.3], vertical_alignment="bottom", gap="small")
        with top[0]:
            values["q"] = st.text_input(
                search_label, key=filter_key(page, "q"), placeholder=search_placeholder,
                icon=":material/search:", persist_state="session",
                help="Type any words — a hospital, doctor, test, medicine or date like 'Oct 2026'.",
            )
        if with_sort:
            with top[1]:
                values["sort"] = st.selectbox("Sort by date", SORT_OPTIONS, index=default_sort, key=filter_key(page, "sort"),
                                              persist_state="session")
        else:
            values["sort"] = SORT_OPTIONS[0]
        with top[-1]:
            st.button("Reset filters", key=f"{page}_reset_filters", on_click=reset_filters, args=(page, names, tuple(extra_reset)),
                      icon=":material/restart_alt:", width="stretch",
                      help="Clear the search and every filter on this page.")

        slots: List[Any] = list(selects) + (["dates"] if with_dates else [])
        per_row = 4 if len(slots) % 4 == 0 or len(slots) > 6 else 3
        values["start"] = values["end"] = None
        for row_start in range(0, len(slots), per_row):
            row = slots[row_start:row_start + per_row]
            cols = st.columns(per_row, gap="small")
            for col, slot in zip(cols, row):
                with col:
                    if slot == "dates":
                        raw = st.date_input("Date range", value=(), key=filter_key(page, "dates"),
                                            format="DD/MM/YYYY", persist_state="session",
                                            help="Pick a start date, then an end date.")
                        values["start"], values["end"] = date_range_value(raw)
                        continue
                    sel = slot
                    opts = [sel.all_label] + [o for o in sel.options if o != sel.all_label]
                    key = filter_key(page, sel.name)
                    if key in st.session_state and st.session_state[key] not in opts:
                        st.session_state[key] = sel.all_label  # value no longer exists (e.g. record deleted)
                    choice = st.selectbox(sel.label, opts, index=0, key=key, persist_state="session")
                    values[sel.name] = ALL if choice == sel.all_label else choice
    values["active"] = [
        f"{sel.label}: {values[sel.name]}" for sel in selects if values.get(sel.name) not in (None, ALL)
    ]
    if values.get("start") or values.get("end"):
        s = values["start"].strftime("%d %b %Y") if values.get("start") else "…"
        e = values["end"].strftime("%d %b %Y") if values.get("end") else "…"
        values["active"].append(f"Dates: {s} – {e}")
    if values.get("q"):
        values["active"].append(f'Search: "{values["q"]}"')
    return values


def apply_sort(df: pd.DataFrame, date_col: str, sort: str, id_col: Optional[str] = None) -> pd.DataFrame:
    if df.empty:
        return df
    cols = [date_col] + ([id_col] if id_col else [])
    return df.sort_values(cols, ascending=(sort == SORT_OPTIONS[1]), kind="stable")
