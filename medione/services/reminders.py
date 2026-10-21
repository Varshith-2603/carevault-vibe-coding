"""Reminders the user sets up themselves (medicines, follow-ups, tests, vaccinations).

A reminder only repeats what the user entered or what is written in a record.
It never works out a dosing schedule on its own.
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from medione import audit
from medione.db import connect, now_iso
from medione.models import REMINDER_KINDS, REPEATS
from medione.services.access import require_profile, require_record
from medione.services.records import iso_date


def _add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def next_occurrence(rem: dict, today: Optional[date] = None) -> Optional[date]:
    """The next due date on/after today (or the overdue date for one-off reminders not done yet)."""
    today = today or date.today()
    due = date.fromisoformat(rem["due_date"])
    until = date.fromisoformat(rem["until_date"]) if rem.get("until_date") else None
    last_done = date.fromisoformat(rem["last_done_on"]) if rem.get("last_done_on") else None
    repeat = rem.get("repeat") or "none"
    if repeat == "none":
        return None if last_done else due
    step = {"daily": lambda d, n: d + timedelta(days=n), "weekly": lambda d, n: d + timedelta(weeks=n),
            "monthly": lambda d, n: _add_months(d, n), "yearly": lambda d, n: _add_months(d, 12 * n)}[repeat]
    start = max(today, last_done + timedelta(days=1)) if last_done else today
    n, current = 0, due
    while current < start:
        n += 1
        current = step(due, n)
        if n > 5000:
            return None
    if until and current > until:
        return None
    return current


def save_reminder(user_id: int, profile_id: int, data: dict, reminder_id: Optional[int] = None) -> int:
    kind = data.get("kind")
    if kind not in REMINDER_KINDS:
        raise ValueError("Choose what the reminder is for.")
    title = (data.get("title") or "").strip()
    if not title:
        raise ValueError("Give the reminder a title.")
    due = iso_date(data.get("due_date"))
    if not due:
        raise ValueError("Choose the date.")
    repeat = data.get("repeat") or "none"
    if repeat not in REPEATS:
        raise ValueError("Invalid repeat option.")
    until = iso_date(data.get("until_date"))
    if until and until < due:
        raise ValueError("The end date is before the first date.")
    time_of_day = (data.get("time_of_day") or "").strip() or None
    if time_of_day:
        try:
            datetime.strptime(time_of_day, "%H:%M")
        except ValueError as exc:
            raise ValueError("Time must look like 08:30.") from exc
    source_record_id = data.get("source_record_id") or None
    values = (kind, title, (data.get("notes") or "").strip() or None, due, time_of_day, repeat, until, source_record_id)
    with connect() as conn:
        require_profile(conn, user_id, profile_id)
        if source_record_id:
            rec = require_record(conn, user_id, source_record_id)
            if rec["profile_id"] != profile_id:
                raise ValueError("Linked record belongs to another profile.")
        if reminder_id:
            _owned(conn, user_id, reminder_id)
            conn.execute("UPDATE reminders SET kind=?, title=?, notes=?, due_date=?, time_of_day=?, repeat=?, "
                         "until_date=?, source_record_id=? WHERE id=?", (*values, reminder_id))
        else:
            reminder_id = conn.execute(
                "INSERT INTO reminders (profile_id, kind, title, notes, due_date, time_of_day, repeat, until_date, "
                "source_record_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (profile_id, *values, now_iso())).lastrowid
        audit.log("reminder.saved", user_id, profile_id, target=f"reminder:{reminder_id}", conn=conn)
    return reminder_id


def _owned(conn, user_id: int, reminder_id: int):
    row = conn.execute("SELECT r.* FROM reminders r JOIN profiles p ON p.id = r.profile_id "
                       "WHERE r.id = ? AND p.user_id = ?", (reminder_id, user_id)).fetchone()
    if row is None:
        raise ValueError("Reminder not found.")
    return row


def list_reminders(user_id: int, profile_id: int, today: Optional[date] = None) -> list[dict]:
    today = today or date.today()
    with connect() as conn:
        require_profile(conn, user_id, profile_id)
        rows = [dict(r) for r in conn.execute(
            "SELECT rem.*, rec.title AS record_title FROM reminders rem LEFT JOIN records rec "
            "ON rec.id = rem.source_record_id WHERE rem.profile_id = ? ORDER BY rem.active DESC, rem.due_date",
            (profile_id,))]
    for r in rows:
        nxt = next_occurrence(r, today) if r["active"] else None
        r["next_due"] = nxt.isoformat() if nxt else None
        r["overdue"] = bool(nxt and nxt < today)
        r["due_today"] = bool(nxt and nxt == today)
    rows.sort(key=lambda r: (not r["active"], r["next_due"] is None, r["next_due"] or ""))
    return rows


def mark_done(user_id: int, reminder_id: int, on: Optional[date] = None) -> None:
    on = on or date.today()
    with connect() as conn:
        row = _owned(conn, user_id, reminder_id)
        nxt = next_occurrence(dict(row), on)
        done_on = (nxt if nxt and nxt <= on else on).isoformat()
        conn.execute("UPDATE reminders SET last_done_on = ? WHERE id = ?", (done_on, reminder_id))


def set_active(user_id: int, reminder_id: int, active: bool) -> None:
    with connect() as conn:
        _owned(conn, user_id, reminder_id)
        conn.execute("UPDATE reminders SET active = ? WHERE id = ?", (1 if active else 0, reminder_id))


def delete_reminder(user_id: int, reminder_id: int) -> None:
    with connect() as conn:
        row = _owned(conn, user_id, reminder_id)
        conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        audit.log("reminder.deleted", user_id, row["profile_id"], target=f"reminder:{reminder_id}", conn=conn)


def _ics_escape(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def to_ics(reminders: list[dict]) -> str:
    """Calendar file the user can import into their phone's calendar for actual notifications."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Thought Medione//Reminders//EN", "CALSCALE:GREGORIAN"]
    for r in reminders:
        if not r["active"]:
            continue
        d = date.fromisoformat(r["due_date"])
        lines += ["BEGIN:VEVENT", f"UID:medione-reminder-{r['id']}@thought-medione", f"DTSTAMP:{stamp}"]
        if r.get("time_of_day"):
            hh, mm = r["time_of_day"].split(":")
            lines.append(f"DTSTART:{d.strftime('%Y%m%d')}T{hh}{mm}00")
            lines.append("DURATION:PT15M")
        else:
            lines.append(f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}")
        if r["repeat"] != "none":
            rule = f"RRULE:FREQ={r['repeat'].upper()}"
            if r.get("until_date"):
                rule += f";UNTIL={date.fromisoformat(r['until_date']).strftime('%Y%m%d')}T235959Z"
            lines.append(rule)
        lines += [f"SUMMARY:{_ics_escape(r['title'])}",
                  f"DESCRIPTION:{_ics_escape((r.get('notes') or '') + ' (Reminder you created in Thought Medione — not medical advice.)')}",
                  "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_ics_escape(r['title'])}", "TRIGGER:-PT10M",
                  "END:VALARM", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
