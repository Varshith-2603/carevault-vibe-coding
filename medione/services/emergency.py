"""Emergency card: the few facts a responder needs, reachable from a QR code on a printed card.

The card holds only blood group, allergies, documented conditions, current
medicines and the emergency contact. The link can be turned off at any time,
and every scan is logged.
"""
from __future__ import annotations

import io
from typing import Optional

from medione import audit, config, security
from medione.db import connect, now_iso
from medione.services.access import require_profile
from medione.services.summary import build_summary


class CardUnavailable(Exception):
    pass


SECTIONS = {"blood_group": "Blood group", "allergies": "Allergies", "conditions": "Conditions",
            "medicines": "Current medicines", "surgeries": "Past surgeries", "contact": "Emergency contact"}
DEFAULT_INCLUDE = {"blood_group": True, "allergies": True, "conditions": True, "medicines": True,
                   "surgeries": False, "contact": True}


def get_include(user_id: int, profile_id: int) -> dict:
    import json
    with connect() as conn:
        require_profile(conn, user_id, profile_id)
        row = conn.execute("SELECT include_json FROM emergency_settings WHERE profile_id = ?", (profile_id,)).fetchone()
    chosen = json.loads(row["include_json"]) if row else {}
    return {k: bool(chosen.get(k, v)) for k, v in DEFAULT_INCLUDE.items()}


def set_include(user_id: int, profile_id: int, include: dict) -> None:
    import json
    clean = {k: bool(include.get(k, v)) for k, v in DEFAULT_INCLUDE.items()}
    with connect() as conn:
        require_profile(conn, user_id, profile_id)
        conn.execute("INSERT OR REPLACE INTO emergency_settings (profile_id, include_json, updated_at) VALUES (?,?,?)",
                     (profile_id, json.dumps(clean), now_iso()))
        audit.log("emergency.settings", user_id, profile_id, conn=conn)


def card_data(user_id: int, profile_id: int) -> dict:
    """Only the sections the user chose to include. Missing information stays None/[] — never 'confirmed none'."""
    s = build_summary(user_id, profile_id)
    include = get_include(user_id, profile_id)
    with connect() as conn:
        p = dict(require_profile(conn, user_id, profile_id))
        updated = conn.execute(
            "SELECT MAX(updated_at) FROM records WHERE profile_id = ? AND type IN "
            "('allergy','diagnosis','prescription','surgery','procedure')", (profile_id,)).fetchone()[0]
        settings_at = conn.execute("SELECT updated_at FROM emergency_settings WHERE profile_id = ?",
                                   (profile_id,)).fetchone()
    card = {
        "name": p["full_name"], "date_of_birth": p["date_of_birth"], "age": s["profile"]["age"], "sex": p["sex"],
        "include": include,
        "updated_at": max(x for x in (updated, settings_at[0] if settings_at else None, p["created_at"]) if x),
        "blood_group": p["blood_group"] if include["blood_group"] else None,
        "allergies": [{"what": r["details"].get("allergen") or r["title"], "reaction": r["details"].get("reaction"),
                       "severity": r["details"].get("severity")} for r in s["allergies"]] if include["allergies"] else [],
        "conditions": [r["condition"] or r["title"] for r in s["diagnoses"]
                       if (r["details"].get("diagnosis_status") or "Active") != "Resolved"] if include["conditions"] else [],
        "medicines": [{"name": m["name"], "dose": m["dosage"], "frequency": m["frequency"]}
                      for m in s["active_medications"]] if include["medicines"] else [],
        "surgeries": [r["title"] for r in s["surgeries"]][:5] if include["surgeries"] else [],
        "contact_name": p["emergency_contact_name"] if include["contact"] else None,
        "contact_phone": p["emergency_contact_phone"] if include["contact"] else None,
    }
    return card


def active_link(user_id: int, profile_id: int) -> Optional[dict]:
    with connect() as conn:
        require_profile(conn, user_id, profile_id)
        row = conn.execute("SELECT * FROM emergency_links WHERE profile_id = ? AND user_id = ? AND revoked_at IS NULL "
                           "ORDER BY id DESC LIMIT 1", (profile_id, user_id)).fetchone()
    return dict(row) if row else None


def create_link(user_id: int, profile_id: int) -> str:
    """Create a new emergency link (any previous one stops working). Returns the token, shown once."""
    token = security.new_share_token()
    with connect() as conn:
        require_profile(conn, user_id, profile_id)
        conn.execute("UPDATE emergency_links SET revoked_at = ? WHERE profile_id = ? AND revoked_at IS NULL",
                     (now_iso(), profile_id))
        lid = conn.execute("INSERT INTO emergency_links (user_id, profile_id, token_hash, created_at) VALUES (?,?,?,?)",
                           (user_id, profile_id, security.token_hash(token), now_iso())).lastrowid
        audit.log("emergency.created", user_id, profile_id, target=f"emergency:{lid}", conn=conn)
    return token


def revoke(user_id: int, profile_id: int) -> None:
    with connect() as conn:
        require_profile(conn, user_id, profile_id)
        conn.execute("UPDATE emergency_links SET revoked_at = ? WHERE profile_id = ? AND user_id = ? "
                     "AND revoked_at IS NULL", (now_iso(), profile_id, user_id))
        audit.log("emergency.revoked", user_id, profile_id, conn=conn)


def open_card(token: str, log_visit: bool = True) -> dict:
    if not token or len(token) > 100:
        raise CardUnavailable("This emergency card link isn't valid.")
    with connect() as conn:
        row = conn.execute("SELECT * FROM emergency_links WHERE token_hash = ?", (security.token_hash(token),)).fetchone()
        if row is None or row["revoked_at"]:
            raise CardUnavailable("This emergency card link isn't valid or has been turned off.")
        if log_visit:
            conn.execute("UPDATE emergency_links SET access_count = access_count + 1, last_access_at = ? WHERE id = ?",
                         (now_iso(), row["id"]))
            audit.log("emergency.viewed", row["user_id"], row["profile_id"], target=f"emergency:{row['id']}", conn=conn)
    return card_data(row["user_id"], row["profile_id"])


def card_url(token: str) -> str:
    return f"{config.settings.base_url}/?emergency={token}"


def qr_png(text: str) -> bytes:
    import qrcode
    img = qrcode.make(text, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
