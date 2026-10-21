"""Account registration, sign-in with lockout, recovery codes and account deletion."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from medione import audit, config, security
from medione.db import connect, now_iso

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(Exception):
    """A user-facing authentication problem (message is safe to display)."""


@dataclass
class User:
    id: int
    email: str
    display_name: str
    ai_consent_at: Optional[str]


def _row_to_user(row) -> User:
    return User(row["id"], row["email"], row["display_name"], row["ai_consent_at"])


def get_user(user_id: int) -> Optional[User]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_user(row) if row else None


def register(email: str, display_name: str, password: str, full_name: str) -> tuple[User, str]:
    """Create an account plus its own ("self") profile. Returns the user and a one-time recovery code."""
    email = email.strip().lower()
    display_name = display_name.strip()
    full_name = full_name.strip() or display_name
    if not EMAIL_RE.match(email):
        raise AuthError("Enter a valid email address.")
    if not display_name:
        raise AuthError("Enter your name.")
    problems = security.password_problems(password, email)
    if problems:
        raise AuthError(" ".join(problems))
    recovery = security.new_recovery_code()
    now = now_iso()
    with connect() as conn:
        if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise AuthError("An account with this email already exists. Sign in instead.")
        cur = conn.execute(
            "INSERT INTO users (email, display_name, password_hash, recovery_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (email, display_name, security.hash_secret(password), security.hash_secret(recovery), now),
        )
        user_id = cur.lastrowid
        conn.execute(
            "INSERT INTO profiles (user_id, full_name, relationship, consent_statement, consent_at, created_at) "
            "VALUES (?, ?, 'self', 'Account holder', ?, ?)",
            (user_id, full_name, now, now),
        )
        audit.log("account.created", user_id, conn=conn)
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _row_to_user(row), recovery


def _locked(row) -> Optional[datetime]:
    if row["locked_until"]:
        until = datetime.fromisoformat(row["locked_until"])
        if until > datetime.now(timezone.utc):
            return until
    return None


def login(email: str, password: str) -> User:
    email = email.strip().lower()
    generic = "Email or password is incorrect."
    error = None  # raised after the block so failure counters are committed, not rolled back
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if row is None:
            security.verify_secret(password, security.hash_secret("timing-equaliser", 1000))
            error = generic
        elif _locked(row):
            error = "Too many failed attempts. Try again in a few minutes or reset your password."
        elif not security.verify_secret(password, row["password_hash"]):
            failed = row["failed_logins"] + 1
            locked_until = None
            if failed >= config.settings.max_login_attempts:
                locked_until = (datetime.now(timezone.utc) + timedelta(minutes=config.settings.lockout_minutes)).isoformat()
                failed = 0
                audit.log("login.locked", row["id"], conn=conn)
            else:
                audit.log("login.failed", row["id"], conn=conn)
            conn.execute("UPDATE users SET failed_logins = ?, locked_until = ? WHERE id = ?", (failed, locked_until, row["id"]))
            error = generic
        else:
            conn.execute("UPDATE users SET failed_logins = 0, locked_until = NULL, last_login_at = ? WHERE id = ?",
                         (now_iso(), row["id"]))
            audit.log("login.success", row["id"], conn=conn)
    if error:
        raise AuthError(error)
    return _row_to_user(row)


def reset_with_recovery_code(email: str, code: str, new_password: str) -> str:
    """Set a new password using the recovery code. Returns a fresh recovery code (old one is used up)."""
    email = email.strip().lower()
    problems = security.password_problems(new_password, email)
    if problems:
        raise AuthError(" ".join(problems))
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        valid = row is not None and security.verify_secret(security.normalise_recovery_code(code), row["recovery_hash"])
        if row is not None and not valid:
            audit.log("recovery.failed", row["id"], conn=conn)
    if not valid:
        raise AuthError("That email and recovery code don't match.")
    with connect() as conn:
        fresh = security.new_recovery_code()
        conn.execute(
            "UPDATE users SET password_hash = ?, recovery_hash = ?, failed_logins = 0, locked_until = NULL WHERE id = ?",
            (security.hash_secret(new_password), security.hash_secret(fresh), row["id"]),
        )
        audit.log("password.reset_with_recovery", row["id"], conn=conn)
    return fresh


def change_password(user_id: int, current: str, new_password: str) -> None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None or not security.verify_secret(current, row["password_hash"]):
            raise AuthError("Your current password is incorrect.")
        problems = security.password_problems(new_password, row["email"])
        if problems:
            raise AuthError(" ".join(problems))
        conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (security.hash_secret(new_password), user_id))
        audit.log("password.changed", user_id, conn=conn)


def regenerate_recovery_code(user_id: int, password: str) -> str:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None or not security.verify_secret(password, row["password_hash"]):
            raise AuthError("Your password is incorrect.")
        code = security.new_recovery_code()
        conn.execute("UPDATE users SET recovery_hash = ? WHERE id = ?", (security.hash_secret(code), user_id))
        audit.log("recovery.regenerated", user_id, conn=conn)
    return code


def set_ai_consent(user_id: int, consent: bool) -> None:
    with connect() as conn:
        conn.execute("UPDATE users SET ai_consent_at = ? WHERE id = ?", (now_iso() if consent else None, user_id))
        audit.log("ai.consent_given" if consent else "ai.consent_withdrawn", user_id, conn=conn)


def delete_account(user_id: int, password: str) -> None:
    """Permanently remove the account, every profile, record, file and share link."""
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None or not security.verify_secret(password, row["password_hash"]):
            raise AuthError("Your password is incorrect.")
        storage = [r["storage_name"] for r in conn.execute(
            "SELECT d.storage_name FROM documents d JOIN profiles p ON p.id = d.profile_id WHERE p.user_id = ?",
            (user_id,))]
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.execute("DELETE FROM audit_log WHERE user_id = ?", (user_id,))
    for name in storage:
        path = config.settings.documents_dir / name
        if path.exists():
            path.unlink()
    audit.log("account.deleted", None, detail=f"user {user_id}")
