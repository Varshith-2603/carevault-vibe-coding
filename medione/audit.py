"""Append-only audit trail of security-relevant actions.

Entries name the action and the record/link id only. They never contain
passwords, tokens, file contents or medical details.
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from medione.db import connect, now_iso


def log(action: str, user_id: Optional[int] = None, profile_id: Optional[int] = None,
        target: str = "", detail: str = "", conn: Optional[sqlite3.Connection] = None) -> None:
    sql = "INSERT INTO audit_log (user_id, profile_id, action, target, detail, at) VALUES (?, ?, ?, ?, ?, ?)"
    params = (user_id, profile_id, action, target, detail[:300], now_iso())
    if conn is not None:
        conn.execute(sql, params)
        return
    with connect() as c:
        c.execute(sql, params)


def recent(user_id: int, limit: int = 200) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT action, target, detail, at, profile_id FROM audit_log WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]
