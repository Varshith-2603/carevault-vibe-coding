"""Turn what a prescription says into reminders and a follow-up appointment.

Only what is written is used: "1-0-1", "BD", "twice daily", "at bedtime", "for 5 days",
"review after 2 weeks"… are translated with fixed, visible default times the user can change.
Anything unclear ("SOS", "as needed", unreadable, not yet confirmed) gets **no** reminder,
and the reason is reported back. Nothing about the treatment itself is changed or suggested.
"""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from medione.db import connect
from medione.services import appointments, records, reminders
from medione.services.access import require_record

SLOT_TIMES = {"morning": "08:00", "afternoon": "14:00", "evening": "18:00", "night": "21:00", "bedtime": "22:00"}


@dataclass
class Plan:
    """What will be (or was) set up for one prescription."""
    medicine_reminders: list[dict] = field(default_factory=list)   # data for reminders.save_reminder
    skipped: list[tuple[str, str]] = field(default_factory=list)   # (medicine, reason)
    follow_up: Optional[dict] = None                                # {"date", "how", "purpose", ...}
    created: list[str] = field(default_factory=list)


def _clean(s: Optional[str]) -> str:
    return " " + re.sub(r"\s+", " ", (s or "").lower()) + " "


def parse_times(frequency: Optional[str], instructions: Optional[str] = None) -> tuple[Optional[list[tuple[str, str]]], str, str]:
    """Return ([(label, HH:MM)…] or None, repeat, explanation)."""
    f, ins = _clean(frequency), _clean(instructions)
    both = f + ins
    if re.search(r"\b(sos|prn|as needed|when needed|if needed|as required|when required|if required)\b", both) or \
            re.search(r"\bif (temperature|fever|pain|temp)\b|\bonly if\b|\bwhen (there is|in) pain\b", both):
        return None, "none", "taken only when needed"
    # "1-0-1" (morning-afternoon-night[-bedtime]); a following "- 5 days" is a duration, not a 4th dose
    m = re.search(r"(?<![\d.])([0-2½])\s*-\s*([0-2½])\s*-\s*([0-2½])"
                  r"(?:\s*-\s*([0-2½])(?!\s*(?:\d|days?\b|weeks?\b|months?\b)))?(?![\d.])", f)
    if m:
        labels = ["morning", "afternoon", "night", "bedtime"]
        slots = [(lab, SLOT_TIMES[lab]) for lab, v in zip(labels, m.groups()) if v and v not in ("0",)]
        if slots:
            return slots, "daily", f"“{m.group(0)}” = " + ", ".join(s[0] for s in slots)
    if re.search(r"\b(once|one time|1 time)s? (a|per|every) week\b|\bweekly\b|\bevery week\b", both) or \
            re.search(r"\bevery (sunday|monday|tuesday|wednesday|thursday|friday|saturday)\b", both):
        return [("weekly dose", "09:00")], "weekly", "once a week"
    if re.search(r"\b(once|one time) (a|per|every) month\b|\bmonthly\b", both):
        return [("monthly dose", "09:00")], "monthly", "once a month"
    hours = re.search(r"\bevery (\d+) ?(hours|hrs|hr|h)\b|\bq(\d+)h\b", f)
    if hours:
        n = int(hours.group(1) or hours.group(3))
        table = {6: ["06:00", "12:00", "18:00", "00:00"], 8: ["06:00", "14:00", "22:00"], 12: ["08:00", "20:00"],
                 24: ["09:00"]}
        if n in table:
            return [(f"dose {i + 1}", t) for i, t in enumerate(table[n])], "daily", f"every {n} hours"
    if re.search(r"\b(qid|four times|4 times)\b", f):
        return [("morning", "07:00"), ("noon", "12:00"), ("evening", "17:00"), ("night", "22:00")], "daily", "4 times a day"
    if re.search(r"\b(tds|tid|thrice|three times|3 times)\b", f):
        return [("morning", "08:00"), ("afternoon", "14:00"), ("night", "20:00")], "daily", "3 times a day"
    if re.search(r"\b(bd|bid|twice|two times|2 times|morning (and|&) (night|evening))\b", f):
        return [("morning", "08:00"), ("night", "20:00")], "daily", "twice a day"
    if re.search(r"\b(hs|at bed ?time|before (sleep|bed))\b", both):
        return [("bedtime", "22:00")], "daily", "at bedtime"
    if re.search(r"\b(od|once|one time|1 time|daily|every day|everyday|qd)\b", f) or re.search(r"\b(morning|night)\b", f):
        if re.search(r"\b(night|dinner|evening|bed)\b", both):
            return [("night", "21:00")], "daily", "once a day (night)"
        if re.search(r"\b(afternoon|lunch)\b", both):
            return [("afternoon", "14:00")], "daily", "once a day (afternoon)"
        if re.search(r"\b(morning|breakfast|empty stomach)\b", both):
            return [("morning", "08:00")], "daily", "once a day (morning)"
        return [("daily", "09:00")], "daily", "once a day"
    return None, "none", "the frequency isn't clear enough"


