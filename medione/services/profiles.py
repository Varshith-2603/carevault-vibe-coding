"""Family profiles: each one holds its own separate records, timeline and links."""
from __future__ import annotations

from typing import Optional

from medione import audit, config
from medione.db import connect, now_iso
from medione.services.access import AccessDenied, require_profile

PROFILE_FIELDS = ("full_name", "relationship", "date_of_birth", "sex", "blood_group", "phone",
                  "emergency_contact_name", "emergency_contact_phone")


def list_profiles(user_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM profiles WHERE user_id = ? ORDER BY relationship != 'self', created_at", (user_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_profile(user_id: int, profile_id: int) -> dict:
    with connect() as conn:
        return dict(require_profile(conn, user_id, profile_id))


def create_profile(user_id: int, data: dict, consent_statement: str) -> int:
    if not (data.get("full_name") or "").strip():
        raise ValueError("Enter the person's full name.")
    if not consent_statement:
        raise ValueError("Confirm that you are authorised to manage this person's records.")
    if data.get("relationship") == "self":
        raise ValueError("Your own profile already exists. Choose the family relationship.")
    values = {k: (data.get(k) or None) for k in PROFILE_FIELDS}
    values["full_name"] = values["full_name"].strip()
    now = now_iso()
    with connect() as conn:
        cur = conn.execute(
            f"INSERT INTO profiles (user_id, {', '.join(PROFILE_FIELDS)}, consent_statement, consent_at, created_at) "
            f"VALUES (?, {', '.join('?' * len(PROFILE_FIELDS))}, ?, ?, ?)",
            (user_id, *values.values(), consent_statement, now, now),
        )
        audit.log("profile.created", user_id, cur.lastrowid, conn=conn)
        return cur.lastrowid


def update_profile(user_id: int, profile_id: int, data: dict) -> None:
    with connect() as conn:
        current = require_profile(conn, user_id, profile_id)
        values = {k: (data.get(k) if k in data else current[k]) for k in PROFILE_FIELDS}
        if not (values["full_name"] or "").strip():
            raise ValueError("Name can't be empty.")
        if current["relationship"] == "self":
            values["relationship"] = "self"
        elif values["relationship"] == "self":
            raise ValueError("Only the account holder's own profile can use 'self'.")
        conn.execute(
            f"UPDATE profiles SET {', '.join(f'{k} = ?' for k in PROFILE_FIELDS)} WHERE id = ?",
            (*[(v.strip() if isinstance(v, str) else v) or None for v in values.values()], profile_id),
        )
        audit.log("profile.updated", user_id, profile_id, conn=conn)


def delete_profile(user_id: int, profile_id: int) -> None:
    """Delete a family member's profile with all of its records and files."""
    with connect() as conn:
        row = require_profile(conn, user_id, profile_id)
        if row["relationship"] == "self":
            raise AccessDenied("Your own profile can only be removed by deleting the account.")
        storage = [r["storage_name"] for r in conn.execute(
            "SELECT storage_name FROM documents WHERE profile_id = ?", (profile_id,))]
        conn.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
        audit.log("profile.deleted", user_id, profile_id, conn=conn)
    for name in storage:
        path = config.settings.documents_dir / name
        if path.exists():
            path.unlink()


def self_profile_id(user_id: int) -> Optional[int]:
    with connect() as conn:
        row = conn.execute("SELECT id FROM profiles WHERE user_id = ? AND relationship = 'self'", (user_id,)).fetchone()
    return row["id"] if row else None
