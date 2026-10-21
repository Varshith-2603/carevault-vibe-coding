"""Point the app at a throw-away data folder and use fast password hashing for tests."""
import os
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp(prefix="medione-tests-")
os.environ["MEDIONE_DATA_DIR"] = _TMP
os.environ["MEDIONE_PBKDF2_ITERATIONS"] = "1000"
os.environ["MEDIONE_ENABLE_DEMO"] = "1"
os.environ.pop("MEDIONE_ENCRYPTION_KEY", None)
for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "MEDIONE_AI_ENABLED"):
    os.environ.pop(var, None)

from medione import config  # noqa: E402

config.reload_settings()


@pytest.fixture
def make_user():
    from medione import auth
    from medione.services import profiles

    def _make(name="Test User"):
        email = f"{uuid.uuid4().hex[:10]}@example.com"
        user, code = auth.register(email, name, "Correct-Horse-42", name)
        return user.id, profiles.self_profile_id(user.id), email, code
    return _make


def pdf_bytes(text="Sample") -> bytes:
    from medione.seed import make_pdf
    return make_pdf("Test document", [text, uuid.uuid4().hex])
