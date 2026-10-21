"""Drive the real Streamlit app headlessly."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from medione.seed import seed_demo
from medione.services import profiles, search, sharing

APP = str(Path(__file__).resolve().parent.parent / "app.py")
NAV = ["Dashboard", "Timeline", "Appointments", "Symptoms", "Vitals", "Medicines", "Lab results", "Reminders",
       "Add record", "Records", "Doctors & facilities", "Emergency card", "Share", "Family",
       "Settings", "Help"]


def _ok(at: AppTest) -> AppTest:
    assert not at.exception, [e.value for e in at.exception]
    return at


def _signed_in_demo() -> AppTest:
    at = _ok(AppTest.from_file(APP, default_timeout=60).run())
    at.button(key="demo_login").click()
    return _ok(at.run())


def test_signed_out_shows_sign_in_only():
    at = _ok(AppTest.from_file(APP, default_timeout=60).run())
    assert any(t.label == "Sign in" for t in at.tabs)
    assert not at.sidebar.button  # no navigation before signing in


def test_wrong_password_shows_error():
    seed_demo()
    at = _ok(AppTest.from_file(APP, default_timeout=60).run())
    at.text_input(key="login_email").input("demo@thoughtmedione.example")
    at.text_input(key="login_password").input("wrong-password")
    at.button[0].click()
    at = _ok(at.run())
    assert any("incorrect" in e.value for e in at.error)


def test_register_shows_recovery_code_then_home(make_user):
    at = _ok(AppTest.from_file(APP, default_timeout=60).run())
    at.text_input(key="reg_name").input("Priya")
    at.text_input(key="reg_full_name").input("Priya Sharma")
    at.text_input(key="reg_email").input("priya.ui.test@example.com")
    at.text_input(key="reg_password").input("Strong-Pass-123")
    at.text_input(key="reg_confirm").input("Strong-Pass-123")
    at.checkbox(key="reg_agree").check()
    next(b for b in at.button if b.label == "Create account").click()
    at = _ok(at.run())
    assert at.code and len(at.code[0].value) == 19
    at.checkbox(key="recovery_saved").check()
    at = _ok(at.run())
    at.button(key="recovery_continue").click()
    at = _ok(at.run())
    assert at.session_state["page"] == "Dashboard"
    assert any("set up your health record" in m.value for m in at.markdown)


def test_every_page_renders_for_demo_account():
    at = _signed_in_demo()
    for name in NAV:
        at.button(key=f"nav_{name}").click()
        at = _ok(at.run())
        assert at.session_state["page"] == name


def test_open_record_and_review_ai_extraction():
    at = _signed_in_demo()
    review = [b for b in at.button if b.key and b.key.startswith("td_review_")]
    assert review, "demo data should contain records that need review"
    review[0].click()
    at = _ok(at.run())
    assert at.session_state["page"] == "Record"
    at.button(key="rec_reviewed").click()
    at = _ok(at.run())
    assert any("reviewed" in s.value for s in at.success)


def test_switch_family_profile_changes_records():
    at = _signed_in_demo()
    uid = at.session_state["uid"]
    dad = next(p for p in profiles.list_profiles(uid) if p["relationship"] == "parent")
    at.sidebar.selectbox(key="sidebar_profile").select(dad["id"])
    at = _ok(at.run())
    assert at.session_state["profile_id"] == dad["id"]
    at.button(key="nav_Records").click()
    at = _ok(at.run())
    titles = " ".join(m.value for m in at.markdown)
    assert "Resting ECG" in titles and "Ultrasound abdomen" not in titles


def test_manual_record_creation():
    at = _signed_in_demo()
    at.button(key="nav_Add record").click()
    at = _ok(at.run())
    at.segmented_control(key="upl_mode").set_value("Type it in")
    at = _ok(at.run())
    at.selectbox(key="upl_manual_type").set_value("vaccination")
    at = _ok(at.run())
    at.text_input[0].input("Tetanus booster UI test")
    next(b for b in at.button if b.label == "Save record").click()
    at = _ok(at.run())
    assert at.session_state["page"] == "Record"
    uid, pid = at.session_state["uid"], at.session_state["profile_id"]
    assert search.search_records(uid, pid, "Tetanus booster UI test")


def test_share_link_view_and_invalid_token():
    uid = seed_demo()
    pid = profiles.self_profile_id(uid)
    rec = search.search_records(uid, pid, types=["imaging"])[0]
    _, token = sharing.create_share(uid, pid, [rec["id"]], "UI test doctor", 1)
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["share"] = token
    at = _ok(at.run())
    text = " ".join(m.value for m in at.markdown)
    assert rec["title"] in text and "Penicillin" not in text
    assert not at.sidebar.button
    bad = AppTest.from_file(APP, default_timeout=60)
    bad.query_params["share"] = "nope"
    bad = _ok(bad.run())
    assert any("isn't valid" in e.value for e in bad.error)


def test_emergency_public_view():
    from medione.services import emergency
    uid = seed_demo()
    pid = profiles.self_profile_id(uid)
    token = emergency.create_link(uid, pid)
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["emergency"] = token
    at = _ok(at.run())
    text = " ".join(m.value for m in at.markdown)
    assert "EMERGENCY MEDICAL CARD" in text and "Penicillin" in text and "HbA1c" not in text
    assert not at.sidebar.button


def test_dashboard_shows_key_sections():
    import html
    at = _signed_in_demo()
    text = html.unescape(" ".join(m.value for m in at.markdown))
    for heading in ("Upcoming appointments", "Pending for you", "Health watch", "Today's reminders",
                    "Latest readings", "Current medicines"):
        assert heading in text, heading


def test_log_symptom_and_book_appointment():
    at = _signed_in_demo()
    at.button(key="qa_Symptoms").click()
    at = _ok(at.run())
    at.text_input[0].input("Dizziness UI test")
    next(b for b in at.button if b.label == "Start tracking").click()
    at = _ok(at.run())
    assert any("Dizziness UI test" in m.value for m in at.markdown)
    at.button(key="nav_Appointments").click()
    at = _ok(at.run())
    next(t for t in at.text_input if t.label.startswith("What is it for")).input("Physio UI test")
    next(b for b in at.button if b.label == "Book appointment").click()
    at = _ok(at.run())
    assert any("Physio UI test" in m.value for m in at.markdown)


@pytest.mark.parametrize("page", ["Share", "Settings"])
def test_sign_out_clears_session(page):
    at = _signed_in_demo()
    at.button(key=f"nav_{page}").click()
    at = _ok(at.run())
    at.sidebar.button(key="nav_signout").click()
    at = _ok(at.run())
    assert "uid" not in at.session_state
