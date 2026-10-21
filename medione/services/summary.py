"""A factual medical-history summary built only from stored records (no AI involved).

It lists what the records say, grouped for a doctor to skim. It does not
interpret, rank or infer anything.
"""
from __future__ import annotations

import html
import json
from datetime import date
from typing import Iterable, Optional

from medione.db import connect
from medione.models import SOURCES
from medione.services.access import require_profile


def _age(dob: Optional[str]) -> Optional[int]:
    if not dob:
        return None
    try:
        d = date.fromisoformat(dob)
    except ValueError:
        return None
    t = date.today()
    return t.year - d.year - ((t.month, t.day) < (d.month, d.day))


def build_summary(user_id: int, profile_id: int, record_ids: Optional[Iterable[int]] = None) -> dict:
    """Return structured sections. With ``record_ids`` only those records are used."""
    ids = list(record_ids) if record_ids is not None else None
    with connect() as conn:
        profile = dict(require_profile(conn, user_id, profile_id))
        sql = ("SELECT r.*, d.name AS doctor_name, f.name AS facility_name FROM records r "
               "LEFT JOIN doctors d ON d.id = r.doctor_id LEFT JOIN facilities f ON f.id = r.facility_id "
               "WHERE r.profile_id = ?")
        params: list = [profile_id]
        if ids is not None:
            if not ids:
                ids = [-1]
            sql += f" AND r.id IN ({', '.join('?' * len(ids))})"
            params += ids
        records = [dict(r) for r in conn.execute(sql + " ORDER BY r.record_date DESC", params)]
        rec_ids = [r["id"] for r in records] or [-1]
        marks = ", ".join("?" * len(rec_ids))
        meds = [dict(r) for r in conn.execute(
            f"SELECT m.*, r.record_date FROM medications m JOIN records r ON r.id = m.record_id "
            f"WHERE m.record_id IN ({marks}) ORDER BY m.status = 'active' DESC, r.record_date DESC", rec_ids)]
        labs = [dict(r) for r in conn.execute(
            f"SELECT l.*, r.record_date FROM lab_results l JOIN records r ON r.id = l.record_id "
            f"WHERE l.record_id IN ({marks}) ORDER BY r.record_date DESC", rec_ids)]
        upcoming = []
        if ids is None:  # a shared (scoped) summary never adds anything beyond the selected records
            today = date.today().isoformat()
            upcoming = [dict(r) for r in conn.execute(
                "SELECT a.starts_on AS date, a.time_of_day, a.purpose AS title, d.name AS doctor_name, "
                "f.name AS facility_name, 'Appointment' AS kind FROM appointments a "
                "LEFT JOIN doctors d ON d.id = a.doctor_id LEFT JOIN facilities f ON f.id = a.facility_id "
                "WHERE a.profile_id = ? AND a.status = 'upcoming' AND a.starts_on >= ? ORDER BY a.starts_on",
                (profile_id, today))]
            upcoming += [{"date": r["follow_up_date"], "time_of_day": None, "title": f"Follow-up written in “{r['title']}”",
                          "doctor_name": r["doctor_name"], "facility_name": r["facility_name"], "kind": "Follow-up",
                          "ref": r["id"]}
                         for r in records if r.get("follow_up_date") and r["follow_up_date"] >= today]
            upcoming.sort(key=lambda u: u["date"])
    for r in records:
        r["details"] = json.loads(r.pop("details_json") or "{}")

    def of(*types):
        return [r for r in records if r["type"] in types]

    latest_labs: dict[str, dict] = {}
    for l in labs:
        latest_labs.setdefault(l["test_name"].lower(), l)

    return {
        "profile": {"name": profile["full_name"], "age": _age(profile["date_of_birth"]),
                    "date_of_birth": profile["date_of_birth"], "sex": profile["sex"],
                    "blood_group": profile["blood_group"]},
        "allergies": of("allergy"),
        "diagnoses": of("diagnosis"),
        "active_medications": [m for m in meds if m["status"] == "active"],
        "past_medications": [m for m in meds if m["status"] != "active"][:15],
        "surgeries": of("surgery", "procedure"),
        "admissions": of("admission"),
        "vaccinations": of("vaccination"),
        "family_history": of("family_history"),
        "recent_tests": of("lab_report", "imaging", "ecg", "other_diagnostic")[:10],
        "latest_lab_values": list(latest_labs.values())[:20],
        "consultations": of("consultation")[:10],
        "upcoming": upcoming,
        "record_count": len(records),
        "unreviewed_ai": sum(1 for r in records if r["source"] in ("ai_extracted", "auto_extracted")),
        "scoped": ids is not None,
    }


def _e(v) -> str:
    return html.escape(str(v)) if v not in (None, "") else "<span class='nr'>Not recorded</span>"


