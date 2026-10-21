"""Medical records with their medicines, lab values and attached documents."""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Iterable, Optional

from medione import audit, config
from medione.db import connect, now_iso
from medione.models import MED_STATUSES, RECORD_TYPES, USER_SETTABLE_SOURCES
from medione.services.access import check_owned, require_profile, require_record

RECORD_COLUMNS = ("type", "title", "record_date", "end_date", "doctor_id", "facility_id", "condition",
                  "summary", "notes", "follow_up_date", "status", "source")
MED_COLUMNS = ("name", "dosage", "frequency", "duration", "route", "instructions", "start_date", "end_date",
               "status", "uncertain", "uncertain_note")
LAB_COLUMNS = ("test_name", "value_num", "value_text", "unit", "ref_low", "ref_high", "ref_text", "uncertain")


def iso_date(value: Any) -> Optional[str]:
    """Normalise a date-like value to YYYY-MM-DD, or None. Raises ValueError on garbage."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return date.fromisoformat(text[:10]).isoformat()


def _clean(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _num(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def validate_record(data: dict) -> dict:
    rtype = data.get("type")
    if rtype not in RECORD_TYPES:
        raise ValueError("Choose a record type.")
    title = _clean(data.get("title"))
    if not title:
        raise ValueError("Give the record a short title.")
    try:
        record_date = iso_date(data.get("record_date"))
        end_date = iso_date(data.get("end_date"))
        follow_up = iso_date(data.get("follow_up_date"))
    except ValueError as exc:
        raise ValueError("One of the dates isn't a valid date.") from exc
    if record_date and end_date and end_date < record_date:
        raise ValueError("The end / discharge date is before the start date.")
    source = data.get("source") or "patient"
    if source not in USER_SETTABLE_SOURCES:
        raise ValueError("Invalid record source.")
    details = {k: _clean(v) for k, v in (data.get("details") or {}).items()}
    for k, v in list(details.items()):
        if isinstance(v, (date, datetime)):
            details[k] = iso_date(v)
    return {
        "type": rtype, "title": title, "record_date": record_date, "end_date": end_date,
        "doctor_id": data.get("doctor_id") or None, "facility_id": data.get("facility_id") or None,
        "condition": _clean(data.get("condition")), "summary": _clean(data.get("summary")),
        "notes": _clean(data.get("notes")), "follow_up_date": follow_up, "status": _clean(data.get("status")),
        "source": source, "details_json": json.dumps({k: v for k, v in details.items() if v is not None}),
    }


def _clean_med(m: dict, default_date: Optional[str]) -> Optional[dict]:
    name = _clean(m.get("name"))
    if not name:
        return None
    status = m.get("status") or "active"
    return {
        "name": name, "dosage": _clean(m.get("dosage")), "frequency": _clean(m.get("frequency")),
        "duration": _clean(m.get("duration")), "route": _clean(m.get("route")),
        "instructions": _clean(m.get("instructions")),
        "start_date": iso_date(m.get("start_date")) or default_date, "end_date": iso_date(m.get("end_date")),
        "status": status if status in MED_STATUSES else "active",
        "uncertain": 1 if m.get("uncertain") else 0, "uncertain_note": _clean(m.get("uncertain_note")),
    }


def _clean_lab(l: dict) -> Optional[dict]:
    name = _clean(l.get("test_name"))
    if not name:
        return None
    raw_value = l.get("value_text") if l.get("value_text") not in (None, "") else l.get("value_num")
    value_num = _num(l.get("value_num")) if l.get("value_num") not in (None, "") else _num(raw_value)
    return {
        "test_name": name, "value_num": value_num,
        "value_text": _clean(str(raw_value)) if raw_value not in (None, "") else None,
        "unit": _clean(l.get("unit")), "ref_low": _num(l.get("ref_low")), "ref_high": _num(l.get("ref_high")),
        "ref_text": _clean(l.get("ref_text")), "uncertain": 1 if l.get("uncertain") else 0,
    }


def save_record(user_id: int, profile_id: int, data: dict, medications: Optional[Iterable[dict]] = None,
                lab_results: Optional[Iterable[dict]] = None, record_id: Optional[int] = None) -> int:
    """Create or update a record. Passing ``medications``/``lab_results`` replaces that list."""
    values = validate_record(data)
    now = now_iso()
    with connect() as conn:
        require_profile(conn, user_id, profile_id)
        check_owned(conn, "doctors", user_id, values["doctor_id"])
        check_owned(conn, "facilities", user_id, values["facility_id"])
        if record_id:
            existing = require_record(conn, user_id, record_id)
            if existing["profile_id"] != profile_id:
                raise ValueError("A record can't be moved to another profile.")
            before = _snapshot(conn, record_id)
            if existing["source"] == "clinician_verified":
                values["source"] = "clinician_verified"
            cols = (*RECORD_COLUMNS, "details_json")
            conn.execute(f"UPDATE records SET {', '.join(f'{c} = ?' for c in cols)}, updated_at = ? WHERE id = ?",
                         (*[values[c] for c in cols], now, record_id))
            action = "record.updated"
        else:
            cols = (*RECORD_COLUMNS, "details_json")
            record_id = conn.execute(
                f"INSERT INTO records (profile_id, {', '.join(cols)}, created_at, updated_at) "
                f"VALUES (?, {', '.join('?' * len(cols))}, ?, ?)",
                (profile_id, *[values[c] for c in cols], now, now)).lastrowid
            action = "record.created"
            before = None
        if medications is not None:
            conn.execute("DELETE FROM medications WHERE record_id = ?", (record_id,))
            for m in medications:
                med = _clean_med(m, values["record_date"])
                if med:
                    conn.execute(f"INSERT INTO medications (record_id, profile_id, {', '.join(MED_COLUMNS)}) "
                                 f"VALUES (?, ?, {', '.join('?' * len(MED_COLUMNS))})",
                                 (record_id, profile_id, *med.values()))
        if lab_results is not None:
            conn.execute("DELETE FROM lab_results WHERE record_id = ?", (record_id,))
            for l in lab_results:
                lab = _clean_lab(l)
                if lab:
                    conn.execute(f"INSERT INTO lab_results (record_id, profile_id, {', '.join(LAB_COLUMNS)}) "
                                 f"VALUES (?, ?, {', '.join('?' * len(LAB_COLUMNS))})",
                                 (record_id, profile_id, *lab.values()))
        _record_history(conn, user_id, record_id, before, _snapshot(conn, record_id))
        audit.log(action, user_id, profile_id, target=f"record:{record_id}", conn=conn)
    return record_id


# ------------------------------------------------------------ change history
HISTORY_LABELS = {"type": "Type", "title": "Title", "record_date": "Date", "end_date": "End date",
                  "doctor_id": "Doctor", "facility_id": "Facility", "condition": "Condition", "summary": "Summary",
                  "notes": "Notes", "follow_up_date": "Follow-up date", "status": "Status", "source": "Source",
                  "medications": "Medicines", "lab_results": "Test results"}


def _snapshot(conn, record_id: int) -> dict:
    row = dict(conn.execute("SELECT r.*, d.name AS doctor_name, f.name AS facility_name FROM records r "
                            "LEFT JOIN doctors d ON d.id = r.doctor_id LEFT JOIN facilities f ON f.id = r.facility_id "
                            "WHERE r.id = ?", (record_id,)).fetchone())
    snap = {k: row[k] for k in RECORD_COLUMNS}
    snap["doctor_id"], snap["facility_id"] = row["doctor_name"], row["facility_name"]
    for k, v in json.loads(row["details_json"] or "{}").items():
        snap[f"details.{k}"] = v
    snap["medications"] = "; ".join(
        " ".join(x for x in (m["name"], m["dosage"], m["frequency"], m["duration"]) if x)
        + (" [needs checking]" if m["uncertain"] else "")
        for m in conn.execute("SELECT * FROM medications WHERE record_id = ? ORDER BY id", (record_id,))) or None
    snap["lab_results"] = "; ".join(
        f"{l['test_name']} {l['value_text'] or l['value_num'] or ''} {l['unit'] or ''}".strip()
        for l in conn.execute("SELECT * FROM lab_results WHERE record_id = ? ORDER BY id", (record_id,))) or None
    return snap


def _record_history(conn, user_id: int, record_id: int, before: Optional[dict], after: dict,
                    summary: str = "") -> None:
    if before is None:
        changes = [{"field": "source", "before": None, "after": after.get("source")}]
        summary = summary or "Record created"
    else:
        changes = [{"field": k, "before": before.get(k), "after": after.get(k)}
                   for k in sorted(set(before) | set(after)) if before.get(k) != after.get(k)]
        if not changes:
            return
        summary = summary or "Edited: " + ", ".join(
            HISTORY_LABELS.get(c["field"], c["field"].replace("details.", "").replace("_", " ").capitalize())
            for c in changes)
    conn.execute("INSERT INTO record_history (record_id, user_id, changed_at, summary, changes_json) VALUES (?,?,?,?,?)",
                 (record_id, user_id, now_iso(), summary[:300], json.dumps(changes, default=str)))


def record_history(user_id: int, record_id: int) -> list[dict]:
    with connect() as conn:
        require_record(conn, user_id, record_id)
        rows = [dict(r) for r in conn.execute(
            "SELECT changed_at, summary, changes_json FROM record_history WHERE record_id = ? ORDER BY id DESC",
            (record_id,))]
    for r in rows:
        r["changes"] = json.loads(r.pop("changes_json"))
    return rows


def get_record(user_id: int, record_id: int) -> dict:
    with connect() as conn:
        require_record(conn, user_id, record_id)
        row = conn.execute(
            "SELECT r.*, d.name AS doctor_name, d.specialty AS doctor_specialty, f.name AS facility_name "
            "FROM records r LEFT JOIN doctors d ON d.id = r.doctor_id LEFT JOIN facilities f ON f.id = r.facility_id "
            "WHERE r.id = ?", (record_id,)).fetchone()
        rec = dict(row)
        rec["details"] = json.loads(rec.pop("details_json") or "{}")
        rec["medications"] = [dict(r) for r in conn.execute(
            "SELECT * FROM medications WHERE record_id = ? ORDER BY id", (record_id,))]
        rec["lab_results"] = [dict(r) for r in conn.execute(
            "SELECT * FROM lab_results WHERE record_id = ? ORDER BY id", (record_id,))]
        rec["documents"] = [dict(r) for r in conn.execute(
            "SELECT id, filename, mime, size, uploaded_at, ai_summary, ai_summary_at, "
            "extracted_text IS NOT NULL AS has_text FROM documents WHERE record_id = ? ORDER BY id", (record_id,))]
    return rec


def mark_reviewed(user_id: int, record_id: int) -> None:
    """The user has checked AI-extracted values against the original document."""
    with connect() as conn:
        row = require_record(conn, user_id, record_id)
        if row["source"] in ("ai_extracted", "auto_extracted"):
            before = _snapshot(conn, record_id)
            conn.execute("UPDATE records SET source = 'patient_confirmed', updated_at = ? WHERE id = ?",
                         (now_iso(), record_id))
            conn.execute("UPDATE medications SET uncertain = 0 WHERE record_id = ?", (record_id,))
            conn.execute("UPDATE lab_results SET uncertain = 0 WHERE record_id = ?", (record_id,))
            _record_history(conn, user_id, record_id, before, _snapshot(conn, record_id),
                            "Checked against the original document and confirmed")
            audit.log("record.reviewed", user_id, row["profile_id"], target=f"record:{record_id}", conn=conn)


def delete_record(user_id: int, record_id: int, delete_files: bool = False) -> None:
    with connect() as conn:
        row = require_record(conn, user_id, record_id)
        storage = []
        if delete_files:
            storage = [r["storage_name"] for r in conn.execute(
                "SELECT storage_name FROM documents WHERE record_id = ?", (record_id,))]
            conn.execute("DELETE FROM documents WHERE record_id = ?", (record_id,))
        conn.execute("DELETE FROM records WHERE id = ?", (record_id,))
        conn.execute("DELETE FROM duplicate_dismissals WHERE record_a = ? OR record_b = ?", (record_id, record_id))
        audit.log("record.deleted", user_id, row["profile_id"], target=f"record:{record_id}",
                  detail="with files" if delete_files else "files kept", conn=conn)
    for name in storage:
        path = config.settings.documents_dir / name
        if path.exists():
            path.unlink()


def list_medications(user_id: int, profile_id: int, status: Optional[str] = None) -> list[dict]:
    sql = ("SELECT m.*, r.title AS record_title, r.record_date AS prescribed_on, d.name AS doctor_name "
           "FROM medications m LEFT JOIN records r ON r.id = m.record_id LEFT JOIN doctors d ON d.id = r.doctor_id "
           "WHERE m.profile_id = ?")
    params: list = [profile_id]
    if status:
        sql += " AND m.status = ?"
        params.append(status)
    sql += " ORDER BY m.status = 'active' DESC, COALESCE(m.start_date, r.record_date) DESC"
    with connect() as conn:
        require_profile(conn, user_id, profile_id)
        return [dict(r) for r in conn.execute(sql, params)]


def set_medication_status(user_id: int, medication_id: int, status: str, end_date: Optional[str] = None) -> None:
    """Record what the patient reports (e.g. course finished). This app never changes treatment."""
    if status not in MED_STATUSES:
        raise ValueError("Unknown status.")
    with connect() as conn:
        row = conn.execute("SELECT m.profile_id FROM medications m JOIN profiles p ON p.id = m.profile_id "
                           "WHERE m.id = ? AND p.user_id = ?", (medication_id, user_id)).fetchone()
        if row is None:
            raise ValueError("Medicine not found.")
        conn.execute("UPDATE medications SET status = ?, end_date = COALESCE(?, end_date) WHERE id = ?",
                     (status, iso_date(end_date), medication_id))
        audit.log("medication.status", user_id, row["profile_id"], target=f"medication:{medication_id}",
                  detail=status, conn=conn)


def list_lab_results(user_id: int, profile_id: int) -> list[dict]:
    with connect() as conn:
        require_profile(conn, user_id, profile_id)
        rows = conn.execute(
            "SELECT l.*, r.record_date, r.title AS record_title, f.name AS facility_name FROM lab_results l "
            "JOIN records r ON r.id = l.record_id LEFT JOIN facilities f ON f.id = r.facility_id "
            "WHERE l.profile_id = ? ORDER BY l.test_name COLLATE NOCASE, r.record_date", (profile_id,)).fetchall()
    return [dict(r) for r in rows]


def profile_counts(user_id: int, profile_id: int) -> dict:
    with connect() as conn:
        require_profile(conn, user_id, profile_id)
        by_type = {r["type"]: r["n"] for r in conn.execute(
            "SELECT type, COUNT(*) AS n FROM records WHERE profile_id = ? GROUP BY type", (profile_id,))}
        docs = conn.execute("SELECT COUNT(*) FROM documents WHERE profile_id = ?", (profile_id,)).fetchone()[0]
        active_meds = conn.execute("SELECT COUNT(*) FROM medications WHERE profile_id = ? AND status = 'active'",
                                   (profile_id,)).fetchone()[0]
        unreviewed = conn.execute("SELECT COUNT(*) FROM records WHERE profile_id = ? AND source IN ('ai_extracted', 'auto_extracted')",
                                  (profile_id,)).fetchone()[0]
    return {"by_type": by_type, "total": sum(by_type.values()), "documents": docs,
            "active_medications": active_meds, "unreviewed": unreviewed}


def upcoming_follow_ups(user_id: int, profile_id: int, today: Optional[date] = None) -> list[dict]:
    today = today or date.today()
    with connect() as conn:
        require_profile(conn, user_id, profile_id)
        rows = conn.execute(
            "SELECT r.id, r.title, r.type, r.follow_up_date, d.name AS doctor_name FROM records r "
            "LEFT JOIN doctors d ON d.id = r.doctor_id WHERE r.profile_id = ? AND r.follow_up_date >= ? "
            "ORDER BY r.follow_up_date LIMIT 10", (profile_id, today.isoformat())).fetchall()
    return [dict(r) for r in rows]
