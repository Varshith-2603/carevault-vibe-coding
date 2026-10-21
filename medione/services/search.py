"""Search, chronological timeline, possible-duplicate review and lab comparisons."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date
from typing import Iterable, Optional

from medione import audit
from medione.db import connect
from medione.models import RECORD_TYPES, type_label
from medione.services.access import require_profile

_BASE_SQL = """
SELECT r.*, d.name AS doctor_name, f.name AS facility_name,
       (SELECT GROUP_CONCAT(m.name, ' | ') FROM medications m WHERE m.record_id = r.id) AS med_names,
       (SELECT GROUP_CONCAT(l.test_name, ' | ') FROM lab_results l WHERE l.record_id = r.id) AS test_names,
       (SELECT COUNT(*) FROM documents x WHERE x.record_id = r.id) AS doc_count,
       (SELECT GROUP_CONCAT(COALESCE(x.extracted_text, '') || ' ' || x.filename, ' ') FROM documents x
         WHERE x.record_id = r.id) AS doc_text
FROM records r
LEFT JOIN doctors d ON d.id = r.doctor_id
LEFT JOIN facilities f ON f.id = r.facility_id
WHERE r.profile_id = ?
"""


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"\s+", (text or "").lower().strip()) if w]


def _haystack(row: dict) -> str:
    parts = [row.get(k) or "" for k in ("title", "condition", "summary", "notes", "status", "doctor_name",
                                         "facility_name", "med_names", "test_names", "doc_text",
                                         "record_date", "follow_up_date")]
    parts.append(type_label(row["type"]))
    parts.append(row.get("details_json") or "")
    if row.get("record_date"):
        try:
            parts.append(date.fromisoformat(row["record_date"]).strftime("%B %b %Y"))
        except ValueError:
            pass
    return " ".join(parts).lower()


def search_records(user_id: int, profile_id: int, query: str = "", types: Optional[Iterable[str]] = None,
                   date_from: Optional[date] = None, date_to: Optional[date] = None,
                   doctor_id: Optional[int] = None, facility_id: Optional[int] = None,
                   condition: str = "", medication: str = "", test: str = "",
                   sources: Optional[Iterable[str]] = None, limit: int = 500) -> list[dict]:
    """Every word of ``query`` must appear somewhere in the record (fields, medicines, tests, file text)."""
    sql, params = _BASE_SQL, [profile_id]
    types = [t for t in (types or []) if t in RECORD_TYPES]
    if types:
        sql += f" AND r.type IN ({', '.join('?' * len(types))})"
        params += types
    if date_from:
        sql += " AND r.record_date >= ?"
        params.append(date_from.isoformat())
    if date_to:
        sql += " AND r.record_date <= ?"
        params.append(date_to.isoformat())
    if doctor_id:
        sql += " AND r.doctor_id = ?"
        params.append(doctor_id)
    if facility_id:
        sql += " AND r.facility_id = ?"
        params.append(facility_id)
    sources = list(sources or [])
    if sources:
        sql += f" AND r.source IN ({', '.join('?' * len(sources))})"
        params += sources
    sql += " ORDER BY r.record_date IS NULL, r.record_date DESC, r.id DESC"
    with connect() as conn:
        require_profile(conn, user_id, profile_id)
        rows = [dict(r) for r in conn.execute(sql, params)]
    words = _words(query)
    out = []
    for row in rows:
        hay = _haystack(row)
        if words and not all(w in hay for w in words):
            continue
        if condition and condition.lower() not in ((row.get("condition") or "") + " " + (row.get("summary") or "")).lower():
            continue
        if medication and medication.lower() not in (row.get("med_names") or "").lower():
            continue
        if test and test.lower() not in ((row.get("test_names") or "") + " " + row["title"]).lower():
            continue
        row.pop("doc_text", None)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def distinct_values(user_id: int, profile_id: int) -> dict:
    """Values that exist in this profile's records, for filter dropdowns."""
    with connect() as conn:
        require_profile(conn, user_id, profile_id)
        conds = [r[0] for r in conn.execute(
            "SELECT DISTINCT condition FROM records WHERE profile_id = ? AND condition IS NOT NULL ORDER BY 1", (profile_id,))]
        meds = [r[0] for r in conn.execute(
            "SELECT DISTINCT name FROM medications WHERE profile_id = ? ORDER BY name COLLATE NOCASE", (profile_id,))]
        tests = [r[0] for r in conn.execute(
            "SELECT DISTINCT test_name FROM lab_results WHERE profile_id = ? ORDER BY test_name COLLATE NOCASE", (profile_id,))]
    return {"conditions": conds, "medications": meds, "tests": tests}


