"""Time-limited, revocable, read-only links to records the user picked.

Only the SHA-256 of a link token is stored. Every visit re-checks expiry,
revocation and that each record still belongs to the shared profile, and only
the selected records (and their files) are ever returned.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Iterable

from medione import audit, config, security
from medione.db import connect, now_iso
from medione.services.access import require_profile
from medione.services.documents import read_document_unchecked
from medione.services.search import record_payload

EXPIRY_CHOICES = {"1 hour": 1, "24 hours": 24, "3 days": 72, "7 days": 168, "30 days": 720}


class ShareUnavailable(Exception):
    """The link is invalid, expired or revoked (message is safe to show)."""


def share_url(token: str) -> str:
    return f"{config.settings.base_url}/?share={token}"


def create_share(user_id: int, profile_id: int, record_ids: Iterable[int], label: str, hours: int,
                 include_summary: bool = False, include_files: bool = True) -> tuple[int, str]:
    ids = sorted({int(i) for i in record_ids})
    label = (label or "").strip()
    if not ids:
        raise ValueError("Select at least one record to share.")
    if not label:
        raise ValueError("Say who the link is for, e.g. 'Dr. Iyer – cardiology visit'.")
    if hours not in EXPIRY_CHOICES.values():
        raise ValueError("Choose how long the link stays valid.")
    token = security.new_share_token()
    expires = (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(microsecond=0).isoformat()
    with connect() as conn:
        require_profile(conn, user_id, profile_id)
        found = conn.execute(f"SELECT COUNT(*) FROM records WHERE profile_id = ? AND id IN ({', '.join('?' * len(ids))})",
                             (profile_id, *ids)).fetchone()[0]
        if found != len(ids):
            raise ValueError("Some selected records don't belong to this profile.")
        share_id = conn.execute(
            "INSERT INTO share_links (user_id, profile_id, token_hash, label, record_ids_json, include_summary, "
            "include_files, expires_at, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (user_id, profile_id, security.token_hash(token), label[:120], json.dumps(ids), int(include_summary),
             int(include_files), expires, now_iso())).lastrowid
        audit.log("share.created", user_id, profile_id, target=f"share:{share_id}",
                  detail=f"{len(ids)} records, expires {expires}", conn=conn)
    return share_id, token


def list_shares(user_id: int, profile_id: int) -> list[dict]:
    with connect() as conn:
        require_profile(conn, user_id, profile_id)
        rows = [dict(r) for r in conn.execute(
            "SELECT id, label, record_ids_json, include_summary, include_files, expires_at, revoked_at, created_at, "
            "access_count, last_access_at FROM share_links WHERE profile_id = ? AND user_id = ? ORDER BY id DESC",
            (profile_id, user_id))]
    now = datetime.now(timezone.utc)
    for r in rows:
        r["record_ids"] = json.loads(r.pop("record_ids_json"))
        r["state"] = ("revoked" if r["revoked_at"] else
                      "expired" if datetime.fromisoformat(r["expires_at"]) <= now else "active")
    return rows


def revoke(user_id: int, share_id: int) -> None:
    with connect() as conn:
        row = conn.execute("SELECT profile_id FROM share_links WHERE id = ? AND user_id = ?",
                           (share_id, user_id)).fetchone()
        if row is None:
            raise ValueError("Link not found.")
        conn.execute("UPDATE share_links SET revoked_at = COALESCE(revoked_at, ?) WHERE id = ?", (now_iso(), share_id))
        audit.log("share.revoked", user_id, row["profile_id"], target=f"share:{share_id}", conn=conn)


def access_log(user_id: int, share_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT action, detail, at FROM audit_log WHERE user_id = ? AND target = ? "
                            "ORDER BY id DESC LIMIT 100", (user_id, f"share:{share_id}")).fetchall()
    return [dict(r) for r in rows]


def _load_share(conn, token: str):
    if not token or len(token) > 100:
        raise ShareUnavailable("This link isn't valid.")
    row = conn.execute("SELECT * FROM share_links WHERE token_hash = ?", (security.token_hash(token),)).fetchone()
    if row is None:
        raise ShareUnavailable("This link isn't valid.")
    if row["revoked_at"]:
        raise ShareUnavailable("The person who shared this link has turned it off.")
    if datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
        raise ShareUnavailable("This link has expired. Ask the patient for a new one.")
    return row


def open_share(token: str, log_visit: bool = True) -> dict:
    """Everything a recipient may see for this token — nothing more."""
    with connect() as conn:
        share = _load_share(conn, token)
        ids = json.loads(share["record_ids_json"]) or [-1]
        marks = ", ".join("?" * len(ids))
        profile = conn.execute("SELECT full_name, date_of_birth, sex, blood_group FROM profiles WHERE id = ?",
                               (share["profile_id"],)).fetchone()
        records = [record_payload(dict(r)) for r in conn.execute(
            f"SELECT r.*, d.name AS doctor_name, f.name AS facility_name FROM records r "
            f"LEFT JOIN doctors d ON d.id = r.doctor_id LEFT JOIN facilities f ON f.id = r.facility_id "
            f"WHERE r.profile_id = ? AND r.id IN ({marks}) ORDER BY r.record_date DESC", (share["profile_id"], *ids))]
        live_ids = [r["id"] for r in records] or [-1]
        live_marks = ", ".join("?" * len(live_ids))
        meds = [dict(r) for r in conn.execute(f"SELECT * FROM medications WHERE record_id IN ({live_marks})", live_ids)]
        labs = [dict(r) for r in conn.execute(f"SELECT * FROM lab_results WHERE record_id IN ({live_marks})", live_ids)]
        docs = []
        if share["include_files"]:
            docs = [dict(r) for r in conn.execute(
                f"SELECT id, record_id, filename, mime, size FROM documents WHERE record_id IN ({live_marks})", live_ids)]
        if log_visit:
            conn.execute("UPDATE share_links SET access_count = access_count + 1, last_access_at = ? WHERE id = ?",
                         (now_iso(), share["id"]))
            audit.log("share.viewed", share["user_id"], share["profile_id"], target=f"share:{share['id']}", conn=conn)
    for r in records:
        r["medications"] = [m for m in meds if m["record_id"] == r["id"]]
        r["lab_results"] = [l for l in labs if l["record_id"] == r["id"]]
        r["documents"] = [d for d in docs if d["record_id"] == r["id"]]
    return {"share_id": share["id"], "label": share["label"], "expires_at": share["expires_at"],
            "include_summary": bool(share["include_summary"]), "profile": dict(profile), "records": records,
            "owner_user_id": share["user_id"], "profile_id": share["profile_id"], "record_ids": live_ids}


def shared_document(token: str, document_id: int) -> tuple[dict, bytes]:
    with connect() as conn:
        share = _load_share(conn, token)
        if not share["include_files"]:
            raise ShareUnavailable("Files aren't included in this link.")
        ids = json.loads(share["record_ids_json"]) or [-1]
        row = conn.execute(
            f"SELECT d.* FROM documents d JOIN records r ON r.id = d.record_id WHERE d.id = ? AND r.profile_id = ? "
            f"AND d.record_id IN ({', '.join('?' * len(ids))})", (document_id, share["profile_id"], *ids)).fetchone()
        if row is None:
            raise ShareUnavailable("That file isn't part of this link.")
        audit.log("share.file_downloaded", share["user_id"], share["profile_id"], target=f"share:{share['id']}",
                  detail=f"document:{document_id}", conn=conn)
    return dict(row), read_document_unchecked(dict(row))
