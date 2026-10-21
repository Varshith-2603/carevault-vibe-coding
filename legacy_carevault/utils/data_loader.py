from pathlib import Path
from datetime import date
from typing import Dict, Any, List
import pandas as pd
import streamlit as st

from utils.helpers import is_missing, parse_date
from utils.records import (
    RECORD_TYPES,
    normalize_df,
    add_record,
    get_df,
    get_record,
    build_record_index,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_CSV_FILES = {
    "visit": "hospital_visits.csv",
    "diagnostic": "diagnostics.csv",
    "prescription": "prescriptions.csv",
    "history": "medication_history.csv",
    "appointment": "appointments.csv",
    "vital": "vitals.csv",
}

DEFAULT_PATIENT = {
    "name": "Alex Morgan",
    "patient_id": "PHR-2026-00428",
    "age": 38,
    "gender": "Female",
    "blood_type": "O+",
    "allergies": "Penicillin",
    "emergency_contact": "Michael Morgan (Spouse)",
    "emergency_phone": "+91 98765 43210",
    "primary_condition": "",
    "organ_donor": "Yes",
    "insurance_provider": "BlueCross Shield Gold Health",
    "policy_no": "BCS-9921-2026",
}

DEFAULT_ALERT_PREFS = {
    "appointments": True,
    "appointment_days": 30,
    "reports": True,
    "refills": True,
}


def load_csv_safely(filename: str) -> pd.DataFrame:
    file_path = DATA_DIR / filename
    if file_path.exists():
        try:
            return pd.read_csv(file_path)
        except Exception as e:
            st.error(f"Error loading {filename}: {e}")
            return pd.DataFrame()
    return pd.DataFrame()


def load_dataset(kind: str) -> pd.DataFrame:
    return normalize_df(kind, load_csv_safely(_CSV_FILES[kind]))


def init_session_data(force: bool = False):
    """Initialize all datasets into Streamlit session state if not already loaded."""
    if force or "data_initialized" not in st.session_state:
        for kind, rt in RECORD_TYPES.items():
            st.session_state[rt.state_key] = load_dataset(kind)

        # Patient Profile state (fictional demo patient)
        st.session_state.patient_info = dict(DEFAULT_PATIENT)
        st.session_state.alert_prefs = dict(DEFAULT_ALERT_PREFS)
        st.session_state.dismissed_alerts = set()
        st.session_state.attachments = {}
        st.session_state["_cv_id_high_water"] = {}
        st.session_state["_cv_session_added"] = set()

        # Navigation state
        if not force:
            st.session_state.current_page = "Dashboard"
            st.session_state.global_search_query = ""
        st.session_state.data_initialized = True


def get_hospital_visits() -> pd.DataFrame:
    init_session_data()
    return st.session_state.hospital_visits


def get_diagnostics() -> pd.DataFrame:
    init_session_data()
    return st.session_state.diagnostics


def get_prescriptions() -> pd.DataFrame:
    init_session_data()
    return st.session_state.prescriptions


def get_medication_history() -> pd.DataFrame:
    init_session_data()
    return st.session_state.medication_history


def get_appointments() -> pd.DataFrame:
    init_session_data()
    return st.session_state.appointments


def get_vitals() -> pd.DataFrame:
    init_session_data()
    return st.session_state.vitals


def get_patient_info() -> Dict[str, Any]:
    init_session_data()
    return st.session_state.patient_info


# Backward-compatible add helpers (the record dict gains its new ID, as before).
def add_hospital_visit(record: Dict[str, Any]):
    init_session_data()
    record["visit_id"] = add_record("visit", record)


def add_diagnostic_report(record: Dict[str, Any]):
    init_session_data()
    record["record_id"] = add_record("diagnostic", record)


def add_prescription(record: Dict[str, Any]):
    init_session_data()
    if is_missing(record.get("status")):
        record["status"] = "Active"
    record["rx_id"] = add_record("prescription", record)


def add_medication_history(record: Dict[str, Any]):
    init_session_data()
    record["history_id"] = add_record("history", record)


def refill_prescription(rx_id: str) -> bool:
    """Record that one refill was used: decrements the remaining refill count."""
    init_session_data()
    df = st.session_state.prescriptions.copy()
    idx = df[df["rx_id"] == rx_id].index
    if len(idx) > 0 and not is_missing(df.loc[idx[0], "refills_remaining"]):
        current_refills = int(df.loc[idx[0], "refills_remaining"])
        if current_refills > 0:
            df.loc[idx[0], "refills_remaining"] = current_refills - 1
            st.session_state.prescriptions = df
            return True
    return False


# --------------------------------------------------------------------------
# Derived views
# --------------------------------------------------------------------------
def upcoming_appointments(today: date | None = None) -> pd.DataFrame:
    """Appointments marked Upcoming and dated today or later, soonest first."""
    today = today or date.today()
    apts = get_appointments()
    if apts.empty:
        return apts
    dates = apts["date"].map(parse_date)
    mask = apts["status"].eq("Upcoming") & dates.map(lambda d: d is not None and d >= today)
    return apts[mask].sort_values(["date", "time"], kind="stable")


def past_records_only(df: pd.DataFrame, date_col: str = "date", today: date | None = None) -> pd.DataFrame:
    """Rows dated on or before today — future-dated measurements are not treated as real readings."""
    today = today or date.today()
    if df.empty:
        return df
    return df[df[date_col].map(lambda v: (parse_date(v) or date.max) <= today)]


def get_dashboard_metrics() -> Dict[str, Any]:
    init_session_data()
    visits = st.session_state.hospital_visits
    diagnostics = st.session_state.diagnostics
    prescriptions = st.session_state.prescriptions
    appointments = st.session_state.appointments

    upcoming = upcoming_appointments()
    if upcoming.empty:
        # Fall back to the recorded status alone so an "Upcoming" entry is still surfaced
        upcoming = appointments[appointments["status"] == "Upcoming"].sort_values("date", kind="stable")
    next_apt = upcoming.iloc[0] if len(upcoming) > 0 else None

    past_visits = past_records_only(visits)
    last_visit = past_visits.iloc[0] if len(past_visits) > 0 else (visits.iloc[0] if len(visits) > 0 else None)

    active_rx_count = len(prescriptions[prescriptions["status"] == "Active"])

    # Total records count (visits + diagnostics + prescriptions) — kept for compatibility
    total_records = len(visits) + len(diagnostics) + len(prescriptions)
    all_records = sum(len(get_df(k)) for k in RECORD_TYPES)

    return {
        "next_appointment": next_apt,
        "upcoming_count": len(upcoming),
        "last_visit": last_visit,
        "active_rx_count": active_rx_count,
        "total_records": total_records,
        "all_records_count": all_records,
        "total_visits": len(visits),
        "different_hospitals": visits["hospital_name"].nunique() if len(visits) > 0 else 0,
        "total_reports": len(diagnostics),
        "pending_reports": len(diagnostics[diagnostics["status"].str.contains("Processing|Pending", case=False, na=False)]),
        "final_reports": len(diagnostics[diagnostics["status"].str.contains("Final|Ready", case=False, na=False)]),
    }


def get_alerts() -> List[Dict[str, Any]]:
    """In-app alerts derived from the records themselves (nothing is invented)."""
    init_session_data()
    prefs = st.session_state.get("alert_prefs", DEFAULT_ALERT_PREFS)
    today = date.today()
    alerts = []
    if prefs.get("appointments", True):
        window = int(prefs.get("appointment_days", 30))
        for apt in upcoming_appointments().to_dict(orient="records"):
            d = parse_date(apt["date"])
            if d and (d - today).days <= window:
                alerts.append({
                    "id": f"apt:{apt['apt_id']}", "kind": "appointment", "record_id": apt["apt_id"],
                    "title": "Upcoming appointment",
                    "desc": f"{apt.get('type') or 'Appointment'} with {apt.get('doctor') or 'your doctor'} on {d.strftime('%d %b %Y')}",
                })
    if prefs.get("reports", True):
        diag = get_diagnostics()
        for rec in diag[diag["status"].str.contains("Processing|Pending", case=False, na=False)].to_dict(orient="records"):
            alerts.append({
                "id": f"dg:{rec['record_id']}:{rec['status']}", "kind": "diagnostic", "record_id": rec["record_id"],
                "title": "Report not final yet",
                "desc": f"{rec.get('scan_type')} — status: {rec.get('status')}",
            })
    if prefs.get("refills", True):
        rx = get_prescriptions()
        for rec in rx[rx["status"].eq("Active")].to_dict(orient="records"):
            refills = rec.get("refills_remaining")
            if not is_missing(refills) and int(refills) <= 1:
                alerts.append({
                    "id": f"rx:{rec['rx_id']}:{int(refills)}", "kind": "prescription", "record_id": rec["rx_id"],
                    "title": "Few refills left",
                    "desc": f"{rec.get('medication')} — {int(refills)} refill{'s' if int(refills) != 1 else ''} remaining",
                })
    dismissed = st.session_state.get("dismissed_alerts", set())
    for a in alerts:
        a["unread"] = a["id"] not in dismissed
    return alerts


def recent_activity(limit: int = 6) -> pd.DataFrame:
    """Most recent dated records up to today (appointments only once they have happened).
    Vitals readings are left out — they have their own chart and would crowd out everything else."""
    index = build_record_index(["visit", "diagnostic", "prescription", "history", "appointment"])
    if index.empty:
        return index
    index = past_records_only(index)
    index = index[~((index["kind"] == "appointment") & (index["status"] == "Upcoming"))]
    return index.head(limit)


def export_bundle() -> Dict[str, Any]:
    """Complete record set for the JSON download."""
    def records(kind):
        df = get_df(kind)
        return df.astype(object).where(df.notna(), None).to_dict(orient="records")
    return {
        "notice": "CareVault demo export. Contains fictional demo data and any records you added in this session.",
        "exported_on": date.today().isoformat(),
        "patient": st.session_state.patient_info,
        **{RECORD_TYPES[k].state_key: records(k) for k in RECORD_TYPES},
    }


def reset_demo_data():
    init_session_data(force=True)