# ------------------------------------------------------------------ timeline
def timeline(user_id: int, profile_id: int, types: Optional[Iterable[str]] = None,
             include_follow_ups: bool = True) -> list[dict]:
    """Chronological events, newest first. Follow-ups come only from dates written in a record."""
    records = search_records(user_id, profile_id, types=types)
    events = []
    for r in records:
        events.append({"date": r["record_date"], "kind": r["type"], "title": r["title"], "record_id": r["id"],
                       "doctor_name": r["doctor_name"], "facility_name": r["facility_name"],
                       "source": r["source"], "doc_count": r["doc_count"], "is_follow_up": False,
                       "end_date": r["end_date"]})
        if include_follow_ups and r.get("follow_up_date"):
            events.append({"date": r["follow_up_date"], "kind": "follow_up", "title": f"Follow-up: {r['title']}",
                           "record_id": r["id"], "doctor_name": r["doctor_name"],
                           "facility_name": r["facility_name"], "source": r["source"], "doc_count": 0,
                           "is_follow_up": True, "end_date": None})
    events.sort(key=lambda e: (e["date"] is not None, e["date"] or ""), reverse=True)
    return events


# ---------------------------------------------------------------- duplicates
def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 1}


def _similar(a: str, b: str) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.6


def possible_duplicates(user_id: int, profile_id: int) -> list[tuple[dict, dict]]:
    """Pairs with the same type and date and a near-identical title. Nothing is deleted automatically."""
    with connect() as conn:
        require_profile(conn, user_id, profile_id)
        rows = [dict(r) for r in conn.execute(
            "SELECT id, type, title, record_date, source FROM records WHERE profile_id = ? AND record_date IS NOT NULL",
            (profile_id,))]
        dismissed = {(r["record_a"], r["record_b"]) for r in conn.execute(
            "SELECT record_a, record_b FROM duplicate_dismissals WHERE profile_id = ?", (profile_id,))}
    groups = defaultdict(list)
    for r in rows:
        groups[(r["type"], r["record_date"])].append(r)
    pairs = []
    for items in groups.values():
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                key = (min(a["id"], b["id"]), max(a["id"], b["id"]))
                if key not in dismissed and _similar(a["title"], b["title"]):
                    pairs.append((a, b) if a["id"] < b["id"] else (b, a))
    return pairs


def dismiss_duplicate(user_id: int, profile_id: int, record_a: int, record_b: int) -> None:
    a, b = min(record_a, record_b), max(record_a, record_b)
    with connect() as conn:
        require_profile(conn, user_id, profile_id)
        n = conn.execute("SELECT COUNT(*) FROM records WHERE profile_id = ? AND id IN (?, ?)",
                         (profile_id, a, b)).fetchone()[0]
        if n != 2:
            raise ValueError("Records not found.")
        conn.execute("INSERT OR IGNORE INTO duplicate_dismissals (profile_id, record_a, record_b) VALUES (?,?,?)",
                     (profile_id, a, b))
        audit.log("duplicate.dismissed", user_id, profile_id, target=f"record:{a},{b}", conn=conn)


# ---------------------------------------------------------------- lab trends
def _norm_test(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def lab_trends(lab_rows: list[dict]) -> list[dict]:
    """Group results per test. A trend is 'comparable' only if every value is numeric with the same unit."""
    groups: dict[str, list[dict]] = defaultdict(list)
    names: dict[str, str] = {}
    for row in lab_rows:
        key = _norm_test(row["test_name"])
        groups[key].append(row)
        names.setdefault(key, row["test_name"])
    out = []
    for key, rows in groups.items():
        rows = sorted(rows, key=lambda r: r.get("record_date") or "")
        units = {(r.get("unit") or "").strip().lower() for r in rows}
        numeric = all(r.get("value_num") is not None for r in rows)
        comparable = numeric and len(units) == 1 and len(rows) >= 2
        for r in rows:
            r["outside_report_range"] = _outside(r)
        reason = None
        if len(rows) < 2:
            reason = "Only one result recorded."
        elif not numeric:
            reason = "Some values aren't numbers, so they can't be plotted."
        elif len(units) > 1:
            reason = "Results use different units (" + ", ".join(sorted(u or "no unit" for u in units)) + "), so they aren't compared."
        out.append({"test_name": names[key], "results": rows, "comparable": comparable,
                    "unit": rows[-1].get("unit"), "reason": reason})
    out.sort(key=lambda t: t["test_name"].lower())
    return out


def _outside(row: dict) -> Optional[str]:
    """'high'/'low' relative to the range printed on that report, or None if unknown."""
    v, lo, hi = row.get("value_num"), row.get("ref_low"), row.get("ref_high")
    if v is None:
        return None
    if hi is not None and v > hi:
        return "above"
    if lo is not None and v < lo:
        return "below"
    return None


def record_payload(row: dict) -> dict:
    row = dict(row)
    row["details"] = json.loads(row.pop("details_json", "{}") or "{}")
    return row
