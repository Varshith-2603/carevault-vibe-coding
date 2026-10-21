"""Everything the dashboard needs, worked out from the profile's own data.

Each "to-do" is a factual nudge (a record to review, a follow-up date written in
a record, a policy about to lapse). None of them is medical advice.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from medione.models import SEVERITY
from medione.services import appointments, health, records, reminders, search, summary


def _d(s: Optional[str]) -> Optional[date]:
    try:
        return date.fromisoformat(s[:10]) if s else None
    except ValueError:
        return None


def build(user_id: int, profile_id: int, today: Optional[date] = None) -> dict:
    today = today or date.today()
    appts = appointments.list_appointments(user_id, profile_id, today)
    rems = reminders.list_reminders(user_id, profile_id, today)
    concerns = health.list_concerns(user_id, profile_id, "active")
    vit = health.latest_vitals(user_id, profile_id)
    s = summary.build_summary(user_id, profile_id)
    recs = search.search_records(user_id, profile_id)
    meds = records.list_medications(user_id, profile_id, "active")
    todos: list[dict] = []

    def todo(kind, title, detail, tone="amber", record_id=None, page=None, key=""):
        todos.append({"kind": kind, "title": title, "detail": detail, "tone": tone, "record_id": record_id,
                      "page": page, "key": key or f"{kind}_{record_id or len(todos)}"})

    for r in recs:
        if r["source"] in ("ai_extracted", "auto_extracted"):
            todo("review", f"Check “{r['title']}”", "Read automatically — compare it with the original document.",
                 record_id=r["id"])
    for a, b in search.possible_duplicates(user_id, profile_id):
        todo("duplicate", f"Possible duplicate: “{a['title']}”",
             f"Looks like “{b['title']}” from the same date. Review and keep one.", "gray", record_id=a["id"],
             key=f"dup_{a['id']}_{b['id']}")
    for a in appts["needs_update"]:
        todo("appointment", f"How did “{a['purpose']}” go?",
             f"Appointment on {a['starts_on']} — mark it completed, missed or cancelled.", page="Appointments",
             key=f"appt_{a['id']}")
    booked = {a["starts_on"] for a in appts["upcoming"]}
    for r in recs:
        fu = _d(r.get("follow_up_date"))
        if fu and today - timedelta(days=14) <= fu <= today + timedelta(days=30):
            near = any(abs((_d(b) - fu).days) <= 7 for b in booked)
            if not near:
                when = "was due" if fu < today else "is due"
                todo("follow_up", f"Follow-up {when} {fu.strftime('%d %b')}",
                     f"Written in “{r['title']}”. No appointment booked around that date.", "blue",
                     page="Appointments", key=f"fu_{r['id']}")
        if r["type"] == "insurance":
            end = _d(r.get("end_date"))
            if end and end <= today + timedelta(days=45):
                todo("insurance", f"Insurance “{r['title']}” {'expired' if end < today else 'expires'} {end.strftime('%d %b %Y')}",
                     "Renew in time so cover doesn't lapse.", "red" if end < today else "amber", record_id=r["id"])
    for r in s["vaccinations"]:
        nxt = _d(r["details"].get("next_dose_date"))
        if nxt and nxt <= today + timedelta(days=30):
            todo("vaccination", f"{r['details'].get('vaccine') or r['title']}: next dose {'overdue' if nxt < today else 'due'}",
                 f"Date written on the vaccination record: {nxt.strftime('%d %b %Y')}.", "blue", record_id=r["id"])
    for m in meds:
        end = _d(m.get("end_date"))
        if end and today <= end <= today + timedelta(days=7):
            todo("medicine", f"{m['name']} course ends {end.strftime('%d %b')}",
                 "If you think you need more, ask your doctor before it runs out.", "amber", record_id=m["record_id"])
        if m["uncertain"]:
            todo("medicine", f"Confirm {m['name']} details", m.get("uncertain_note") or "Part of the prescription was unclear.",
                 record_id=m["record_id"], key=f"medunc_{m['id']}")

    due_today = [r for r in rems if r["active"] and r["next_due"] and r["next_due"] <= today.isoformat()]
    flagged_vitals = [v for v in vit if v["latest"]["flag"] and _d(v["latest"]["measured_on"]) >= today - timedelta(days=30)]
    lab_flags = []
    for l in s["latest_lab_values"]:
        v, lo, hi = l.get("value_num"), l.get("ref_low"), l.get("ref_high")
        if v is not None and ((hi is not None and v > hi) or (lo is not None and v < lo)):
            lab_flags.append({**l, "direction": "above" if hi is not None and v > hi else "below"})

    conditions = [r["condition"] or r["title"] for r in s["diagnoses"]
                  if (r["details"].get("diagnosis_status") or "Active") != "Resolved"]
    return {
        "today": today,
        "next_appointments": appts["upcoming"][:4],
        "upcoming_count": len(appts["upcoming"]),
        "todos": todos,
        "due_today": due_today,
        "concerns": concerns,
        "severe_concern": any(c["severity"] >= 3 for c in concerns),
        "vitals": vit,
        "flagged_vitals": flagged_vitals,
        "lab_flags": lab_flags,
        "conditions": conditions,
        "allergies": [r["details"].get("allergen") or r["title"] for r in s["allergies"]],
        "medicines": s["active_medications"],
        "recent": recs[:5],
        "record_count": len(recs),
        "summary": s,
        "severity_labels": SEVERITY,
    }
