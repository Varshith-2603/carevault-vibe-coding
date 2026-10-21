import pandas as pd
import streamlit as st

from components.state import open_dialog
from components.ui import render_record_list
from utils.exports import to_csv
from utils.records import RECORD_TYPES, record_title

TABLE_COLUMNS = {
    "visit": {"date": "Date", "hospital_name": "Hospital", "department": "Department",
              "attending_physician": "Doctor", "reason_for_visit": "Reason", "status": "Status", "visit_id": "Record ID"},
    "diagnostic": {"date": "Date", "scan_type": "Test", "category": "Category", "facility": "Facility",
                   "ordering_doctor": "Ordered by", "status": "Status", "record_id": "Record ID"},
    "prescription": {"medication": "Medication", "dosage": "Dose", "frequency": "Frequency",
                     "prescribing_doctor": "Prescribed by", "start_date": "Start", "end_date": "End",
                     "refills_remaining": "Refills left", "status": "Status", "rx_id": "Record ID"},
    "history": {"medication": "Medication", "dosage": "Dose", "start_date": "Start", "end_date": "End",
                "prescribed_by": "Prescribed by", "reason": "Recorded reason", "status": "Status", "history_id": "Record ID"},
    "appointment": {"date": "Date", "time": "Time", "type": "Type", "doctor": "Doctor", "department": "Department",
                    "facility": "Facility", "status": "Status", "apt_id": "Record ID"},
    "vital": {"date": "Date", "heart_rate": "Heart rate (bpm)", "systolic_bp": "Systolic (mmHg)",
              "diastolic_bp": "Diastolic (mmHg)", "weight_kg": "Weight (kg)", "spo2": "SpO₂ (%)",
              "recorded_by": "Measured with", "notes": "Notes", "vital_id": "Record ID"},
}


def table_frame(kind: str, df: pd.DataFrame) -> pd.DataFrame:
    cols = TABLE_COLUMNS[kind]
    out = df[[c for c in cols if c in df.columns]].rename(columns=cols).copy()
    for c in out.columns:
        if out[c].dtype == object:
            out[c] = out[c].replace("", "—")
    return out


def render_table_view(kind: str, df: pd.DataFrame, key: str):
    """Sortable, scrollable table. Selecting a row offers a button to open that record."""
    rt = RECORD_TYPES[kind]
    view = table_frame(kind, df)
    event = st.dataframe(
        view, hide_index=True, width="stretch", key=f"{key}_table", on_select="rerun",
        selection_mode="single-row", height=min(42 + 35 * len(view), 520),
        column_config={"Status": st.column_config.TextColumn(width="small")},
    )
    rows = getattr(getattr(event, "selection", None), "rows", []) or []
    if rows and rows[0] < len(df):
        rec = df.iloc[rows[0]].to_dict()
        rid = rec[rt.id_col]
        st.button(f"Open: {record_title(kind, rec)}", key=f"{key}_open_selected", type="primary",
                  on_click=open_dialog, args=(kind, rid), icon=":material/open_in_new:")
    else:
        st.caption("Tip: click the box at the start of a row to select it, then open it. Click a column name to sort.")


def csv_download(kind: str, df: pd.DataFrame, file_stem: str, key: str, label: str = "Export CSV"):
    st.download_button(
        label, data=to_csv(df, TABLE_COLUMNS[kind]), file_name=f"{file_stem}.csv", mime="text/csv",
        key=key, icon=":material/download:", on_click="ignore", disabled=df.empty,
        help=f"Downloads the {len(df)} {RECORD_TYPES[kind].plural.lower()} currently shown "
             "(after filters), with the table columns. Contains demo data.",
    )


def render_hospital_visits_table(df: pd.DataFrame):
    """Backward-compatible wrapper: hospital visits as responsive record rows."""
    render_record_list("visit", df, "visits_compat", "No hospital visits found",
                       "No visits match your filters or search.")


def render_medication_history_table(df: pd.DataFrame):
    """Backward-compatible wrapper: medication history as responsive record rows."""
    render_record_list("history", df, "history_compat", "No medication history",
                       "No past medicines match your filters or search.")
