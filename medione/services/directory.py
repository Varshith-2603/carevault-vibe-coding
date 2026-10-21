"""Doctors and healthcare facilities the user has dealt with."""
from __future__ import annotations

from typing import Optional

from medione import audit
from medione.db import connect, now_iso
from medione.services.access import AccessDenied, check_owned


def list_facilities(user_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT f.*, (SELECT COUNT(*) FROM records r WHERE r.facility_id = f.id) AS record_count "
            "FROM facilities f WHERE f.user_id = ? ORDER BY f.name COLLATE NOCASE", (user_id,)).fetchall()
    return [dict(r) for r in rows]


def list_doctors(user_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT d.*, f.name AS facility_name, "
            "(SELECT COUNT(*) FROM records r WHERE r.doctor_id = d.id) AS record_count, "
            "(SELECT MAX(r.record_date) FROM records r WHERE r.doctor_id = d.id) AS last_seen "
            "FROM doctors d LEFT JOIN facilities f ON f.id = d.facility_id "
            "WHERE d.user_id = ? ORDER BY d.name COLLATE NOCASE", (user_id,)).fetchall()
    return [dict(r) for r in rows]


def save_facility(user_id: int, data: dict, facility_id: Optional[int] = None) -> int:
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("Enter the facility name.")
    values = (name, data.get("kind") or "hospital", (data.get("address") or "").strip() or None,
              (data.get("phone") or "").strip() or None, (data.get("notes") or "").strip() or None)
    with connect() as conn:
        clash = conn.execute("SELECT id FROM facilities WHERE user_id = ? AND name = ? COLLATE NOCASE",
                             (user_id, name)).fetchone()
        if clash and clash["id"] != facility_id:
            raise ValueError(f"'{name}' is already in your list.")
        if facility_id:
            check_owned(conn, "facilities", user_id, facility_id)
            conn.execute("UPDATE facilities SET name=?, kind=?, address=?, phone=?, notes=? WHERE id=?",
                         (*values, facility_id))
        else:
            facility_id = conn.execute(
                "INSERT INTO facilities (user_id, name, kind, address, phone, notes, created_at) VALUES (?,?,?,?,?,?,?)",
                (user_id, *values, now_iso())).lastrowid
        audit.log("facility.saved", user_id, target=f"facility:{facility_id}", conn=conn)
    return facility_id


def save_doctor(user_id: int, data: dict, doctor_id: Optional[int] = None) -> int:
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("Enter the doctor's name.")
    facility_id = data.get("facility_id") or None
    values = (name, (data.get("specialty") or "").strip() or None, facility_id,
              (data.get("phone") or "").strip() or None, (data.get("email") or "").strip() or None,
              (data.get("notes") or "").strip() or None)
    with connect() as conn:
        check_owned(conn, "facilities", user_id, facility_id)
        if doctor_id:
            check_owned(conn, "doctors", user_id, doctor_id)
            conn.execute("UPDATE doctors SET name=?, specialty=?, facility_id=?, phone=?, email=?, notes=? WHERE id=?",
                         (*values, doctor_id))
        else:
            doctor_id = conn.execute(
                "INSERT INTO doctors (user_id, name, specialty, facility_id, phone, email, notes, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)", (user_id, *values, now_iso())).lastrowid
        audit.log("doctor.saved", user_id, target=f"doctor:{doctor_id}", conn=conn)
    return doctor_id


def delete_doctor(user_id: int, doctor_id: int) -> None:
    """Remove from the directory. Linked records keep their content; only the link is cleared."""
    with connect() as conn:
        check_owned(conn, "doctors", user_id, doctor_id)
        conn.execute("DELETE FROM doctors WHERE id = ?", (doctor_id,))
        audit.log("doctor.deleted", user_id, target=f"doctor:{doctor_id}", conn=conn)


def delete_facility(user_id: int, facility_id: int) -> None:
    with connect() as conn:
        check_owned(conn, "facilities", user_id, facility_id)
        conn.execute("DELETE FROM facilities WHERE id = ?", (facility_id,))
        audit.log("facility.deleted", user_id, target=f"facility:{facility_id}", conn=conn)


def find_or_create_doctor(user_id: int, name: str, facility_id: Optional[int] = None) -> Optional[int]:
    """Match a doctor by exact name (case-insensitive); create a minimal entry if new.

    Only the name written on the document is stored — no specialty or credentials are guessed.
    """
    name = (name or "").strip()
    if not name:
        return None
    with connect() as conn:
        row = conn.execute("SELECT id FROM doctors WHERE user_id = ? AND name = ? COLLATE NOCASE",
                           (user_id, name)).fetchone()
    if row:
        return row["id"]
    return save_doctor(user_id, {"name": name, "facility_id": facility_id})


def find_or_create_facility(user_id: int, name: str) -> Optional[int]:
    name = (name or "").strip()
    if not name:
        return None
    with connect() as conn:
        row = conn.execute("SELECT id FROM facilities WHERE user_id = ? AND name = ? COLLATE NOCASE",
                           (user_id, name)).fetchone()
    if row:
        return row["id"]
    return save_facility(user_id, {"name": name})


def get_doctor(user_id: int, doctor_id: int) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT d.*, f.name AS facility_name FROM doctors d LEFT JOIN facilities f "
                           "ON f.id = d.facility_id WHERE d.id = ? AND d.user_id = ?", (doctor_id, user_id)).fetchone()
    if row is None:
        raise AccessDenied("Doctor not found.")
    return dict(row)
