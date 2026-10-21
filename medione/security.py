"""Password hashing, random tokens and encryption of stored documents.

* Passwords and recovery codes: PBKDF2-HMAC-SHA256 with a per-hash random salt.
* Share tokens: random 256-bit values; only their SHA-256 hash is stored.
* Documents: Fernet (AES-128-CBC + HMAC-SHA256). The key comes from
  ``MEDIONE_ENCRYPTION_KEY``; for local development a key file is generated
  inside the data folder. Losing the key makes stored documents unreadable.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import string

from cryptography.fernet import Fernet, InvalidToken

from medione import config

_ALGO = "pbkdf2_sha256"


def hash_secret(secret: str, iterations: int | None = None) -> str:
    iterations = iterations or config.settings.pbkdf2_iterations
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, iterations)
    return f"{_ALGO}${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_secret(secret: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, iterations, salt_b64, digest_b64 = stored.split("$")
        if algo != _ALGO:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), base64.b64decode(salt_b64), int(iterations))
        return hmac.compare_digest(digest, base64.b64decode(digest_b64))
    except (ValueError, TypeError):
        return False


def new_recovery_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    alphabet = alphabet.translate(str.maketrans("", "", "O0I1"))
    raw = "".join(secrets.choice(alphabet) for _ in range(16))
    return "-".join(raw[i:i + 4] for i in range(0, 16, 4))


def normalise_recovery_code(code: str) -> str:
    raw = "".join(ch for ch in code.upper() if ch.isalnum())
    return "-".join(raw[i:i + 4] for i in range(0, len(raw), 4))


def new_share_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- encryption
_fernet: Fernet | None = None
_fernet_source: str | None = None


def _load_key() -> bytes:
    env_key = os.environ.get("MEDIONE_ENCRYPTION_KEY")
    if env_key:
        return env_key.encode()
    if config.settings.production:
        raise RuntimeError("MEDIONE_ENCRYPTION_KEY must be set in production.")
    key_file = config.settings.key_file
    key_file.parent.mkdir(parents=True, exist_ok=True)
    if not key_file.exists():
        key_file.write_bytes(Fernet.generate_key())
    return key_file.read_bytes().strip()


def fernet() -> Fernet:
    global _fernet, _fernet_source
    source = str(config.settings.key_file) + "|" + os.environ.get("MEDIONE_ENCRYPTION_KEY", "")
    if _fernet is None or _fernet_source != source:
        _fernet = Fernet(_load_key())
        _fernet_source = source
    return _fernet


def encrypt(data: bytes) -> bytes:
    return fernet().encrypt(data)


def decrypt(token: bytes) -> bytes:
    try:
        return fernet().decrypt(token)
    except InvalidToken as exc:
        raise ValueError("This file could not be decrypted with the current encryption key.") from exc


def password_problems(password: str, email: str = "") -> list[str]:
    problems = []
    if len(password) < 10:
        problems.append("Use at least 10 characters.")
    if password.lower() == password or password.upper() == password:
        problems.append("Mix upper- and lower-case letters.")
    if not any(ch.isdigit() for ch in password):
        problems.append("Include at least one number.")
    if email and email.split("@")[0].lower() in password.lower() and len(email.split("@")[0]) >= 3:
        problems.append("Don't include your email name in the password.")
    return problems
