"""Appointments, symptoms, vitals, emergency card and the dashboard aggregation."""
from datetime import date, timedelta

import pytest

from medione.services import (appointments, dashboard, directory, emergency, health, profiles, records,
                              visit_prep)
from medione.services.access import AccessDenied

TODAY = date.today()


def test_appointments_split_and_status(make_user):
    uid, pid, *_ = make_user()
    doc = directory.save_doctor(uid, {"name": "Dr. Test"})
    future = appointments.save_appointment(uid, pid, {"starts_on": TODAY + timedelta(days=3), "time_of_day": "10:30",
                                                      "purpose": "Review", "doctor_id": doc,
                                                      "questions": "Q1\nQ2"})
    past = appointments.save_appointment(uid, pid, {"starts_on": TODAY - timedelta(days=2), "purpose": "Old"})
    data = appointments.list_appointments(uid, pid)
    assert [a["id"] for a in data["upcoming"]] == [future] and data["upcoming"][0]["days_away"] == 3
    assert [a["id"] for a in data["needs_update"]] == [past]
    appointments.set_status(uid, past, "completed", "Dose changed")
    data = appointments.list_appointments(uid, pid)
    assert data["needs_update"] == [] and data["history"][0]["outcome"] == "Dose changed"
    ics = appointments.appointment_ics(appointments.get_appointment(uid, future))
    assert "T103000" in ics and "Dr. Test" in ics
    html = visit_prep.visit_prep_html(uid, future)
    assert "Q1" in html and "Q2" in html
    with pytest.raises(ValueError):
        appointments.save_appointment(uid, pid, {"starts_on": TODAY, "purpose": ""})
    with pytest.raises(ValueError):
        appointments.save_appointment(uid, pid, {"starts_on": TODAY, "purpose": "x", "time_of_day": "10am"})


def test_appointments_isolated_between_users(make_user):
    a_uid, a_pid, *_ = make_user()
    b_uid, b_pid, *_ = make_user()
    aid = appointments.save_appointment(a_uid, a_pid, {"starts_on": TODAY, "purpose": "Mine"})
    with pytest.raises(ValueError):
        appointments.get_appointment(b_uid, aid)
    with pytest.raises(ValueError):
        appointments.delete_appointment(b_uid, aid)
    with pytest.raises(AccessDenied):
        appointments.list_appointments(b_uid, a_pid)


def test_concern_tracking_trend(make_user):
    uid, pid, *_ = make_user()
    cid = health.save_concern(uid, pid, {"title": "Headache", "severity": 1, "logged_on": TODAY - timedelta(days=3)})
    health.log_concern(uid, cid, 3, "worse")
    c = health.list_concerns(uid, pid, "active")[0]
    assert c["severity"] == 3 and c["trend"] == "worse"
    health.set_concern_status(uid, cid, True)
    assert health.list_concerns(uid, pid, "active") == []
    with pytest.raises(ValueError):
        health.save_concern(uid, pid, {"title": " "})
    with pytest.raises(ValueError):
        health.save_concern(uid, pid, {"title": "x", "started_on": TODAY + timedelta(days=1)})
    b_uid, *_ = make_user()
    with pytest.raises(ValueError):
        health.log_concern(b_uid, cid, 1)


@pytest.mark.parametrize("data,flag", [
    ({"kind": "bp", "value1": 150, "value2": 85}, "high"),
    ({"kind": "bp", "value1": 118, "value2": 76}, None),
    ({"kind": "bp", "value1": 85, "value2": 55}, "low"),
    ({"kind": "sugar", "value1": 110, "context": "Fasting"}, "high"),
    ({"kind": "sugar", "value1": 130, "context": "After meal (2 h)"}, None),
    ({"kind": "spo2", "value1": 93}, "low"),
    ({"kind": "temp", "value1": 38.4}, "high"),
    ({"kind": "weight", "value1": 70}, None),
])
def test_vital_flags(make_user, data, flag):
    uid, pid, *_ = make_user()
    vid = health.save_vital(uid, pid, data)
    row = [r for r in health.list_vitals(uid, pid) if r["id"] == vid][0]
    assert row["flag"] == flag


