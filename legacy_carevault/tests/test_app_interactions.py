"""AppTest-driven checks: every page and dialog renders, and core flows work through the UI."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from streamlit.testing.v1 import AppTest

from components.sidebar import ALL_PAGES


def new_app():
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()


def assert_clean(at, label):
    assert not at.exception, f"{label}: {[e.value for e in at.exception]}"
    assert not at.error, f"{label}: {[e.value for e in at.error]}"


def test_every_page_renders():
    at = new_app()
    for page in ALL_PAGES:
        at.session_state["current_page"] = page
        at.run()
        assert_clean(at, page)


@pytest.mark.parametrize("kind,rid", [
    ("visit", "HV-2026-014"), ("diagnostic", "DG-2026-015"), ("prescription", "RX-2026-081"),
    ("history", "MH-2026-016"), ("appointment", "APT-2026-008"),
])
@pytest.mark.parametrize("mode", ["view", "edit", "delete"])
def test_every_dialog_renders(kind, rid, mode):
    at = new_app()
    at.session_state["cv_dialog"] = {"kind": kind, "id": rid, "mode": mode}
    at.run()
    assert_clean(at, f"{kind}/{mode}")


def test_sidebar_navigation_buttons():
    at = new_app()
    for page in ALL_PAGES:
        at.button(key=f"nav_btn_{page}").click().run()
        assert at.session_state["current_page"] == page
        assert_clean(at, page)


def test_open_details_then_close():
    at = new_app()
    at.session_state["current_page"] = "Hospital Visits"
    at.run()
    at.button(key="visits_view_HV-2026-014").click().run()
    assert at.session_state["cv_dialog"]["id"] == "HV-2026-014"
    at.button(key="dlg_close_HV-2026-014").click().run()
    assert "cv_dialog" not in at.session_state


def test_header_search_goes_to_all_records():
    at = new_app()
    at.text_input(key="header_search_input").input("Metoprolol").run()
    assert at.session_state["current_page"] == "All Records"
    assert_clean(at, "search")
    assert any("Metoprolol" in m.value for m in at.markdown)


def test_delete_flow_requires_confirmation():
    at = new_app()
    before = len(at.session_state["hospital_visits"])
    at.session_state["cv_dialog"] = {"kind": "visit", "id": "HV-2026-001", "mode": "view"}
    at.run()
    at.button(key="dlg_delete_HV-2026-001").click().run()
    assert len(at.session_state["hospital_visits"]) == before  # nothing deleted yet
    at.button(key="dlg_confirm_delete_HV-2026-001").click().run()
    assert len(at.session_state["hospital_visits"]) == before - 1
    assert "cv_dialog" not in at.session_state


def test_cancel_appointment_flow():
    at = new_app()
    at.session_state["cv_dialog"] = {"kind": "appointment", "id": "APT-2026-009", "mode": "cancel_appointment"}
    at.run()
    at.button(key="dlg_confirm_cancel_APT-2026-009").click().run()
    df = at.session_state["appointments"]
    assert df.loc[df["apt_id"] == "APT-2026-009", "status"].iloc[0] == "Cancelled"


def test_profile_save_validates_name():
    at = new_app()
    at.session_state["current_page"] = "Settings"
    at.run()
    at.text_input(key="set_name").input("")
    at.button(key="save_profile_btn").click().run()
    assert at.session_state["patient_info"]["name"] == "Alex Morgan"
    assert "name" in at.session_state["_cv_profile_errors"]