def _rec_line(r: dict) -> str:
    who = " · ".join(x for x in (r.get("doctor_name"), r.get("facility_name")) if x)
    extra = r.get("condition") or r["details"].get("allergen") or r["details"].get("vaccine") or ""
    src = SOURCES.get(r["source"], (r["source"],))[0]
    return (f"<li><b>{_e(r['title'])}</b> — {_e(r.get('record_date'))}"
            f"{' · ' + html.escape(who) if who else ''}{' · ' + html.escape(extra) if extra else ''}"
            f" <span class='src'>({html.escape(src)} · ref #{r['id']})</span></li>")


def summary_html(s: dict, generated_for: str = "") -> str:
    """Printable, self-contained HTML version of the summary."""
    p = s["profile"]
    sections = []

    def section(title: str, items: list, render) -> None:
        body = "".join(render(i) for i in items) if items else "<li class='nr'>None recorded</li>"
        sections.append(f"<h2>{html.escape(title)}</h2><ul>{body}</ul>")

    section("Allergies", s["allergies"], lambda r: f"<li><b>{_e(r['details'].get('allergen') or r['title'])}</b>"
            f" — reaction: {_e(r['details'].get('reaction'))}; severity: {_e(r['details'].get('severity'))}</li>")
    section("Current medicines (as prescribed)", s["active_medications"], lambda m: (
        f"<li><b>{_e(m['name'])}</b> {_e(m['dosage'])} — {_e(m['frequency'])}"
        f"{' · ' + html.escape(m['instructions']) if m.get('instructions') else ''}"
        f"{' <span class=warn>(needs confirmation)</span>' if m['uncertain'] else ''}</li>"))
    section("Diagnoses documented by doctors", s["diagnoses"], _rec_line)
    section("Surgeries & procedures", s["surgeries"], _rec_line)
    section("Hospital admissions", s["admissions"], _rec_line)
    section("Recent tests & scans", s["recent_tests"], _rec_line)
    section("Latest lab values (as printed on the report)", s["latest_lab_values"], lambda l: (
        f"<li><b>{_e(l['test_name'])}</b>: {_e(l['value_text'] or l['value_num'])} {html.escape(l['unit'] or '')}"
        f" — reference: {_e(l['ref_text'] or _range(l))} · {_e(l['record_date'])}</li>"))
    section("Vaccinations", s["vaccinations"], _rec_line)
    if not s["scoped"]:
        section("Upcoming appointments & follow-ups", s.get("upcoming", []), lambda u: (
            f"<li><b>{_e(u['date'])}</b>{(' ' + html.escape(u['time_of_day'])) if u.get('time_of_day') else ''} — "
            f"{_e(u['title'])}{' · ' + html.escape(u['doctor_name']) if u.get('doctor_name') else ''}"
            f"{' · ' + html.escape(u['facility_name']) if u.get('facility_name') else ''}"
            f" <span class='src'>({html.escape(u['kind'])})</span></li>"))
    section("Family history", s["family_history"], lambda r: f"<li>{_e(r['details'].get('relative'))}: {_e(r['condition'] or r['title'])}</li>")
    section("Past medicines", s["past_medications"], lambda m: f"<li>{_e(m['name'])} {_e(m['dosage'])} — {_e(m['status'])}</li>")

    scope = ("Includes only the records the patient selected for sharing." if s["scoped"]
             else f"Built from {s['record_count']} stored records.")
    caution = (f"<p class='warn'>{s['unreviewed_ai']} record(s) were extracted by AI and have not been reviewed "
               "by the patient yet.</p>") if s["unreviewed_ai"] else ""
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Medical history summary</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{{font-family:'Plus Jakarta Sans',Segoe UI,Arial,sans-serif;color:#0F2A33;max-width:820px;margin:24px auto;padding:0 16px;line-height:1.45}}
h1{{font-size:22px;margin-bottom:4px}}h2{{font-size:15px;border-bottom:1px solid #E2E8F0;padding-bottom:4px;margin-top:22px;color:#0F766E}}
ul{{padding-left:18px}}li{{margin:3px 0}}.nr{{color:#64748B}}.src{{color:#64748B;font-size:12px}}.warn{{color:#B45309}}
.meta{{color:#475569;font-size:13px}}.note{{background:#F1F5F9;padding:10px 12px;border-radius:8px;font-size:13px}}</style></head><body>
<h1>Medical history summary — {_e(p['name'])}</h1>
<div class="meta">Date of birth: {_e(p['date_of_birth'])}{f" (age {p['age']})" if p['age'] is not None else ''} · Sex: {_e(p['sex'])} ·
Blood group: {_e(p['blood_group'])}<br>Generated {date.today().isoformat()} by Thought Medione{(' for ' + html.escape(generated_for)) if generated_for else ''}. {scope}</div>
{caution}
<p class="note">This summary lists information exactly as recorded by the patient or copied from their documents.
It is not a diagnosis, and items marked "AI-extracted" may contain reading errors — please check the original documents.</p>
{''.join(sections)}
</body></html>"""


def _range(l: dict) -> str:
    lo, hi = l.get("ref_low"), l.get("ref_high")
    if lo is None and hi is None:
        return ""
    return f"{'' if lo is None else _fmt(lo)}–{'' if hi is None else _fmt(hi)}"


def _fmt(v: float) -> str:
    return f"{v:g}"
