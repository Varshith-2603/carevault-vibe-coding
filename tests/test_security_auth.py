from datetime import date

import pytest

from medione import audit, auth, config, security
from medione.services import documents, records
from tests.conftest import pdf_bytes


def test_hash_and_verify():
    h = security.hash_secret("S3cret-pass")
    assert security.verify_secret("S3cret-pass", h)
    assert not security.verify_secret("wrong", h)
    assert not security.verify_secret("x", None)
    assert not security.verify_secret("x", "garbage")


def test_encrypt_round_trip():
    blob = security.encrypt(b"hello")
    assert blob != b"hello"
    assert security.decrypt(blob) == b"hello"


def test_recovery_code_normalisation():
    code = security.new_recovery_code()
    assert security.normalise_recovery_code(code.lower().replace("-", " ")) == code


@pytest.mark.parametrize("pw", ["short1A", "alllowercase123", "NoDigitsHereAtAll"])
def test_weak_passwords_rejected(pw):
    with pytest.raises(auth.AuthError):
        auth.register("weak@example.com", "W", pw, "W")


def test_register_login_and_duplicate_email(make_user):
    uid, pid, email, _ = make_user()
    assert auth.login(email.upper(), "Correct-Horse-42").id == uid
    with pytest.raises(auth.AuthError, match="already exists"):
        auth.register(email, "X", "Correct-Horse-42", "X")
    with pytest.raises(auth.AuthError, match="incorrect"):
        auth.login(email, "nope")
    with pytest.raises(auth.AuthError, match="incorrect"):
        auth.login("nobody@example.com", "Correct-Horse-42")


def test_lockout_after_repeated_failures(make_user):
    _, _, email, _ = make_user()
    for _ in range(config.settings.max_login_attempts):
        with pytest.raises(auth.AuthError):
            auth.login(email, "bad-password")
    with pytest.raises(auth.AuthError, match="Too many"):
        auth.login(email, "Correct-Horse-42")


def test_recovery_code_resets_password_once(make_user):
    _, _, email, code = make_user()
    fresh = auth.reset_with_recovery_code(email, code, "Brand-New-Pass-9")
    assert auth.login(email, "Brand-New-Pass-9")
    with pytest.raises(auth.AuthError):
        auth.reset_with_recovery_code(email, code, "Another-Pass-99")  # old code used up
    auth.reset_with_recovery_code(email, fresh, "Another-Pass-99")


def test_audit_log_has_no_secrets(make_user):
    uid, _, email, _ = make_user()
    auth.login(email, "Correct-Horse-42")
    for entry in audit.recent(uid):
        assert "Correct-Horse-42" not in str(entry)


def test_delete_account_removes_data_and_files(make_user):
    uid, pid, email, _ = make_user()
    rid = records.save_record(uid, pid, {"type": "other", "title": "Doc", "record_date": date(2025, 1, 1)})
    doc_id = documents.store_document(uid, pid, "a.pdf", pdf_bytes(), record_id=rid)
    row, _ = documents.read_document(uid, doc_id)
    stored = config.settings.documents_dir / row["storage_name"]
    assert stored.exists()
    with pytest.raises(auth.AuthError):
        auth.delete_account(uid, "wrong")
    auth.delete_account(uid, "Correct-Horse-42")
    assert not stored.exists()
    assert auth.get_user(uid) is None
    with pytest.raises(auth.AuthError):
        auth.login(email, "Correct-Horse-42")