def test_vital_validation(make_user):
    uid, pid, *_ = make_user()
    with pytest.raises(ValueError, match="higher"):
        health.save_vital(uid, pid, {"kind": "bp", "value1": 80, "value2": 120})
    with pytest.raises(ValueError, match="mistyped"):
        health.save_vital(uid, pid, {"kind": "spo2", "value1": 140})
    with pytest.raises(ValueError, match="future"):
        health.save_vital(uid, pid, {"kind": "weight", "value1": 70, "measured_on": TODAY + timedelta(days=1)})
    with pytest.raises(ValueError, match="number"):
        health.save_vital(uid, pid, {"kind": "pulse", "value1": None})


def test_emergency_card_shows_only_critical_info(make_user):
    uid, pid, *_ = make_user()
    profiles.update_profile(uid, pid, {"blood_group": "O-", "emergency_contact_phone": "+91 1"})
    records.save_record(uid, pid, {"type": "allergy", "title": "Peanut", "details": {"allergen": "Peanuts"}})
    records.save_record(uid, pid, {"type": "lab_report", "title": "Private lab report"})
    token = emergency.create_link(uid, pid)
    card = emergency.open_card(token)
    assert card["blood_group"] == "O-" and card["allergies"][0]["what"] == "Peanuts"
    assert "Private lab report" not in str(card)
    new_token = emergency.create_link(uid, pid)  # replaces the old one
    with pytest.raises(emergency.CardUnavailable):
        emergency.open_card(token)
    emergency.revoke(uid, pid)
    with pytest.raises(emergency.CardUnavailable):
        emergency.open_card(new_token)
    assert emergency.qr_png("https://example.com").startswith(b"\x89PNG")


def test_dashboard_todos(make_user):
    uid, pid, *_ = make_user()
    records.save_record(uid, pid, {"type": "consultation", "title": "Visit", "record_date": TODAY - timedelta(days=30),
                                   "follow_up_date": TODAY + timedelta(days=10)})
    records.save_record(uid, pid, {"type": "insurance", "title": "Policy", "record_date": TODAY - timedelta(days=300),
                                   "end_date": TODAY + timedelta(days=20)})
    records.save_record(uid, pid, {"type": "prescription", "title": "Rx", "record_date": TODAY - timedelta(days=5),
                                   "source": "ai_extracted"},
                        medications=[{"name": "Drug A", "end_date": TODAY + timedelta(days=2)}])
    appointments.save_appointment(uid, pid, {"starts_on": TODAY - timedelta(days=1), "purpose": "Past visit"})
    d = dashboard.build(uid, pid)
    kinds = sorted(t["kind"] for t in d["todos"])
    assert kinds == ["appointment", "follow_up", "insurance", "medicine", "review"]
    # booking an appointment near the follow-up date clears that nudge
    appointments.save_appointment(uid, pid, {"starts_on": TODAY + timedelta(days=11), "purpose": "Follow-up"})
    assert "follow_up" not in [t["kind"] for t in dashboard.build(uid, pid)["todos"]]


def test_sample_data_covers_every_screen():
    from medione.db import connect
    from medione.models import RECORD_TYPES
    from medione.seed import seed_demo
    uid = seed_demo()
    plist = profiles.list_profiles(uid)
    assert len(plist) == 4
    with connect() as conn:
        used = {r[0] for r in conn.execute(
            "SELECT DISTINCT r.type FROM records r JOIN profiles p ON p.id = r.profile_id WHERE p.user_id = ?", (uid,))}
        for p in plist:
            for table in ("records", "appointments", "vitals", "reminders", "health_concerns"):
                assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE profile_id = ?", (p["id"],)).fetchone()[0], \
                    (p["full_name"], table)
        states = {r[0] for r in conn.execute("SELECT CASE WHEN revoked_at IS NOT NULL THEN 'revoked' WHEN expires_at < "
                                             "datetime('now') THEN 'expired' ELSE 'active' END FROM share_links "
                                             "WHERE user_id = ?", (uid,))}
    assert used == set(RECORD_TYPES)
    assert states == {"active", "expired", "revoked"}
