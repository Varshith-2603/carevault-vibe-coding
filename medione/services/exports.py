"""Full data export (right to access / portability): JSON plus original files in a ZIP."""
from __future__ import annotations

import io
import json
import zipfile
from datetime import date

from medione import APP_NAME, audit
from medione.db import connect
from medione.services.documents import read_document_unchecked


def export_all(user_id: int) -> bytes:
    with connect() as conn:
        user = dict(conn.execute("SELECT id, email, display_name, created_at, ai_consent_at FROM users WHERE id = ?",
                                 (user_id,)).fetchone())
        profiles = [dict(r) for r in conn.execute("SELECT * FROM profiles WHERE user_id = ?", (user_id,))]
        pids = [p["id"] for p in profiles] or [-1]
        marks = ", ".join("?" * len(pids))

        def rows(sql: str, params) -> list[dict]:
            return [dict(r) for r in conn.execute(sql, params)]

        data = {
            "exported_by": APP_NAME, "exported_on": date.today().isoformat(), "account": user,
            "profiles": profiles,
            "doctors": rows("SELECT * FROM doctors WHERE user_id = ?", (user_id,)),
            "facilities": rows("SELECT * FROM facilities WHERE user_id = ?", (user_id,)),
            "records": rows(f"SELECT * FROM records WHERE profile_id IN ({marks})", pids),
            "medications": rows(f"SELECT * FROM medications WHERE profile_id IN ({marks})", pids),
            "lab_results": rows(f"SELECT * FROM lab_results WHERE profile_id IN ({marks})", pids),
            "reminders": rows(f"SELECT * FROM reminders WHERE profile_id IN ({marks})", pids),
            "share_links": rows("SELECT id, profile_id, label, record_ids_json, expires_at, revoked_at, created_at, "
                                "access_count FROM share_links WHERE user_id = ?", (user_id,)),
            "documents": rows(f"SELECT id, profile_id, record_id, filename, mime, size, sha256, uploaded_at, "
                              f"extracted_text, ai_summary FROM documents WHERE profile_id IN ({marks})", pids),
        }
        storage = rows(f"SELECT id, filename, storage_name FROM documents WHERE profile_id IN ({marks})", pids)
        audit.log("export.full", user_id, conn=conn)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("thought-medione-data.json", json.dumps(data, indent=2, default=str))
        for doc in storage:
            try:
                zf.writestr(f"documents/{doc['id']}-{doc['filename']}", read_document_unchecked(doc))
            except (OSError, ValueError):
                zf.writestr(f"documents/{doc['id']}-MISSING.txt", "This file could not be read from storage.")
    return buf.getvalue()
