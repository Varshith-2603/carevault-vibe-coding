from datetime import date
from types import SimpleNamespace

import pytest

from medione.ai import client as ai_client
from medione.ai import tasks as ai_tasks
from medione.services import reminders
from tests.conftest import pdf_bytes


def _rem(**kw):
    base = {"due_date": "2026-01-31", "repeat": "none", "until_date": None, "last_done_on": None}
    base.update(kw)
    return base


def test_next_occurrence_rules():
    today = date(2026, 3, 15)
    assert reminders.next_occurrence(_rem(), today) == date(2026, 1, 31)  # one-off, overdue
    assert reminders.next_occurrence(_rem(last_done_on="2026-02-01"), today) is None
    assert reminders.next_occurrence(_rem(repeat="daily"), today) == today
    assert reminders.next_occurrence(_rem(repeat="daily", last_done_on="2026-03-15"), today) == date(2026, 3, 16)
    assert reminders.next_occurrence(_rem(repeat="monthly"), today) == date(2026, 3, 31)
    assert reminders.next_occurrence(_rem(repeat="weekly", until_date="2026-02-28"), today) is None
    assert reminders.next_occurrence(_rem(due_date="2026-12-01", repeat="yearly"), today) == date(2026, 12, 1)


def test_reminder_validation_and_ics(make_user):
    uid, pid, *_ = make_user()
    with pytest.raises(ValueError):
        reminders.save_reminder(uid, pid, {"kind": "medication", "title": "", "due_date": date.today()})
    with pytest.raises(ValueError, match="08:30"):
        reminders.save_reminder(uid, pid, {"kind": "medication", "title": "x", "due_date": date.today(),
                                           "time_of_day": "8am"})
    rid = reminders.save_reminder(uid, pid, {"kind": "medication", "title": "Tab, one; daily", "due_date": date.today(),
                                             "time_of_day": "21:00", "repeat": "daily"})
    items = reminders.list_reminders(uid, pid)
    assert items[0]["due_today"]
    ics = reminders.to_ics(items)
    assert "RRULE:FREQ=DAILY" in ics and "Tab\\, one\\; daily" in ics and "T210000" in ics
    reminders.mark_done(uid, rid)
    assert reminders.list_reminders(uid, pid)[0]["next_due"] > date.today().isoformat()


class FakeMessages:
    def __init__(self, text, stop_reason="end_turn"):
        self.text, self.stop_reason, self.calls = text, stop_reason, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(stop_reason=self.stop_reason, content=[SimpleNamespace(type="text", text=self.text)])


@pytest.fixture
def fake_ai():
    def install(text, stop_reason="end_turn"):
        msgs = FakeMessages(text, stop_reason)
        ai_client.set_client_for_tests(SimpleNamespace(beta=SimpleNamespace(messages=msgs)))
        return msgs
    yield install
    ai_client.set_client_for_tests(None)


def test_ai_unavailable_without_configuration():
    assert not ai_client.is_configured()
    with pytest.raises(ai_client.AIUnavailable):
        ai_tasks.explain_term("HbA1c")


def test_extraction_request_and_mapping(fake_ai):
    import json
    payload = {"document_type": "made_up_type", "title": "Rx", "record_date": "2026-01-02", "end_date": None,
               "follow_up_date": None, "doctor_name": "Dr. A", "facility_name": None, "condition": None,
               "summary": None, "extra_fields": [], "medications": [], "lab_results": [], "uncertain_fields": [],
               "legibility_note": None}
    msgs = fake_ai(json.dumps(payload))
    out = ai_tasks.extract_document(pdf_bytes(), "application/pdf")
    assert out["document_type"] == "other"  # unknown types fall back safely
    call = msgs.calls[0]
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["messages"][0]["content"][0]["type"] == "document"
    assert "never suggest starting, stopping or changing" in call["system"]
    assert call["fallbacks"] == "default"


def test_ai_refusal_and_bad_json_are_reported(fake_ai):
    fake_ai("{}", stop_reason="refusal")
    with pytest.raises(ai_client.AIError, match="declined"):
        ai_tasks.explain_term("x")
    fake_ai("not json")
    with pytest.raises(ai_client.AIError):
        ai_tasks.explain_term("x")
