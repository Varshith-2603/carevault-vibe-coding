"""Record types, categories and provenance labels used across the app."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class Extra:
    """A type-specific field stored in ``records.details_json``."""
    name: str
    label: str
    kind: str = "text"  # text | textarea | select | date
    options: Tuple[str, ...] = ()
    help: str = ""


@dataclass(frozen=True)
class RecordType:
    key: str
    label: str
    category: str
    icon: str
    date_label: str = "Date"
    end_date_label: str = ""
    extras: Tuple[Extra, ...] = ()
    has_medications: bool = False
    has_lab_results: bool = False


CATEGORIES: Dict[str, str] = {
    "visits": "Consultations & admissions",
    "prescriptions": "Prescriptions",
    "reports": "Reports & scans",
    "history": "Medical history",
    "documents": "Other documents",
    "insurance": "Insurance & bills",
}

RECORD_TYPES: Dict[str, RecordType] = {t.key: t for t in [
    RecordType("consultation", "Doctor consultation", "visits", ":material/stethoscope:", "Consultation date"),
    RecordType("admission", "Hospital admission / discharge summary", "visits", ":material/local_hospital:",
               "Admission date", "Discharge date",
               (Extra("discharge_instructions", "Discharge instructions (as written)", "textarea"),)),
    RecordType("prescription", "Prescription", "prescriptions", ":material/prescriptions:", "Prescription date",
               extras=(Extra("doctor_instructions", "Doctor's instructions (as written)", "textarea"),),
               has_medications=True),
    RecordType("lab_report", "Blood test / laboratory report", "reports", ":material/biotech:", "Sample / test date",
               extras=(Extra("lab_name", "Test panel name", help="For example: Complete blood count"),),
               has_lab_results=True),
    RecordType("imaging", "Imaging report (X-ray, CT, MRI, ultrasound)", "reports", ":material/radiology:",
               "Examination date", extras=(
                   Extra("modality", "Imaging type", "select", ("X-ray", "CT scan", "MRI", "Ultrasound", "Mammogram", "PET scan", "Other")),
                   Extra("body_part", "Body part examined"),
                   Extra("findings", "Findings (as written)", "textarea"),
                   Extra("impression", "Impression (as written)", "textarea"),
               )),
    RecordType("ecg", "ECG / cardiac test", "reports", ":material/monitor_heart:", "Test date",
               extras=(Extra("findings", "Findings (as written)", "textarea"),)),
    RecordType("other_diagnostic", "Other diagnostic report", "reports", ":material/lab_profile:", "Test date",
               extras=(Extra("findings", "Findings (as written)", "textarea"),)),
    RecordType("diagnosis", "Diagnosis documented by a doctor", "history", ":material/clinical_notes:", "Date diagnosed",
               extras=(Extra("diagnosis_status", "Current status", "select", ("Active", "Resolved", "Not recorded")),)),
    RecordType("surgery", "Surgery", "history", ":material/surgical:", "Surgery date",
               extras=(Extra("procedure_name", "Procedure name"), Extra("outcome", "Outcome / notes from the doctor", "textarea"))),
    RecordType("procedure", "Medical procedure", "history", ":material/healing:", "Procedure date",
               extras=(Extra("procedure_name", "Procedure name"),)),
    RecordType("vaccination", "Vaccination", "history", ":material/vaccines:", "Date given",
               extras=(Extra("vaccine", "Vaccine"), Extra("dose", "Dose (e.g. 1st, booster)"),
                       Extra("batch", "Batch / lot number"),
                       Extra("next_dose_date", "Next dose due (if written on the card)", "date"))),
    RecordType("allergy", "Allergy", "history", ":material/allergy:", "Date recorded",
               extras=(Extra("allergen", "Allergic to"), Extra("reaction", "Reaction"),
                       Extra("severity", "Severity (if documented)", "select", ("Mild", "Moderate", "Severe", "Not recorded")))),
    RecordType("family_history", "Family medical history", "history", ":material/family_restroom:", "Date recorded",
               extras=(Extra("relative", "Relative (e.g. mother, grandfather)"),)),
    RecordType("referral", "Referral letter", "documents", ":material/forward_to_inbox:", "Letter date",
               extras=(Extra("referred_to", "Referred to"),)),
    RecordType("certificate", "Medical certificate", "documents", ":material/workspace_premium:", "Issue date",
               extras=(Extra("purpose", "Purpose"),)),
    RecordType("other", "Other medical document", "documents", ":material/description:", "Document date"),
    RecordType("insurance", "Health insurance policy", "insurance", ":material/health_and_safety:", "Policy start date",
               "Valid until", (Extra("insurer", "Insurer"), Extra("policy_number", "Policy / card number"),
                               Extra("sum_insured", "Sum insured"), Extra("tpa", "TPA / helpline"))),
    RecordType("bill", "Hospital / pharmacy bill", "insurance", ":material/receipt_long:", "Bill date",
               extras=(Extra("bill_number", "Bill number"), Extra("amount", "Amount (₹)"),
                       Extra("claim_status", "Insurance claim", "select",
                             ("Not claimed", "Claim submitted", "Claim settled", "Claim rejected", "Not applicable")))),
]}

TIMELINE_EVENT_TYPES = list(RECORD_TYPES)


def types_in(category: str) -> List[str]:
    return [k for k, t in RECORD_TYPES.items() if t.category == category]


def type_label(key: str) -> str:
    t = RECORD_TYPES.get(key)
    return t.label if t else key.replace("_", " ").title()


# Where a piece of information came from. "clinician_verified" is reserved for a
# future verified-provider integration; patients cannot set it in this app.
SOURCES: Dict[str, Tuple[str, str]] = {
    "patient": ("Entered by you", "gray"),
    "ai_extracted": ("AI-extracted · not yet reviewed", "orange"),
    "auto_extracted": ("Auto-read from document · not yet reviewed", "orange"),
    "patient_confirmed": ("Read from document · reviewed by you", "blue"),
    "clinician_verified": ("Verified by a clinician", "green"),
}
USER_SETTABLE_SOURCES = ("patient", "ai_extracted", "auto_extracted", "patient_confirmed")
UNREVIEWED_SOURCES = ("ai_extracted", "auto_extracted")

RELATIONSHIPS = ("self", "spouse / partner", "child", "parent", "sibling", "grandparent", "other dependent")
FACILITY_KINDS = ("hospital", "clinic", "diagnostic centre", "pharmacy", "other")
REMINDER_KINDS = {
    "medication": "Medicine",
    "appointment": "Follow-up / appointment",
    "test": "Scheduled test",
    "checkup": "Routine check-up",
    "vaccination": "Vaccination",
    "other": "Other",
}
REPEATS = {"none": "Does not repeat", "daily": "Every day", "weekly": "Every week",
           "monthly": "Every month", "yearly": "Every year"}
BLOOD_GROUPS = ("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-", "Unknown")
SEXES = ("Female", "Male", "Intersex", "Prefer not to say")
MED_STATUSES = ("active", "completed", "stopped")

APPOINTMENT_KINDS = {"consultation": "Consultation", "follow_up": "Follow-up", "test": "Test / scan",
                     "procedure": "Procedure", "vaccination": "Vaccination", "teleconsult": "Video / phone consult"}
APPOINTMENT_STATUSES = {"upcoming": "Upcoming", "completed": "Completed", "cancelled": "Cancelled", "missed": "Missed"}

SEVERITY = {1: "Mild", 2: "Moderate", 3: "Severe"}


@dataclass(frozen=True)
class VitalKind:
    key: str
    label: str
    unit: str
    icon: str
    two_values: bool = False
    contexts: Tuple[str, ...] = ()
    # General adult reference used only to highlight readings worth discussing with a doctor.
    low: float | None = None
    high: float | None = None
    low2: float | None = None
    high2: float | None = None
    reference: str = ""


VITAL_KINDS: Dict[str, VitalKind] = {k.key: k for k in [
    VitalKind("bp", "Blood pressure", "mmHg", ":material/blood_pressure:", True, (), 90, 139, 60, 89,
              "General adult reference: below 140/90 mmHg."),
    VitalKind("sugar", "Blood sugar", "mg/dL", ":material/glucose:", False, ("Fasting", "After meal (2 h)", "Random"),
              70, None, reference="General reference: fasting 70–99, 2 h after a meal below 140 mg/dL."),
    VitalKind("pulse", "Pulse", "bpm", ":material/ecg_heart:", False, (), 60, 100,
              reference="General resting adult reference: 60–100 bpm."),
    VitalKind("spo2", "Oxygen (SpO₂)", "%", ":material/spo2:", False, (), 95, None,
              reference="General reference: 95% or higher at rest."),
    VitalKind("temp", "Temperature", "°C", ":material/thermometer:", False, (), 35.5, 37.9,
              reference="Fever is generally 38 °C or higher."),
    VitalKind("weight", "Weight", "kg", ":material/monitor_weight:"),
]}
SUGAR_HIGH = {"Fasting": 99, "After meal (2 h)": 139, "Random": 199}

ALLOWED_UPLOAD_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
UPLOAD_EXTENSIONS = ["pdf", "jpg", "jpeg", "png", "webp"]
