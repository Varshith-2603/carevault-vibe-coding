"""Users and family profiles must never see each other's data; share links expose only what was chosen."""
from datetime import date, datetime, timedelta, timezone

import pytest

from medione.db import connect
from medione.services import directory, documents, profiles, records, reminders, search, sharing
from medione.services.access import AccessDenied
from tests.conftest import pdf_bytes


def _record(uid, pid, title="Report", **kw):
    return records.save_record(uid, pid, {"type": "lab_report", "title": title, "record_date": date(2026, 1, 5), **kw},
                               lab_results=[{"test_name": "HbA1c", "value_text": "5.8", "unit": "%"}])


def test_other_user_cannot_read_or_change(make_user):
    a_uid, a_pid, *_ = make_user("Alice")
    b_uid, b_pid, *_ = make_user("Bob")
    rid = _record(a_uid, a_pid)
    doc = documents.store_document(a_uid, a_pid, "r.pdf", pdf_bytes(), record_id=rid)
    with pytest.raises(AccessDenied):
        records.get_record(b_uid, rid)
    with pytest.raises(AccessDenied):
        records.delete_record(b_uid, rid)
    with pytest.raises(AccessDenied):
        documents.read_document(b_uid, doc)
    with pytest.raises(AccessDenied):
        profiles.get_profile(b_uid, a_pid)
    with pytest.raises(AccessDenied):
        search.search_records(b_uid, a_pid)
    with pytest.raises(AccessDenied):  # writing into someone else's profile
        records.save_record(b_uid, a_pid, {"type": "other", "title": "x"})
    with pytest.raises(AccessDenied):  # editing someone else's record via own profile
        records.save_record(b_uid, b_pid, {"type": "other", "title": "x"}, record_id=rid)
    with pytest.raises(AccessDenied):
        sharing.create_share(b_uid, a_pid, [rid], "x", 1)
    with pytest.raises(ValueError):
        sharing.create_share(b_uid, b_pid, [rid], "x", 1)  # record not in Bob's profile


def test_other_users_doctor_cannot_be_linked(make_user):
    a_uid, a_pid, *_ = make_user()
    b_uid, b_pid, *_ = make_user()
    a_doc = directory.save_doctor(a_uid, {"name": "Dr. A"})
    with pytest.raises(AccessDenied):
        records.save_record(b_uid, b_pid, {"type": "other", "title": "x", "doctor_id": a_doc})


def test_family_profiles_are_separate(make_user):
    uid, me, *_ = make_user()
    kid = profiles.create_profile(uid, {"full_name": "Kid", "relationship": "child"}, "authorised")
    _record(uid, me, "Mine")
    _record(uid, kid, "Kid's")
    assert [r["title"] for r in search.search_records(uid, me)] == ["Mine"]
    assert [r["title"] for r in search.search_records(uid, kid)] == ["Kid's"]
    assert all(m["profile_id"] == kid for m in records.list_lab_results(uid, kid))
    with pytest.raises(ValueError):
        profiles.create_profile(uid, {"full_name": "No consent", "relationship": "child"}, "")
    with pytest.raises(AccessDenied):
        profiles.delete_profile(uid, me)
    rid_kid = search.search_records(uid, kid)[0]["id"]
    with pytest.raises(ValueError):  # a record can't be moved between profiles by editing
        records.save_record(uid, me, {"type": "other", "title": "move"}, record_id=rid_kid)
    with pytest.raises(ValueError):  # reminder can't link to another profile's record
        reminders.save_reminder(uid, me, {"kind": "other", "title": "x", "due_date": date.today(),
                                          "source_record_id": rid_kid})


def test_share_exposes_only_selected_records(make_user):
    uid, pid, *_ = make_user()
    shared = _record(uid, pid, "Shared one")
    private = _record(uid, pid, "Private one")
    d_shared = documents.store_document(uid, pid, "s.pdf", pdf_bytes(), record_id=shared)
    d_private = documents.store_document(uid, pid, "p.pdf", pdf_bytes(), record_id=private)
    sid, token = sharing.create_share(uid, pid, [shared], "Dr. X", 24, include_files=True)
    view = sharing.open_share(token)
    assert [r["title"] for r in view["records"]] == ["Shared one"]
    _, data = sharing.shared_document(token, d_shared)
    assert data.startswith(b"%PDF")
    with pytest.raises(sharing.ShareUnavailable):
        sharing.shared_document(token, d_private)
    # token is stored only as a hash
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM share_links WHERE token_hash = ?", (token,)).fetchone()[0] == 0
    assert sharing.list_shares(uid, pid)[0]["access_count"] == 1


def test_share_without_files_blocks_downloads(make_user):
    uid, pid, *_ = make_user()
    rid = _record(uid, pid)
    doc = documents.store_document(uid, pid, "s.pdf", pdf_bytes(), record_id=rid)
    _, token = sharing.create_share(uid, pid, [rid], "Dr. Y", 1, include_files=False)
    assert sharing.open_share(token)["records"][0]["documents"] == []
    with pytest.raises(sharing.ShareUnavailable):
        sharing.shared_document(token, doc)


def test_revoked_and_expired_links_stop_working(make_user):
    uid, pid, *_ = make_user()
    rid = _record(uid, pid)
    sid, token = sharing.create_share(uid, pid, [rid], "Dr. Z", 1)
    sharing.revoke(uid, sid)
    with pytest.raises(sharing.ShareUnavailable, match="turned it off"):
        sharing.open_share(token)
    sid2, token2 = sharing.create_share(uid, pid, [rid], "Dr. Z", 1)
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with connect() as conn:
        conn.execute("UPDATE share_links SET expires_at = ? WHERE id = ?", (past, sid2))
    with pytest.raises(sharing.ShareUnavailable, match="expired"):
        sharing.open_share(token2)
    with pytest.raises(sharing.ShareUnavailable):
        sharing.open_share("not-a-real-token")


def test_deleted_record_disappears_from_share(make_user):
    uid, pid, *_ = make_user()
    rid = _record(uid, pid)
    _, token = sharing.create_share(uid, pid, [rid], "Dr. Q", 1)
    records.delete_record(uid, rid)
    assert sharing.open_share(token)["records"] == []


def test_share_validation(make_user):
    uid, pid, *_ = make_user()
    rid = _record(uid, pid)
    with pytest.raises(ValueError):
        sharing.create_share(uid, pid, [], "x", 1)
    with pytest.raises(ValueError):
        sharing.create_share(uid, pid, [rid], "", 1)
    with pytest.raises(ValueError):
        sharing.create_share(uid, pid, [rid], "x", 99999)
