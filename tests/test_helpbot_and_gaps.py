"""Medi chatbot, plain-language search, change history, emergency-card choices, summary additions."""
from datetime import date, timedelta
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from medione.seed import seed_demo
from medione.services import (appointments, emergency, helpbot, nlsearch, profiles, records, search, summary)

TODAY = date.today()
APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(scope="module")
def demo():
    uid = seed_demo()
    plist = {p["relationship"]: p["id"] for p in profiles.list_profiles(uid)}
    return uid, plist["self"], plist["parent"]


# ------------------------------------------------------------------ helpbot
@pytest.mark.parametrize("q", ["I have chest pain", "my father can't breathe", "he fainted"])
def test_emergency_words_always_get_112(demo, q):
    uid, me, _ = demo
    r = helpbot.answer(uid, me, q)
    assert r.urgent and "112" in r.text


def test_self_harm_gets_helpline(demo):
    uid, me, _ = demo
    r = helpbot.answer(uid, me, "I want to end my life")
    assert r.urgent and "14416" in r.text


@pytest.mark.parametrize("q", ["Should I stop metformin?", "can I double my dose", "should i take more tablets"])
def test_no_treatment_advice(demo, q):
    uid, me, _ = demo
    r = helpbot.answer(uid, me, q)
    assert r.source == "Safety" and "can't advise" in r.text


def test_answers_come_from_records(demo):
    uid, me, dad = demo
    nxt = appointments.list_appointments(uid, me)["upcoming"][0]
    assert nxt["purpose"] in helpbot.answer(uid, me, "When is my next appointment?").text
    meds = helpbot.answer(uid, me, "what medicines am I taking").text
    assert "Metformin" in meds and "Amlodipine" not in meds  # father's medicine never leaks into Ananya's answer
    assert "Amlodipine" in helpbot.answer(uid, dad, "what medicines am I taking").text
    assert "Penicillin" in helpbot.answer(uid, me, "any allergies?").text
    lab = helpbot.answer(uid, me, "my hba1c result")
    assert "HbA1c" in lab.text and lab.records


def test_search_never_invents_records(demo):
    uid, me, _ = demo
    r = helpbot.answer(uid, me, "find my MRI report from March")
    assert not r.records and "couldn't find" in r.text
    r = helpbot.answer(uid, me, "find my latest blood test")
    assert len(r.records) == 1
    newest = search.search_records(uid, me, types=["lab_report"])[0]
    assert r.records[0]["id"] == newest["id"]


def test_glossary_faq_and_fallback(demo):
    uid, me, _ = demo
    assert "twice a day" in helpbot.answer(uid, me, "what does BD mean").text
    assert "Family" in helpbot.answer(uid, me, "how do I add my mother?").text
    assert helpbot.answer(uid, me, "open vitals").actions == [("Open Vitals", "Vitals")]
    assert helpbot.answer(uid, me, "qwertyuiop").suggestions  # graceful fallback, AI not configured


# ----------------------------------------------------------------- nlsearch
@pytest.mark.parametrize("q,types,has_dates", [
    ("Find my latest blood test report", ["lab_report"], False),
    ("Show my prescriptions from last year", ["prescription"], True),
    ("previous hospital discharge summary", ["admission"], False),
    ("records from Sunrise Diagnostics", [], False),
])
def test_nl_parse(demo, q, types, has_dates):
    uid, me, _ = demo
    f = nlsearch.parse(uid, me, q)
    assert f["types"] == types and bool(f["date_from"]) == has_dates


def test_nl_last_year_range_and_doctor(demo):
    uid, me, _ = demo
    f = nlsearch.parse(uid, me, "prescriptions from last year", today=date(2026, 5, 1))
    assert (f["date_from"], f["date_to"]) == (date(2025, 1, 1), date(2025, 12, 31))
    f, results = nlsearch.run(uid, me, "records from Dr. Vivek Menon")
    assert f["doctor_id"] and results and all(r["doctor_name"] == "Dr. Vivek Menon" for r in results)