def parse_duration(text: Optional[str], start: date) -> tuple[Optional[date], bool]:
    """(end date or None, is_long_term). Unknown duration -> (None, False)."""
    t = _clean(text)
    if re.search(r"\b(long ?term|lifelong|continue|ongoing|until (review|next visit|further)|regular|indefinite)", t):
        return None, True
    m = re.search(r"(\d+)\s*(day|days|d|week|weeks|wk|wks|month|months|mo)\b", t)
    if not m:
        return None, False
    n, unit = int(m.group(1)), m.group(2)
    if unit.startswith(("w",)):
        return start + timedelta(days=7 * n - 1), False
    if unit.startswith("mo"):
        return _add_months(start, n) - timedelta(days=1), False
    return start + timedelta(days=n - 1), False


def _add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def relative_follow_up(text: Optional[str], start: date) -> Optional[tuple[date, str]]:
    """'Review after 2 weeks' / 'follow up in 10 days' -> (date, phrase)."""
    t = _clean(text)
    m = re.search(r"\b(review|follow[- ]?up|revisit|come back|see (me|again)|check[- ]?up|repeat visit)\b[^.]{0,25}?"
                  r"\b(after|in)\s+(\d+|one|two|three|four|six)\s*(day|days|week|weeks|month|months)\b", t)
    if not m:
        return None
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "six": 6}
    n = int(m.group(4)) if m.group(4).isdigit() else words[m.group(4)]
    unit = m.group(5)
    when = start + (timedelta(days=n) if unit.startswith("day") else timedelta(weeks=n) if unit.startswith("week")
                    else timedelta(days=0))
    if unit.startswith("month"):
        when = _add_months(start, n)
    return when, m.group(0).strip()


