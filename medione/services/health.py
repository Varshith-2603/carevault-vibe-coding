"""Patient-reported health: ongoing concerns/symptoms and home vital-sign readings.

Readings are compared only with *general* adult reference ranges so the app can
point out what may be worth discussing with a doctor. It never diagnoses.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from medione import audit
from medione.db import connect, now_iso
from medione.models import SEVERITY, SUGAR_HIGH, VITAL_KINDS
from medione.services.access import require_profile
from medione.services.records import iso_date


# ------------------------------------------------------------------ concerns
def save_concern(user_id: int, profile_id: int, data: dict, concern_id: Optional[int] = None) -> int:
    title = (data.get("title") or "").strip()
    if not title:
        raise ValueError("Describe the health concern, e.g. 'Headaches' or 'Knee pain'.")
    started = iso_date(data.get("started_on"))
    if started and started > date.today().isoformat():
        raise ValueError("The start date can't be in the future.")
    values = (title[:120], (data.get("body_area") or "").strip() or None, started,
              (data.get("notes") or "").strip() or None)
    with connect() as conn:
        require_profile(conn, user_id, profile_id)
        if concern_id:
            _owned(conn, user_id, concern_id)
            conn.execute("UPDATE health_concerns SET title=?, body_area=?, started_on=?, notes=? WHERE id=?",
                         (*values, concern_id))
        else:
            concern_id = conn.execute(
                "INSERT INTO health_concerns (profile_id, title, body_area, started_on, notes, created_at) "
                "VALUES (?,?,?,?,?,?)", (profile_id, *values, now_iso())).lastrowid
            severity = int(data.get("severity") or 1)
            conn.execute("INSERT INTO concern_logs (concern_id, logged_on, severity, note) VALUES (?,?,?,?)",
                         (concern_id, iso_date(data.get("logged_on")) or date.today().isoformat(),
                          severity if severity in SEVERITY else 1, (data.get("first_note") or "").strip() or None))
        audit.log("concern.saved", user_id, profile_id, target=f"concern:{concern_id}", conn=conn)
    return concern_id


def _owned(conn, user_id: int, concern_id: int):
    row = conn.execute("SELECT c.* FROM health_concerns c JOIN profiles p ON p.id = c.profile_id "
                       "WHERE c.id = ? AND p.user_id = ?", (concern_id, user_id)).fetchone()
    if row is None:
        raise ValueError("Concern not found.")
    return row


def log_concern(user_id: int, concern_id: int, severity: int, note: str = "", on: Optional[date] = None) -> None:
    if severity not in SEVERITY:
        raise ValueError("Choose how bad it is.")
    with connect() as conn:
        _owned(conn, user_id, concern_id)
        conn.execute("INSERT INTO concern_logs (concern_id, logged_on, severity, note) VALUES (?,?,?,?)",
                     (concern_id, (on or date.today()).isoformat(), severity, note.strip() or None))


def set_concern_status(user_id: int, concern_id: int, resolved: bool) -> None:
    with connect() as conn:
        _owned(conn, user_id, concern_id)
        conn.execute("UPDATE health_concerns SET status = ?, resolved_on = ? WHERE id = ?",
                     ("resolved" if resolved else "active", date.today().isoformat() if resolved else None, concern_id))


def delete_concern(user_id: int, concern_id: int) -> None:
    with connect() as conn:
        row = _owned(conn, user_id, concern_id)
        conn.execute("DELETE FROM health_concerns WHERE id = ?", (concern_id,))
        audit.log("concern.deleted", user_id, row["profile_id"], target=f"concern:{concern_id}", conn=conn)


def list_concerns(user_id: int, profile_id: int, status: Optional[str] = None) -> list[dict]:
    with connect() as conn:
        require_profile(conn, user_id, profile_id)
        sql = "SELECT * FROM health_concerns WHERE profile_id = ?"
        params: list = [profile_id]
        if status:
            sql += " AND status = ?"
            params.append(status)
        concerns = [dict(r) for r in conn.execute(sql + " ORDER BY status = 'active' DESC, created_at DESC", params)]
        for c in concerns:
            c["logs"] = [dict(r) for r in conn.execute(
                "SELECT * FROM concern_logs WHERE concern_id = ? ORDER BY logged_on, id", (c["id"],))]
            last = c["logs"][-1] if c["logs"] else None
            c["severity"] = last["severity"] if last else 1
            c["last_logged"] = last["logged_on"] if last else None
            c["trend"] = _trend(c["logs"])
    return concerns


def _trend(logs: list[dict]) -> str:
    if len(logs) < 2:
        return "new"
    a, b = logs[-2]["severity"], logs[-1]["severity"]
    return "worse" if b > a else "better" if b < a else "same"


# -------------------------------------------------------------------- vitals
def save_vital(user_id: int, profile_id: int, data: dict) -> int:
    kind = data.get("kind")
    spec = VITAL_KINDS.get(kind)
    if spec is None:
        raise ValueError("Choose what you measured.")
    try:
        v1 = float(data.get("value1"))
        v2 = float(data["value2"]) if spec.two_values else None
    except (TypeError, ValueError, KeyError) as exc:
        raise ValueError("Enter the reading as a number.") from exc
    limits = {"bp": (40, 300), "sugar": (20, 700), "pulse": (20, 250), "spo2": (50, 100), "temp": (30, 45),
              "weight": (1, 400)}[kind]
    if not limits[0] <= v1 <= limits[1] or (v2 is not None and not 20 <= v2 <= 200):
        raise ValueError("That reading looks mistyped. Please check the number.")
    if spec.two_values and v2 >= v1:
        raise ValueError("The top (systolic) number should be higher than the bottom (diastolic) number.")
    measured = iso_date(data.get("measured_on")) or date.today().isoformat()
    if measured > date.today().isoformat():
        raise ValueError("Readings can't be dated in the future.")
    context = data.get("context") if data.get("context") in spec.contexts else None
    with connect() as conn:
        require_profile(conn, user_id, profile_id)
        vid = conn.execute(
            "INSERT INTO vitals (profile_id, kind, measured_on, time_of_day, value1, value2, context, note, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (profile_id, kind, measured, (data.get("time_of_day") or None), v1, v2, context,
             (data.get("note") or "").strip() or None, now_iso())).lastrowid
    return vid


def delete_vital(user_id: int, vital_id: int) -> None:
    with connect() as conn:
        row = conn.execute("SELECT v.id FROM vitals v JOIN profiles p ON p.id = v.profile_id "
                           "WHERE v.id = ? AND p.user_id = ?", (vital_id, user_id)).fetchone()
        if row is None:
            raise ValueError("Reading not found.")
        conn.execute("DELETE FROM vitals WHERE id = ?", (vital_id,))


def list_vitals(user_id: int, profile_id: int, kind: Optional[str] = None, since: Optional[date] = None) -> list[dict]:
    sql, params = "SELECT * FROM vitals WHERE profile_id = ?", [profile_id]
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    if since:
        sql += " AND measured_on >= ?"
        params.append(since.isoformat())
    with connect() as conn:
        require_profile(conn, user_id, profile_id)
        rows = [dict(r) for r in conn.execute(sql + " ORDER BY measured_on, COALESCE(time_of_day, ''), id", params)]
    for r in rows:
        r["flag"] = vital_flag(r)
    return rows


def vital_flag(r: dict) -> Optional[str]:
    """'high'/'low' versus the general adult reference, or None."""
    spec = VITAL_KINDS[r["kind"]]
    v1, v2 = r["value1"], r.get("value2")
    if r["kind"] == "sugar":
        high = SUGAR_HIGH.get(r.get("context") or "Random", 199)
        return "high" if v1 > high else "low" if v1 < 70 else None
    if spec.high is not None and v1 > spec.high or (spec.high2 is not None and v2 is not None and v2 > spec.high2):
        return "high"
    if spec.low is not None and v1 < spec.low or (spec.low2 is not None and v2 is not None and v2 < spec.low2):
        return "low"
    return None


def format_vital(r: dict) -> str:
    spec = VITAL_KINDS[r["kind"]]
    num = lambda v: f"{v:g}"  # noqa: E731
    value = f"{num(r['value1'])}/{num(r['value2'])}" if spec.two_values else num(r["value1"])
    return f"{value} {spec.unit}"


def latest_vitals(user_id: int, profile_id: int) -> list[dict]:
    """Latest and previous reading for each kind that has data."""
    rows = list_vitals(user_id, profile_id)
    out = []
    for key, spec in VITAL_KINDS.items():
        mine = [r for r in rows if r["kind"] == key]
        if not mine:
            continue
        out.append({"kind": key, "spec": spec, "latest": mine[-1], "previous": mine[-2] if len(mine) > 1 else None,
                    "count": len(mine), "series": mine[-30:]})
    return out