# ------------------------------------------------------------ change history
def test_record_change_history(make_user):
    uid, pid, *_ = make_user()
    rid = records.save_record(uid, pid, {"type": "prescription", "title": "Rx", "record_date": "2026-01-01",
                                         "source": "ai_extracted"},
                              medications=[{"name": "Drug A", "dosage": "5 mg", "uncertain": True}])
    records.save_record(uid, pid, {"type": "prescription", "title": "Rx", "record_date": "2026-01-02",
                                   "source": "ai_extracted"},
                        medications=[{"name": "Drug A", "dosage": "10 mg"}], record_id=rid)
    records.save_record(uid, pid, {"type": "prescription", "title": "Rx", "record_date": "2026-01-02",
                                   "source": "ai_extracted"}, record_id=rid)  # no change -> no entry
    records.mark_reviewed(uid, rid)
    hist = records.record_history(uid, rid)
    assert [h["summary"].split(":")[0] for h in hist] == ["Checked against the original document and confirmed",
                                                          "Edited", "Record created"]
    edit = {c["field"]: c for c in hist[1]["changes"]}
    assert edit["record_date"]["before"] == "2026-01-01" and edit["record_date"]["after"] == "2026-01-02"
    assert "5 mg" in edit["medications"]["before"] and "10 mg" in edit["medications"]["after"]
    b_uid, *_ = make_user()
    with pytest.raises(Exception):
        records.record_history(b_uid, rid)


# ------------------------------------------------------------- emergency card
def test_emergency_card_choices(make_user):
    uid, pid, *_ = make_user()
    records.save_record(uid, pid, {"type": "prescription", "title": "Rx"}, medications=[{"name": "Secret Med"}])
    emergency.set_include(uid, pid, {"medicines": False, "surgeries": True})
    card = emergency.card_data(uid, pid)
    assert card["medicines"] == [] and card["include"]["surgeries"] and card["updated_at"]
    token = emergency.create_link(uid, pid)
    assert "Secret Med" not in str(emergency.open_card(token))


# ------------------------------------------------------------------ summary
def test_summary_includes_upcoming_but_not_when_shared(make_user):
    uid, pid, *_ = make_user()
    rid = records.save_record(uid, pid, {"type": "consultation", "title": "Visit", "record_date": TODAY,
                                         "follow_up_date": TODAY + timedelta(days=7)})
    dx = records.save_record(uid, pid, {"type": "diagnosis", "title": "Asthma", "record_date": TODAY})
    appointments.save_appointment(uid, pid, {"starts_on": TODAY + timedelta(days=3), "purpose": "Review"})
    full = summary.build_summary(uid, pid)
    assert [u["kind"] for u in full["upcoming"]] == ["Appointment", "Follow-up"]
    html = summary.summary_html(full)
    assert "Upcoming appointments" in html and f"ref #{dx}" in html
    shared = summary.build_summary(uid, pid, [rid])
    assert shared["upcoming"] == [] and "Upcoming appointments" not in summary.summary_html(shared)


# ----------------------------------------------------------------------- UI
def _ok(at):
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_chatbot_toy_opens_and_answers():
    at = _ok(AppTest.from_file(APP, default_timeout=90).run())
    at.button(key="demo_login").click()
    at = _ok(at.run())
    assert "nav_AI assistant" not in [b.key for b in at.button]  # removed from the menu
    at.button(key="tm_bot_toggle").click()
    at = _ok(at.run())
    assert at.session_state["bot_open"]
    chip = next(b for b in at.button if b.key and b.key.startswith("bot_sug_"))  # greeting offers suggestion chips
    assert chip.label == "When is my next appointment?"
    chip.click()
    at = _ok(at.run())
    assert "Your next appointment is" in " ".join(m.value for m in at.markdown)
    at.text_input(key="bot_input").input("find my latest blood test")
    next(b for b in at.button if b.label == "Send").click()
    at = _ok(at.run())
    rec_buttons = [b for b in at.button if b.key and b.key.startswith("bot_rec_")]
    assert len(rec_buttons) == 1 and len(at.session_state["bot_msgs"]) == 5
    rec_buttons[0].click()  # opening a record from the chat navigates to it
    at = _ok(at.run())
    assert at.session_state["page"] == "Record"
    # switching profile clears the conversation (no cross-profile leakage)
    uid = at.session_state["uid"]
    dad = next(p for p in profiles.list_profiles(uid) if p["relationship"] == "parent")
    at.sidebar.selectbox(key="sidebar_profile").select(dad["id"])
    at = _ok(at.run())
    assert not at.session_state["bot_msgs"] if "bot_msgs" in at.session_state else True
