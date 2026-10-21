"""Automatic reminders and follow-up appointments from a prescription."""
from datetime import date, timedelta

import pytest

from medione.seed import make_pdf
from medione.services import appointments, reminders, records, rx_parser, schedule
from medione.services.documents import extract_pdf_text

TODAY = date.today()


@pytest.mark.parametrize("freq,instr,times", [
    ("1-0-1", None, ["08:00", "21:00"]),
    ("0-0-1", None, ["21:00"]),
    ("0-0-1 - 5 days", None, ["21:00"]),  # the "5" is a duration, not a 4th dose
    ("1-0-1-1", None, ["08:00", "21:00", "22:00"]),
    ("1-1-1", None, ["08:00", "14:00", "21:00"]),
    ("BD", "after food", ["08:00", "20:00"]),
    ("TDS", None, ["08:00", "14:00", "20:00"]),
    ("Once daily", "After dinner", ["21:00"]),
    ("Once daily", "before breakfast", ["08:00"]),
    ("1 puff twice daily", None, ["08:00", "20:00"]),
    ("HS", None, ["22:00"]),
    ("every 8 hours", None, ["06:00", "14:00", "22:00"]),
])
def test_written_frequency_becomes_times(freq, instr, times):
    slots, repeat, _ = schedule.parse_times(freq, instr)
    assert [t for _, t in slots] == times and repeat == "daily"


@pytest.mark.parametrize("freq,instr", [("SOS", None), ("2 puffs when needed", None), (None, None), ("as directed", None),
                                        ("5 ml", "if temperature above 100 F")])
def test_unclear_or_as_needed_gets_no_reminder(freq, instr):
    assert schedule.parse_times(freq, instr)[0] is None


def test_weekly_duration_and_relative_follow_up():
    assert schedule.parse_times("Once weekly", None)[1] == "weekly"
    start = date(2026, 1, 10)
    assert schedule.parse_duration("5 days", start) == (date(2026, 1, 14), False)
    assert schedule.parse_duration("2 weeks", start) == (date(2026, 1, 23), False)
    assert schedule.parse_duration("Long term", start) == (None, True)
    assert schedule.relative_follow_up("Review after 2 weeks with reports", start)[0] == date(2026, 1, 24)
    assert schedule.relative_follow_up("Follow-up in 3 months", start)[0] == date(2026, 4, 10)
    assert schedule.relative_follow_up("Take with water", start) is None


def test_local_reader_on_typed_pdf():
    pdf = make_pdf("Clinic - Prescription", [
        "Date: 05/10/2026", "Doctor: Dr. Asha Verma", "1. Tab. Metformin 500 mg - 1-0-1 after food - 3 months",
        "2. Cap. Vitamin D3 60000 IU - once weekly - 8 weeks", "3. Tab. Paracetamol 650 mg - SOS",
        "4. Syp. Cough syrup 10 ml", "Advice: Review after 2 weeks."])
    out = rx_parser.parse_text(extract_pdf_text(pdf))
    meds = {m["name"]: m for m in out["medications"]}
    assert out["document_type"] == "prescription" and out["record_date"] == "2026-10-05"
    assert out["doctor_name"] == "Dr. Asha Verma"
    assert meds["Metformin"]["dosage"] == "500 mg" and meds["Metformin"]["frequency"] == "1-0-1"
    assert meds["Metformin"]["duration"] == "3 months" and meds["Vitamin D3"]["dosage"] == "60000 IU"
    assert meds["Cough syrup"]["uncertain"]  # no frequency found -> must be checked
    assert rx_parser.parse_text("Haemoglobin 12.1 g/dL reference 12-15") is None


def test_plan_and_apply(make_user):
    uid, pid, *_ = make_user()
    rid = records.save_record(uid, pid, {
        "type": "prescription", "title": "Rx", "record_date": TODAY - timedelta(days=2),
        "follow_up_date": TODAY + timedelta(days=12)}, medications=[
        {"name": "Metformin", "dosage": "500 mg", "frequency": "1-0-1", "duration": "3 months"},
        {"name": "Paracetamol", "dosage": "650 mg", "frequency": "SOS"},
        {"name": "Unclear drug", "frequency": "BD", "uncertain": True},
        {"name": "Old course", "frequency": "OD", "duration": "1 day"},
    ])
    plan = schedule.build_plan(uid, rid)
    assert [(d["title"], d["time_of_day"]) for d in plan.medicine_reminders] == [
        ("Metformin 500 mg (morning)", "08:00"), ("Metformin 500 mg (night)", "21:00")]
    start = TODAY - timedelta(days=2)  # 3 calendar months from the prescription date
    assert plan.medicine_reminders[0]["until_date"] == schedule._add_months(start, 3) - timedelta(days=1)
    skipped = dict(plan.skipped)
    assert "only when needed" in skipped["Paracetamol 650 mg"]
    assert "checking" in skipped["Unclear drug"] and "ended" in skipped["Old course"]
    schedule.apply_plan(uid, rid, plan)
    rems = reminders.list_reminders(uid, pid)
    assert {r["title"] for r in rems} >= {"Metformin 500 mg (morning)", "Metformin 500 mg (night)"}
    appts = appointments.list_appointments(uid, pid)["upcoming"]
    assert len(appts) == 1 and appts[0]["starts_on"] == (TODAY + timedelta(days=12)).isoformat()
    # running it again creates nothing new
    again = schedule.apply_plan(uid, rid)
    assert again.created == [] and len(reminders.list_reminders(uid, pid)) == len(rems)
    assert len(appointments.list_appointments(uid, pid)["upcoming"]) == 1
    # after the patient confirms the unclear medicine (edit clears the flag), it can be scheduled too
    records.save_record(uid, pid, {"type": "prescription", "title": "Rx", "record_date": TODAY - timedelta(days=2),
                                   "follow_up_date": TODAY + timedelta(days=12)},
                        medications=[{"name": "Unclear drug", "frequency": "BD"}], record_id=rid)
    assert [d["title"] for d in schedule.build_plan(uid, rid).medicine_reminders] == [
        "Unclear drug (morning)", "Unclear drug (night)"]


def test_relative_follow_up_from_doctor_instructions(make_user):
    uid, pid, *_ = make_user()
    rid = records.save_record(uid, pid, {"type": "prescription", "title": "Rx", "record_date": TODAY,
                                         "details": {"doctor_instructions": "Review after 2 weeks."}},
                              medications=[{"name": "X", "frequency": "OD"}])
    plan = schedule.build_plan(uid, rid)
    assert plan.follow_up["date"] == TODAY + timedelta(days=14) and "review after 2 weeks" in plan.follow_up["how"]


def test_other_user_cannot_apply(make_user):
    uid, pid, *_ = make_user()
    other, *_ = make_user()
    rid = records.save_record(uid, pid, {"type": "prescription", "title": "Rx"}, medications=[{"name": "X", "frequency": "OD"}])
    with pytest.raises(Exception):
        schedule.apply_plan(other, rid)
