"""Doctor appointments: plan the visit, note questions to ask, record what happened."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from medione import audit
from medione.db import connect, now_iso
from medione.models import APPOINTMENT_KINDS, APPOINTMENT_STATUSES
from medione.services.access import check_owned, require_profile, require_record
from medione.services.records import iso_date
from medione.services.reminders import _ics_escape

_SELECT = ("SELECT a.*, d.name AS doctor_name, d.specialty AS doctor_specialty, f.name AS facility_name, "
           "f.address AS facility_address, f.phone AS facility_phone FROM appointments a "
           "LEFT JOIN doctors d ON d.id = a.doctor_id LEFT JOIN facilities f ON f.id = a.facility_id ")


def save_appointment(user_id: int, profile_id: int, data: dict, appointment_id: Optional[int] = None) -> int:
    purpose = (data.get("purpose") or "").strip()
    if not purpose:
        raise ValueError("Say what the appointment is for.")
    starts = iso_date(data.get("starts_on"))
    if not starts:
        raise ValueError("Choose the appointment date.")
    kind = data.get("kind") or "consultation"
    if kind not in APPOINTMENT_KINDS:
        raise ValueError("Invalid appointment type.")
    status = data.get("status") or "upcoming"
    if status not in APPOINTMENT_STATUSES:
        raise ValueError("Invalid status.")
    time_of_day = (data.get("time_of_day") or "").strip() or None
    if time_of_day:
        try:
            datetime.strptime(time_of_day, "%H:%M")
        except ValueError as exc:
            raise ValueError("Time must look like 10:30.") from exc
    values = (starts, time_of_day, data.get("doctor_id") or None, data.get("facility_id") or None, purpose[:160], kind,
              status, (data.get("questions") or "").strip() or None, (data.get("notes") or "").strip() or None)
    with connect() as conn:
        require_profile(conn, user_id, profile_id)
        check_owned(conn, "doctors", user_id, values[2])
        check_owned(conn, "facilities", user_id, values[3])
        if appointment_id:
            _owned(conn, user_id, appointment_id)
            conn.execute("UPDATE appointments SET starts_on=?, time_of_day=?, doctor_id=?, facility_id=?, purpose=?, "
                         "kind=?, status=?, questions=?, notes=? WHERE id=?", (*values, appointment_id))
        else:
            appointment_id = conn.execute(
                "INSERT INTO appointments (profile_id, starts_on, time_of_day, doctor_id, facility_id, purpose, kind, "
                "status, questions, notes, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (profile_id, *values, now_iso())).lastrowid
        audit.log("appointment.saved", user_id, profile_id, target=f"appointment:{appointment_id}", conn=conn)
    return appointment_id


def _owned(conn, user_id: int, appointment_id: int):
    row = conn.execute("SELECT a.* FROM appointments a JOIN profiles p ON p.id = a.profile_id "
                       "WHERE a.id = ? AND p.user_id = ?", (appointment_id, user_id)).fetchone()
    if row is None:
        raise ValueError("Appointment not found.")
    return row


def set_status(user_id: int, appointment_id: int, status: str, outcome: str = "",
               record_id: Optional[int] = None) -> None:
    if status not in APPOINTMENT_STATUSES:
        raise ValueError("Invalid status.")
    with connect() as conn:
        row = _owned(conn, user_id, appointment_id)
        if record_id:
            rec = require_record(conn, user_id, record_id)
            if rec["profile_id"] != row["profile_id"]:
                raise ValueError("That record belongs to another profile.")
        conn.execute("UPDATE appointments SET status = ?, outcome = COALESCE(?, outcome), "
                     "record_id = COALESCE(?, record_id) WHERE id = ?",
                     (status, outcome.strip() or None, record_id, appointment_id))
        audit.log("appointment.status", user_id, row["profile_id"], target=f"appointment:{appointment_id}",
                  detail=status, conn=conn)


def delete_appointment(user_id: int, appointment_id: int) -> None:
    with connect() as conn:
        row = _owned(conn, user_id, appointment_id)
        conn.execute("DELETE FROM appointments WHERE id = ?", (appointment_id,))
        audit.log("appointment.deleted", user_id, row["profile_id"], target=f"appointment:{appointment_id}", conn=conn)


def list_appointments(user_id: int, profile_id: int, today: Optional[date] = None) -> dict:
    """Split into upcoming (incl. today), needs_update (past but still 'upcoming') and history."""
    today = (today or date.today()).isoformat()
    with connect() as conn:
        require_profile(conn, user_id, profile_id)
        rows = [dict(r) for r in conn.execute(_SELECT + "WHERE a.profile_id = ? ORDER BY a.starts_on, "
                                              "COALESCE(a.time_of_day, '')", (profile_id,))]
    upcoming = [r for r in rows if r["status"] == "upcoming" and r["starts_on"] >= today]
    needs_update = [r for r in rows if r["status"] == "upcoming" and r["starts_on"] < today]
    history = sorted([r for r in rows if r["status"] != "upcoming"], key=lambda r: r["starts_on"], reverse=True)
    for r in upcoming:
        r["days_away"] = (date.fromisoformat(r["starts_on"]) - date.fromisoformat(today)).days
    return {"upcoming": upcoming, "needs_update": needs_update, "history": history}


def get_appointment(user_id: int, appointment_id: int) -> dict:
    with connect() as conn:
        _owned(conn, user_id, appointment_id)
        return dict(conn.execute(_SELECT + "WHERE a.id = ?", (appointment_id,)).fetchone())


def appointment_ics(a: dict) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    d = date.fromisoformat(a["starts_on"]).strftime("%Y%m%d")
    start = f"DTSTART:{d}T{a['time_of_day'].replace(':', '')}00\r\nDURATION:PT30M" if a.get("time_of_day") \
        else f"DTSTART;VALUE=DATE:{d}"
    where = ", ".join(x for x in (a.get("facility_name"), a.get("facility_address")) if x)
    desc = " ".join(x for x in (f"Doctor: {a['doctor_name']}." if a.get("doctor_name") else "",
                                f"Questions: {a['questions']}" if a.get("questions") else "") if x)
    return "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Thought Medione//Appointments//EN", "BEGIN:VEVENT",
        f"UID:medione-appt-{a['id']}@thought-medione", f"DTSTAMP:{stamp}", start,
        f"SUMMARY:{_ics_escape(a['purpose'])}", f"LOCATION:{_ics_escape(where)}", f"DESCRIPTION:{_ics_escape(desc)}",
        "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_ics_escape(a['purpose'])}", "TRIGGER:-PT2H", "END:VALARM",
        "END:VEVENT", "END:VCALENDAR"]) + "\r\n"
