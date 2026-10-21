"""Ownership checks shared by all services."""
from __future__ import annotations

import sqlite3


class AccessDenied(PermissionError):
    """Raised when a user asks for data that does not belong to them."""


def require_profile(conn: sqlite3.Connection, user_id: int, profile_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM profiles WHERE id = ? AND user_id = ?", (profile_id, user_id)).fetchone()
    if row is None:
        raise AccessDenied("Profile not found.")
    return row


def require_record(conn: sqlite3.Connection, user_id: int, record_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT r.* FROM records r JOIN profiles p ON p.id = r.profile_id WHERE r.id = ? AND p.user_id = ?",
        (record_id, user_id),
    ).fetchone()
    if row is None:
        raise AccessDenied("Record not found.")
    return row


def require_document(conn: sqlite3.Connection, user_id: int, document_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT d.* FROM documents d JOIN profiles p ON p.id = d.profile_id WHERE d.id = ? AND p.user_id = ?",
        (document_id, user_id),
    ).fetchone()
    if row is None:
        raise AccessDenied("Document not found.")
    return row


def check_owned(conn: sqlite3.Connection, table: str, user_id: int, row_id: int | None) -> None:
    """Doctors and facilities belong to the user; reject ids from other accounts."""
    if row_id is None:
        return
    assert table in {"doctors", "facilities"}
    if conn.execute(f"SELECT 1 FROM {table} WHERE id = ? AND user_id = ?", (row_id, user_id)).fetchone() is None:
        raise AccessDenied("Not found.")
