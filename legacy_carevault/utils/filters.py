from datetime import date
from typing import Dict, Optional, Sequence
import pandas as pd

from utils.helpers import parse_date
from utils.records import match_query, row_search_text


def _is_all(value) -> bool:
    return value is None or value == "" or value == "All" or (isinstance(value, str) and value.startswith("All "))


def filter_by_date(df: pd.DataFrame, date_col: str, start: Optional[date] = None, end: Optional[date] = None) -> pd.DataFrame:
    """Keep rows whose date falls within [start, end]. Rows without a date are kept only when no range is set."""
    if df.empty or (start is None and end is None):
        return df
    dates = df[date_col].map(parse_date)
    mask = dates.map(lambda d: d is not None and (start is None or d >= start) and (end is None or d <= end))
    return df[mask]


def _apply_equals(df: pd.DataFrame, column: str, value) -> pd.DataFrame:
    if _is_all(value) or column not in df.columns:
        return df
    return df[df[column] == value]


def _apply_search(df: pd.DataFrame, kind: str, search_query: str) -> pd.DataFrame:
    if not search_query or not search_query.strip() or df.empty:
        return df
    return df[match_query(row_search_text(kind, df), search_query)]


def filter_hospital_visits(
    df: pd.DataFrame,
    hospital: str = "All",
    department: str = "All",
    search_query: str = "",
    doctor: str = "All",
    status: str = "All",
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> pd.DataFrame:
    filtered = df.copy()
    filtered = _apply_equals(filtered, "hospital_name", hospital)
    filtered = _apply_equals(filtered, "department", department)
    filtered = _apply_equals(filtered, "attending_physician", doctor)
    filtered = _apply_equals(filtered, "status", status)
    filtered = filter_by_date(filtered, "date", start, end)
    return _apply_search(filtered, "visit", search_query)


DIAGNOSTIC_GROUPS = {
    "Imaging": ("Radiology & Imaging",),
    "Laboratory tests": ("Laboratory & Pathology",),
    "Other procedures": None,  # everything that is neither imaging nor lab
}


def diagnostic_group(category: str) -> str:
    for group, cats in DIAGNOSTIC_GROUPS.items():
        if cats and category in cats:
            return group
    return "Other procedures"


def filter_diagnostics(
    df: pd.DataFrame,
    category: str = "All",
    status: str = "All",
    search_query: str = "",
    group: str = "All",
    facility: str = "All",
    doctor: str = "All",
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> pd.DataFrame:
    filtered = df.copy()
    filtered = _apply_equals(filtered, "category", category)
    filtered = _apply_equals(filtered, "status", status)
    filtered = _apply_equals(filtered, "facility", facility)
    filtered = _apply_equals(filtered, "ordering_doctor", doctor)
    if not _is_all(group) and not filtered.empty:
        filtered = filtered[filtered["category"].map(diagnostic_group) == group]
    filtered = filter_by_date(filtered, "date", start, end)
    return _apply_search(filtered, "diagnostic", search_query)


def filter_prescriptions(
    df: pd.DataFrame,
    status: str = "All",
    search_query: str = "",
    doctor: str = "All",
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> pd.DataFrame:
    filtered = df.copy()
    filtered = _apply_equals(filtered, "status", status)
    filtered = _apply_equals(filtered, "prescribing_doctor", doctor)
    filtered = filter_by_date(filtered, "start_date", start, end)
    return _apply_search(filtered, "prescription", search_query)


def filter_medication_history(
    df: pd.DataFrame,
    status: str = "All",
    search_query: str = "",
    doctor: str = "All",
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> pd.DataFrame:
    filtered = df.copy()
    filtered = _apply_equals(filtered, "status", status)
    filtered = _apply_equals(filtered, "prescribed_by", doctor)
    filtered = filter_by_date(filtered, "start_date", start, end)
    return _apply_search(filtered, "history", search_query)


def filter_appointments(
    df: pd.DataFrame,
    status: str = "All",
    search_query: str = "",
    doctor: str = "All",
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> pd.DataFrame:
    filtered = df.copy()
    filtered = _apply_equals(filtered, "status", status)
    filtered = _apply_equals(filtered, "doctor", doctor)
    filtered = filter_by_date(filtered, "date", start, end)
    return _apply_search(filtered, "appointment", search_query)


def filter_index(
    index: pd.DataFrame,
    query: str = "",
    kinds: Optional[Sequence[str]] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> pd.DataFrame:
    """Filter the unified record index used by All Records and global search."""
    out = index
    if kinds:
        out = out[out["kind"].isin(list(kinds))]
    out = filter_by_date(out, "date", start, end)
    if query and query.strip() and not out.empty:
        out = out[match_query(out["_search"], query)]
    return out


def perform_global_search(
    query: str,
    visits_df: pd.DataFrame,
    diagnostics_df: pd.DataFrame,
    prescriptions_df: pd.DataFrame,
    history_df: pd.DataFrame,
    appointments_df: Optional[pd.DataFrame] = None,
) -> Dict[str, pd.DataFrame]:
    if not query or not query.strip():
        empty = {"visits": pd.DataFrame(), "diagnostics": pd.DataFrame(), "prescriptions": pd.DataFrame(),
                 "history": pd.DataFrame()}
        if appointments_df is not None:
            empty["appointments"] = pd.DataFrame()
        return empty

    results = {
        "visits": _apply_search(visits_df, "visit", query),
        "diagnostics": _apply_search(diagnostics_df, "diagnostic", query),
        "prescriptions": _apply_search(prescriptions_df, "prescription", query),
        "history": _apply_search(history_df, "history", query),
    }
    if appointments_df is not None:
        results["appointments"] = _apply_search(appointments_df, "appointment", query)
    return results