def build_plan(user_id: int, record_id: int, today: Optional[date] = None) -> Plan:
    """Work out (without saving) the reminders and follow-up for a saved prescription record."""
    today = today or date.today()
    rec = records.get_record(user_id, record_id)
    plan = Plan()
    start = date.fromisoformat(rec["record_date"]) if rec.get("record_date") else today
    existing = {(r["title"], r["time_of_day"]) for r in reminders.list_reminders(user_id, rec["profile_id"])
                if r.get("source_record_id") == record_id}
    for m in rec["medications"]:
        name = " ".join(x for x in (m["name"], m["dosage"]) if x)
        if m["status"] != "active":
            plan.skipped.append((name, f"marked {m['status']}"))
            continue
        if m["uncertain"]:
            plan.skipped.append((name, "details still need checking — confirm them first"))
            continue
        slots, repeat, how = parse_times(m["frequency"], m["instructions"])
        if not slots:
            plan.skipped.append((name, how))
            continue
        med_start = date.fromisoformat(m["start_date"]) if m.get("start_date") else start
        end, long_term = parse_duration(m["duration"], med_start)
        if m.get("end_date"):
            end = date.fromisoformat(m["end_date"])
        if end and end < today:
            plan.skipped.append((name, f"course ended on {end.strftime('%d %b %Y')}"))
            continue
        first = max(med_start, today)
        for label, hhmm in slots:
            title = f"{name} ({label})"
            if (title, hhmm) in existing:
                continue
            plan.medicine_reminders.append({
                "kind": "medication", "title": title[:120], "due_date": first, "time_of_day": hhmm, "repeat": repeat,
                "until_date": end, "source_record_id": record_id,
                "notes": "As written: " + ", ".join(x for x in (m["frequency"], m["instructions"], m["duration"]) if x)
                         + f". Times set automatically from “{how}” — change them if your doctor said otherwise.",
            })

    fu_date, how = None, ""
    if rec.get("follow_up_date"):
        fu_date, how = date.fromisoformat(rec["follow_up_date"]), "date written on the prescription"
    else:
        texts = " ".join(str(v) for v in (rec["details"].get("doctor_instructions"), rec.get("notes"), rec.get("summary"),
                                          *[m["instructions"] for m in rec["medications"]]) if v)
        rel = relative_follow_up(texts, start)
        if rel:
            fu_date, how = rel[0], f"calculated from “{rel[1]}” on the prescription"
    if fu_date and fu_date >= today:
        upcoming = appointments.list_appointments(user_id, rec["profile_id"], today)["upcoming"]
        clash = next((a for a in upcoming if abs((date.fromisoformat(a["starts_on"]) - fu_date).days) <= 3
                      and (not rec["doctor_id"] or a["doctor_id"] in (None, rec["doctor_id"]))), None)
        who = rec.get("doctor_name") or "the doctor"
        plan.follow_up = {"date": fu_date, "how": how, "existing": clash,
                          "purpose": f"Follow-up with {who}" + (f" – {rec['condition']}" if rec.get("condition") else ""),
                          "doctor_id": rec["doctor_id"], "facility_id": rec["facility_id"]}
    elif fu_date:
        plan.skipped.append(("Follow-up", f"date {fu_date.strftime('%d %b %Y')} has already passed"))
    return plan


def apply_plan(user_id: int, record_id: int, plan: Optional[Plan] = None) -> Plan:
    """Create the reminders and follow-up appointment from the plan. Returns the plan with ``created`` filled."""
    plan = plan or build_plan(user_id, record_id)
    with connect() as conn:
        profile_id = require_record(conn, user_id, record_id)["profile_id"]
    for data in plan.medicine_reminders:
        reminders.save_reminder(user_id, profile_id, data)
        plan.created.append(f"⏰ {data['title']} at {data['time_of_day']}"
                            + (f" until {data['until_date'].strftime('%d %b')}" if data.get("until_date") else ""))
    fu = plan.follow_up
    if fu and not fu["existing"]:
        appointments.save_appointment(user_id, profile_id, {
            "starts_on": fu["date"], "kind": "follow_up", "purpose": fu["purpose"][:160], "doctor_id": fu["doctor_id"],
            "facility_id": fu["facility_id"], "notes": f"Added automatically — {fu['how']}. Call the clinic to confirm the time."})
        reminders.save_reminder(user_id, profile_id, {
            "kind": "appointment", "title": fu["purpose"][:120], "due_date": fu["date"] - timedelta(days=1),
            "time_of_day": "18:00", "source_record_id": record_id,
            "notes": f"Your follow-up is tomorrow ({fu['how']})."})
        plan.created.append(f"📅 {fu['purpose']} on {fu['date'].strftime('%d %b %Y')} (+ a reminder the day before)")
    elif fu and fu["existing"]:
        plan.skipped.append(("Follow-up", f"already booked: “{fu['existing']['purpose']}” on {fu['existing']['starts_on']}"))
    return plan
