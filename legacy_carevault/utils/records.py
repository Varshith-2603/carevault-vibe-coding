"""
Record registry and data operations for every CareVault record type.

Each record type is described once (fields, form sections, identifiers, search
fields) and every page, form, detail view, search and export reads from that
description. Data lives in ``st.session_state`` as pandas DataFrames, exactly
as the original CSV loader stored it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from utils.helpers import display, format_date, is_missing, parse_date


# --------------------------------------------------------------------------
# Schema
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Field:
    name: str
    label: str
    kind: str = "text"  # text | textarea | date | optional_date | time | select | number | float | visit_link
    required: bool = False
    help: str = ""
    placeholder: str = ""
    options: Tuple[str, ...] = ()
    accept_new: bool = False  # select that also accepts typed values
    suggest_from: Tuple[str, ...] = ()  # (state_key, column) pairs flattened: suggestions from existing data
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allow_future: bool = True


@dataclass(frozen=True)
class RecordType:
    kind: str
    label: str
    plural: str
    state_key: str
    id_col: str
    id_prefix: str
    date_col: str
    sections: Tuple[Tuple[str, Tuple[Field, ...]], ...]
    search_cols: Tuple[str, ...]
    numeric_cols: Tuple[str, ...] = ()
    page: str = ""
    icon: str = "folder"

    @property
    def fields(self) -> List[Field]:
        return [f for _, fs in self.sections for f in fs]

    def field(self, name: str) -> Optional[Field]:
        return next((f for f in self.fields if f.name == name), None)


VISIT_LINK_HELP = "Optional. Link this record to the hospital visit it came from, so you can move between them."

HOSPITAL_SUGGEST = ("hospital_visits:hospital_name", "diagnostics:facility", "appointments:facility")
DOCTOR_SUGGEST = (
    "hospital_visits:attending_physician", "diagnostics:ordering_doctor", "prescriptions:prescribing_doctor",
    "medication_history:prescribed_by", "appointments:doctor",
)
DEPARTMENT_SUGGEST = ("hospital_visits:department", "appointments:department")

VISIT = RecordType(
    kind="visit", label="Hospital visit", plural="Hospital visits", state_key="hospital_visits",
    id_col="visit_id", id_prefix="HV", date_col="date", page="Hospital Visits", icon="hospital",
    sections=(
        ("Visit information", (
            Field("date", "Visit date", "date", required=True, allow_future=False),
            Field("visit_type", "Visit type", "select", options=("Outpatient", "Emergency", "Inpatient", "Teleconsult")),
            Field("status", "Visit status", "select", options=("Completed", "Follow-up Scheduled", "Inpatient", "Discharged")),
        )),
        ("Hospital and doctor", (
            Field("hospital_name", "Hospital or clinic", "select", required=True, accept_new=True,
                  suggest_from=HOSPITAL_SUGGEST, help="Pick from the list or type a new name."),
            Field("department", "Department", "select", required=True, accept_new=True, suggest_from=DEPARTMENT_SUGGEST,
                  help="For example Cardiology or General Medicine."),
            Field("attending_physician", "Doctor you saw", "select", required=True, accept_new=True, suggest_from=DOCTOR_SUGGEST),
        )),
        ("Reason and notes", (
            Field("reason_for_visit", "Reason for visit", required=True, placeholder="e.g. Fever and fatigue"),
            Field("diagnosis_code", "Diagnosis or code", placeholder="As written on your visit paperwork",
                  help="Optional. Copy it exactly from your documents."),
            Field("summary", "Visit notes", "textarea", placeholder="What the doctor found or told you"),
            Field("discharge_instructions", "Follow-up instructions", "textarea",
                  placeholder="Any follow-up the doctor recorded"),
        )),
    ),
    search_cols=("hospital_name", "department", "attending_physician", "reason_for_visit", "status",
                 "visit_type", "diagnosis_code", "visit_id"),
)

DIAGNOSTIC = RecordType(
    kind="diagnostic", label="Diagnostic report", plural="Scans & diagnostics", state_key="diagnostics",
    id_col="record_id", id_prefix="DG", date_col="date", page="Scans & Diagnostics", icon="flask",
    sections=(
        ("Test information", (
            Field("scan_type", "Test or scan name", required=True, placeholder="e.g. Lipid Panel, Chest X-Ray"),
            Field("category", "Category", "select", required=True,
                  options=("Radiology & Imaging", "Laboratory & Pathology", "Cardiology Diagnostics", "Other")),
            Field("date", "Test date", "date", required=True, allow_future=False),
            Field("status", "Report status", "select",
                  options=("Final Report Ready", "Processing", "Pending Review", "Report Unavailable"),
                  help="Choose 'Processing' if you are still waiting for results."),
        )),
        ("Facility and doctor", (
            Field("facility", "Facility or lab", "select", required=True, accept_new=True, suggest_from=HOSPITAL_SUGGEST),
            Field("ordering_doctor", "Doctor who ordered it", "select", required=True, accept_new=True,
                  suggest_from=DOCTOR_SUGGEST),
            Field("accession_no", "Reference number", placeholder="Accession or sample number, if shown"),
        )),
        ("Results as written in your report", (
            Field("summary", "Result summary", "textarea", placeholder="A short summary copied from the report"),
            Field("findings", "Detailed findings", "textarea"),
            Field("impression", "Conclusion / impression", "textarea"),
            Field("normal_range", "Reference range", placeholder="As printed on the report"),
        )),
        ("Related records", (
            Field("visit_id", "Related hospital visit", "visit_link", help=VISIT_LINK_HELP),
        )),
    ),
    search_cols=("scan_type", "category", "facility", "ordering_doctor", "status", "summary", "impression",
                 "record_id", "accession_no"),
)

PRESCRIPTION = RecordType(
    kind="prescription", label="Prescription", plural="Prescriptions", state_key="prescriptions",
    id_col="rx_id", id_prefix="RX", date_col="start_date", page="Prescriptions & Medicines", icon="pill",
    numeric_cols=("refills_remaining",),
    sections=(
        ("Medication", (
            Field("medication", "Medication name", required=True, placeholder="As written on the label"),
            Field("dosage", "Dose / strength", required=True, placeholder="e.g. 50 mg"),
            Field("frequency", "How often (as prescribed)", "select", required=True, accept_new=True,
                  options=("Once daily", "Twice daily", "Thrice daily", "Before breakfast", "At bedtime",
                           "Once weekly", "As needed"),
                  suggest_from=("prescriptions:frequency",)),
            Field("route", "How it is taken", "select",
                  options=("Oral", "Topical", "Ophthalmic", "Nasal", "Inhaled", "Injection", "Other")),
        )),
        ("Prescriber and dates", (
            Field("prescribing_doctor", "Prescribing doctor", "select", required=True, accept_new=True,
                  suggest_from=DOCTOR_SUGGEST),
            Field("start_date", "Start date", "date", required=True),
            Field("end_date", "End date", "optional_date", help="Leave empty if no end date was given."),
            Field("status", "Status", "select", options=("Active", "On Hold", "Completed", "Discontinued")),
        )),
        ("Refills and pharmacy", (
            Field("refills_remaining", "Refills remaining", "number", min_value=0, max_value=99,
                  help="Leave empty if you don't know."),
            Field("pharmacy", "Pharmacy", "select", accept_new=True, suggest_from=("prescriptions:pharmacy",)),
        )),
        ("Label instructions", (
            Field("instructions", "Directions on the label", "textarea",
                  placeholder="Copy the directions exactly as printed"),
            Field("warnings", "Warnings on the label", "textarea"),
        )),
        ("Related records", (
            Field("visit_id", "Related hospital visit", "visit_link", help=VISIT_LINK_HELP),
        )),
    ),
    search_cols=("medication", "dosage", "frequency", "prescribing_doctor", "status", "pharmacy", "instructions", "rx_id"),
)

HISTORY = RecordType(
    kind="history", label="Past medication", plural="Medication history", state_key="medication_history",
    id_col="history_id", id_prefix="MH", date_col="start_date", page="Prescriptions & Medicines", icon="history",
    sections=(
        ("Medication", (
            Field("medication", "Medication name", required=True),
            Field("dosage", "Dose / strength", placeholder="e.g. 625 mg"),
            Field("reason", "Recorded reason", required=True, placeholder="Why it was prescribed, as recorded"),
        )),
        ("Prescriber and dates", (
            Field("prescribed_by", "Prescribed by", "select", required=True, accept_new=True, suggest_from=DOCTOR_SUGGEST),
            Field("start_date", "Start date", "date", required=True, allow_future=False),
            Field("end_date", "End date", "optional_date", allow_future=False),
            Field("status", "Status", "select", options=("Completed", "Discontinued")),
        )),
        ("Notes", (
            Field("notes", "Notes", "textarea", placeholder="Anything recorded about this course"),
        )),
        ("Related records", (
            Field("visit_id", "Related hospital visit", "visit_link", help=VISIT_LINK_HELP),
        )),
    ),
    search_cols=("medication", "dosage", "prescribed_by", "reason", "status", "notes", "history_id"),
)

APPOINTMENT = RecordType(
    kind="appointment", label="Appointment", plural="Appointments", state_key="appointments",
    id_col="apt_id", id_prefix="APT", date_col="date", page="Appointments", icon="calendar",
    sections=(
        ("When", (
            Field("date", "Date", "date", required=True),
            Field("time", "Time", "time"),
            Field("status", "Status", "select", options=("Upcoming", "Completed", "Cancelled")),
        )),
        ("Where and with whom", (
            Field("doctor", "Doctor", "select", required=True, accept_new=True, suggest_from=DOCTOR_SUGGEST),
            Field("department", "Department", "select", accept_new=True, suggest_from=DEPARTMENT_SUGGEST),
            Field("facility", "Hospital or clinic", "select", required=True, accept_new=True, suggest_from=HOSPITAL_SUGGEST),
            Field("room", "Room / location", placeholder="e.g. Room 402"),
        )),
        ("Details", (
            Field("type", "Appointment type", placeholder="e.g. Follow-up consultation", required=True),
            Field("instructions", "Preparation notes", "textarea", placeholder="Anything you were asked to bring or do"),
        )),
        ("Related records", (
            Field("visit_id", "Resulting hospital visit", "visit_link",
                  help="Optional. For a completed appointment, link the visit record it produced."),
        )),
    ),
    search_cols=("doctor", "department", "facility", "type", "status", "room", "apt_id"),
)

VITAL = RecordType(
    kind="vital", label="Vitals reading", plural="Health vitals", state_key="vitals",
    id_col="vital_id", id_prefix="VT", date_col="date", page="Health Vitals", icon="heart",
    numeric_cols=("heart_rate", "systolic_bp", "diastolic_bp", "weight_kg", "spo2"),
    sections=(
        ("Reading", (
            Field("date", "Date measured", "date", required=True, allow_future=False),
            Field("recorded_by", "Measured with / by", "select", accept_new=True, suggest_from=("vitals:recorded_by",),
                  help="For example a home monitor or a clinic."),
        )),
        ("Measurements (fill in what you measured)", (
            Field("heart_rate", "Heart rate (bpm)", "number", min_value=20, max_value=250),
            Field("spo2", "Blood oxygen SpO₂ (%)", "number", min_value=50, max_value=100),
            Field("systolic_bp", "Blood pressure — systolic (mmHg)", "number", min_value=50, max_value=260,
                  help="The top number."),
            Field("diastolic_bp", "Blood pressure — diastolic (mmHg)", "number", min_value=30, max_value=160,
                  help="The bottom number."),
            Field("weight_kg", "Weight (kg)", "float", min_value=1, max_value=400),
        )),
        ("Notes", (
            Field("notes", "Notes", "textarea", placeholder="e.g. Resting, morning"),
        )),
    ),
    search_cols=("recorded_by", "notes", "vital_id"),
)

RECORD_TYPES: Dict[str, RecordType] = {
    rt.kind: rt for rt in (VISIT, DIAGNOSTIC, PRESCRIPTION, HISTORY, APPOINTMENT, VITAL)
}
LINKABLE_KINDS = ("diagnostic", "prescription", "history", "appointment")
VITAL_MEASURES = ("heart_rate", "systolic_bp", "diastolic_bp", "weight_kg", "spo2")


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------
def normalize_df(kind: str, df: pd.DataFrame) -> pd.DataFrame:
    """Give a DataFrame every schema column, consistent dtypes, IDs and newest-first order."""
    rt = RECORD_TYPES[kind]
    df = df.copy()
    columns = [rt.id_col] + [f.name for f in rt.fields]
    for col in columns:
        if col not in df.columns:
            df[col] = pd.NA if col in rt.numeric_cols else ""
    for col in df.columns:
        if col in rt.numeric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)
        else:
            # object dtype keeps assignments of any text safe under pandas' strict string dtype
            df[col] = df[col].astype(object).where(df[col].notna(), "").map(lambda v: str(v).strip())
    if df[rt.id_col].eq("").any():
        df = df.sort_values(rt.date_col, kind="stable").reset_index(drop=True)
        counter = _max_id_number(df[rt.id_col])
        for i in df.index[df[rt.id_col].eq("")]:
            counter += 1
            df.at[i, rt.id_col] = _format_id(rt, counter, df.at[i, rt.date_col])
    return sort_df(kind, df)


def sort_df(kind: str, df: pd.DataFrame, ascending: bool = False) -> pd.DataFrame:
    rt = RECORD_TYPES[kind]
    if df.empty or rt.date_col not in df.columns:
        return df.reset_index(drop=True)
    return df.sort_values([rt.date_col, rt.id_col], ascending=ascending, kind="stable").reset_index(drop=True)


def _max_id_number(ids: pd.Series) -> int:
    nums = [int(m.group(1)) for m in (re.search(r"(\d+)$", str(i)) for i in ids) if m]
    return max(nums, default=0)


def _format_id(rt: RecordType, number: int, when: Any = None) -> str:
    year = (parse_date(when) or date.today()).year
    return f"{rt.id_prefix}-{year}-{number:03d}"


def next_id(kind: str, df: pd.DataFrame) -> str:
    """Collision-free ID: one more than the highest number already used, even after deletions."""
    rt = RECORD_TYPES[kind]
    used = st.session_state.setdefault("_cv_id_high_water", {})
    number = max(_max_id_number(df[rt.id_col]) if rt.id_col in df.columns else 0, used.get(kind, 0)) + 1
    used[kind] = number
    return _format_id(rt, number, date.today())


# --------------------------------------------------------------------------
# Access & mutation
# --------------------------------------------------------------------------
def get_df(kind: str) -> pd.DataFrame:
    return st.session_state[RECORD_TYPES[kind].state_key]


def _set_df(kind: str, df: pd.DataFrame):
    st.session_state[RECORD_TYPES[kind].state_key] = sort_df(kind, df)


def get_record(kind: str, record_id: str) -> Optional[Dict[str, Any]]:
    rt = RECORD_TYPES.get(kind)
    if rt is None or rt.state_key not in st.session_state:
        return None
    df = get_df(kind)
    match = df[df[rt.id_col] == record_id]
    return None if match.empty else match.iloc[0].to_dict()


def clean_values(kind: str, values: Dict[str, Any]) -> Dict[str, Any]:
    """Convert widget values into the stored representation (ISO dates, stripped text, numbers or NA)."""
    rt = RECORD_TYPES[kind]
    out: Dict[str, Any] = {}
    for f in rt.fields:
        if f.name not in values:
            continue
        v = values[f.name]
        if f.kind in ("date", "optional_date"):
            d = parse_date(v)
            out[f.name] = d.isoformat() if d else ""
        elif f.kind == "time":
            if is_missing(v):
                out[f.name] = ""
            elif hasattr(v, "strftime"):
                out[f.name] = v.strftime("%I:%M %p")
            else:
                out[f.name] = str(v).strip()
        elif f.kind in ("number", "float"):
            if is_missing(v):
                out[f.name] = pd.NA
            else:
                out[f.name] = float(v) if f.kind == "float" else int(v)
        else:
            out[f.name] = "" if is_missing(v) else str(v).strip()
    return out


def add_record(kind: str, values: Dict[str, Any]) -> str:
    rt = RECORD_TYPES[kind]
    df = get_df(kind)
    record = {k: v for k, v in values.items()}
    if is_missing(record.get(rt.id_col)) or record.get(rt.id_col) in set(df[rt.id_col]):
        record[rt.id_col] = next_id(kind, df)
    new_row = normalize_df(kind, pd.DataFrame([record]))
    for col in df.columns:
        if col not in new_row.columns:
            new_row[col] = pd.NA if col in rt.numeric_cols else ""
    combined = pd.concat([new_row[df.columns.union(new_row.columns, sort=False)], df], ignore_index=True)
    _set_df(kind, combined)
    st.session_state.setdefault("_cv_session_added", set()).add((kind, record[rt.id_col]))
    return record[rt.id_col]


def update_record(kind: str, record_id: str, values: Dict[str, Any]) -> bool:
    rt = RECORD_TYPES[kind]
    df = get_df(kind).copy()
    idx = df.index[df[rt.id_col] == record_id]
    if len(idx) == 0:
        return False
    for col, v in values.items():
        if col == rt.id_col:
            continue
        if col not in df.columns:
            df[col] = pd.NA if col in rt.numeric_cols else ""
        if col in rt.numeric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)
            df.loc[idx[0], col] = float("nan") if is_missing(v) else float(v)
        else:
            df[col] = df[col].astype(object)
            df.at[idx[0], col] = "" if is_missing(v) else str(v)
    _set_df(kind, df)
    return True


def delete_record(kind: str, record_id: str) -> bool:
    """Delete one record. Deleting a visit unlinks (never deletes) the records that pointed to it."""
    rt = RECORD_TYPES[kind]
    df = get_df(kind)
    if record_id not in set(df[rt.id_col]):
        return False
    _set_df(kind, df[df[rt.id_col] != record_id])
    if kind == "visit":
        for linked_kind in LINKABLE_KINDS:
            ldf = get_df(linked_kind).copy()
            if "visit_id" in ldf.columns and ldf["visit_id"].eq(record_id).any():
                ldf.loc[ldf["visit_id"] == record_id, "visit_id"] = ""
                _set_df(linked_kind, ldf)
    st.session_state.get("attachments", {}).pop((kind, record_id), None)
    return True


def linked_records(visit_id: str) -> List[Tuple[str, Dict[str, Any]]]:
    """Records explicitly linked to a visit through their ``visit_id`` field."""
    out = []
    if is_missing(visit_id):
        return out
    for kind in LINKABLE_KINDS:
        df = get_df(kind)
        if "visit_id" in df.columns:
            for _, row in df[df["visit_id"] == visit_id].iterrows():
                out.append((kind, row.to_dict()))
    return out


# --------------------------------------------------------------------------
# Presentation helpers shared by lists, search and exports
# --------------------------------------------------------------------------
def vitals_summary(rec: Dict[str, Any]) -> str:
    parts = []
    if not is_missing(rec.get("heart_rate")):
        parts.append(f"HR {display(rec['heart_rate'])} bpm")
    if not is_missing(rec.get("systolic_bp")) and not is_missing(rec.get("diastolic_bp")):
        parts.append(f"BP {display(rec['systolic_bp'])}/{display(rec['diastolic_bp'])} mmHg")
    if not is_missing(rec.get("weight_kg")):
        parts.append(f"{float(rec['weight_kg']):.1f} kg")
    if not is_missing(rec.get("spo2")):
        parts.append(f"SpO₂ {display(rec['spo2'])}%")
    return " · ".join(parts) or "No measurements recorded"


def record_title(kind: str, rec: Dict[str, Any]) -> str:
    if kind == "visit":
        return display(rec.get("reason_for_visit"), "Hospital visit")
    if kind == "diagnostic":
        return display(rec.get("scan_type"), "Diagnostic report")
    if kind in ("prescription", "history"):
        med = display(rec.get("medication"), "Medication")
        dose = rec.get("dosage")
        return f"{med} {display(dose)}" if not is_missing(dose) else med
    if kind == "appointment":
        return display(rec.get("type"), "Appointment")
    if kind == "vital":
        return "Vitals reading"
    return "Record"


def record_subtitle(kind: str, rec: Dict[str, Any]) -> str:
    def join(*vals):
        return " · ".join(display(v) for v in vals if not is_missing(v))
    if kind == "visit":
        return join(rec.get("hospital_name"), rec.get("department"), rec.get("attending_physician"))
    if kind == "diagnostic":
        return join(rec.get("facility"), rec.get("ordering_doctor"))
    if kind == "prescription":
        return join(rec.get("frequency"), rec.get("prescribing_doctor"))
    if kind == "history":
        return join(rec.get("reason"), rec.get("prescribed_by"))
    if kind == "appointment":
        return join(rec.get("time"), rec.get("doctor"), rec.get("facility"))
    if kind == "vital":
        return vitals_summary(rec)
    return ""


def record_status(kind: str, rec: Dict[str, Any]) -> str:
    if kind == "vital":
        return "Recorded"
    return display(rec.get("status"), "Not recorded")


def build_record_index(kinds: Optional[List[str]] = None) -> pd.DataFrame:
    """One row per record across every type, for the library, global search and activity feed."""
    rows = []
    for kind in kinds or list(RECORD_TYPES):
        rt = RECORD_TYPES[kind]
        df = get_df(kind)
        for rec in df.to_dict(orient="records"):
            d = rec.get(rt.date_col, "")
            text_parts = [str(rec.get(c, "")) for c in rt.search_cols if not is_missing(rec.get(c))]
            text_parts += [rt.label, rt.plural, str(d), format_date(d), record_title(kind, rec),
                           record_subtitle(kind, rec)]
            rows.append({
                "kind": kind,
                "type": rt.label,
                "record_id": rec[rt.id_col],
                "date": d,
                "title": record_title(kind, rec),
                "details": record_subtitle(kind, rec),
                "status": record_status(kind, rec),
                "_search": " ".join(text_parts).lower(),
            })
    index = pd.DataFrame(rows, columns=["kind", "type", "record_id", "date", "title", "details", "status", "_search"])
    if not index.empty:
        index = index.sort_values(["date", "record_id"], ascending=False, kind="stable").reset_index(drop=True)
    return index


def search_tokens(query: str) -> List[str]:
    return [t for t in re.split(r"\s+", (query or "").strip().lower()) if t]


def match_query(haystack: pd.Series, query: str) -> pd.Series:
    """Every word in the query must appear somewhere in the record (order-independent, literal match)."""
    mask = pd.Series(True, index=haystack.index)
    for token in search_tokens(query):
        mask &= haystack.str.contains(token, regex=False, na=False)
    return mask


def row_search_text(kind: str, df: pd.DataFrame) -> pd.Series:
    rt = RECORD_TYPES[kind]
    cols = [c for c in rt.search_cols if c in df.columns]
    if df.empty:
        return pd.Series([], dtype=object)
    dates = df[rt.date_col].map(lambda v: f"{v} {format_date(v)}")
    text = df[cols].astype(str).agg(" ".join, axis=1) + " " + dates
    if kind in ("prescription", "history") and "dosage" in df.columns:
        text = text + " " + df["dosage"].astype(str)
    return text.str.lower()


def suggestions(f: Field, current: Any = None) -> List[str]:
    """Options for a select field: fixed options plus values already used in the data."""
    seen: List[str] = []
    for opt in f.options:
        if opt not in seen:
            seen.append(opt)
    extra = set()
    for spec in f.suggest_from:
        state_key, col = spec.split(":")
        df = st.session_state.get(state_key)
        if df is not None and col in df.columns:
            extra.update(str(v).strip() for v in df[col].dropna() if str(v).strip())
    for v in sorted(extra):
        if v not in seen:
            seen.append(v)
    if not is_missing(current) and str(current) not in seen:
        seen.insert(0, str(current))
    return seen


def visit_label(visit_id: str) -> str:
    if is_missing(visit_id):
        return "No linked visit"
    rec = get_record("visit", visit_id)
    if rec is None:
        return f"{visit_id} (no longer available)"
    return f"{format_date(rec.get('date'))} · {display(rec.get('hospital_name'))} · {display(rec.get('reason_for_visit'))}"


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------
def validate(kind: str, values: Dict[str, Any], today: Optional[date] = None) -> Dict[str, str]:
    """Return {field_name: message} for every problem; empty when the record can be saved."""
    rt = RECORD_TYPES[kind]
    today = today or date.today()
    errors: Dict[str, str] = {}
    for f in rt.fields:
        v = values.get(f.name)
        if f.required and is_missing(v):
            errors[f.name] = f"Please enter {f.label.lower()}."
            continue
        if f.kind in ("date", "optional_date") and not is_missing(v):
            d = parse_date(v)
            if d is None:
                errors[f.name] = "Please choose a valid date."
            elif not f.allow_future and d > today:
                errors[f.name] = "This date is in the future. Please check it."
        if f.kind in ("number", "float") and not is_missing(v):
            try:
                num = float(v)
            except (TypeError, ValueError):
                errors[f.name] = "Please enter a number."
                continue
            if f.min_value is not None and num < f.min_value or f.max_value is not None and num > f.max_value:
                errors[f.name] = f"Please enter a value between {f.min_value:g} and {f.max_value:g}."
        if f.kind == "text" and isinstance(v, str) and len(v) > 200:
            errors[f.name] = "Please keep this under 200 characters."

    # Cross-field rules
    if kind in ("prescription", "history"):
        start, end = parse_date(values.get("start_date")), parse_date(values.get("end_date"))
        if start and end and end < start and "end_date" not in errors:
            errors["end_date"] = "The end date can't be before the start date."
    if kind == "vital":
        if all(is_missing(values.get(m)) for m in VITAL_MEASURES):
            errors["heart_rate"] = "Enter at least one measurement."
        sys_v, dia_v = values.get("systolic_bp"), values.get("diastolic_bp")
        if is_missing(sys_v) != is_missing(dia_v):
            key = "diastolic_bp" if is_missing(dia_v) else "systolic_bp"
            errors.setdefault(key, "Blood pressure needs both the top and bottom numbers.")
        elif not is_missing(sys_v) and not is_missing(dia_v) and float(sys_v) <= float(dia_v):
            errors.setdefault("systolic_bp", "The systolic (top) number should be higher than the diastolic.")
    return errors


def possible_duplicate(kind: str, values: Dict[str, Any], exclude_id: Optional[str] = None) -> Optional[str]:
    """ID of an existing record that looks identical (same date and title), to warn before saving twice."""
    rt = RECORD_TYPES[kind]
    df = get_df(kind)
    if df.empty:
        return None
    title = record_title(kind, values).lower()
    d = values.get(rt.date_col, "")
    for rec in df[df[rt.date_col] == d].to_dict(orient="records"):
        if rec[rt.id_col] != exclude_id and record_title(kind, rec).lower() == title:
            if kind != "vital" or vitals_summary(rec) == vitals_summary(values):
                return rec[rt.id_col]
    return None


def today_iso() -> str:
    return date.today().isoformat()
