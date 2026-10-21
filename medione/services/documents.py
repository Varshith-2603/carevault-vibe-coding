"""Encrypted storage of original medical documents.

Files are checked by size, declared type *and* their leading bytes, encrypted
with the app key and saved under a random name. Originals are never modified;
extracted text and AI summaries are stored separately alongside them.
"""
from __future__ import annotations

import io
import re
import uuid
from typing import Optional

from medione import audit, config, security
from medione.db import connect, now_iso
from medione.models import ALLOWED_UPLOAD_TYPES
from medione.services.access import require_document, require_profile, require_record


class UploadRejected(ValueError):
    """The file can't be accepted (message is safe to show)."""


class DuplicateDocument(ValueError):
    def __init__(self, existing: dict):
        self.existing = existing
        super().__init__("This exact file has already been uploaded.")


_MAGIC = {
    "application/pdf": lambda b: b.startswith(b"%PDF-"),
    "image/png": lambda b: b.startswith(b"\x89PNG\r\n\x1a\n"),
    "image/jpeg": lambda b: b.startswith(b"\xff\xd8\xff"),
    "image/webp": lambda b: b[:4] == b"RIFF" and b[8:12] == b"WEBP",
}


def sniff_mime(data: bytes) -> Optional[str]:
    return next((mime for mime, check in _MAGIC.items() if check(data)), None)


def safe_filename(name: str) -> str:
    name = re.split(r"[\\/]", name or "document")[-1]
    name = re.sub(r"[^\w.\- ()]+", "_", name).strip(" .") or "document"
    return name[:120]


def extract_pdf_text(data: bytes, max_chars: int = 60_000) -> Optional[str]:
    """Text layer of a PDF, read locally (no external service). Scanned PDFs return None."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        parts = []
        for page in reader.pages[:50]:
            parts.append(page.extract_text() or "")
            if sum(map(len, parts)) > max_chars:
                break
        text = "\n".join(parts).strip()
        return text[:max_chars] or None
    except Exception:
        return None


def validate_upload(filename: str, data: bytes) -> str:
    """Return the verified MIME type or raise UploadRejected."""
    if not data:
        raise UploadRejected("The file is empty.")
    limit = config.settings.max_upload_mb
    if len(data) > limit * 1024 * 1024:
        raise UploadRejected(f"The file is larger than {limit} MB. Try a smaller scan or split the PDF.")
    mime = sniff_mime(data)
    if mime not in ALLOWED_UPLOAD_TYPES:
        raise UploadRejected("Only PDF, JPG, PNG and WEBP files are accepted, and the file must really be one of these.")
    return mime


def find_duplicate(user_id: int, profile_id: int, data: bytes) -> Optional[dict]:
    digest = security.sha256_bytes(data)
    with connect() as conn:
        require_profile(conn, user_id, profile_id)
        row = conn.execute("SELECT d.id, d.filename, d.record_id, d.uploaded_at, r.title AS record_title "
                           "FROM documents d LEFT JOIN records r ON r.id = d.record_id "
                           "WHERE d.profile_id = ? AND d.sha256 = ?", (profile_id, digest)).fetchone()
    return dict(row) if row else None


def store_document(user_id: int, profile_id: int, filename: str, data: bytes,
                   record_id: Optional[int] = None, allow_duplicate: bool = False) -> int:
    mime = validate_upload(filename, data)
    if not allow_duplicate:
        dup = find_duplicate(user_id, profile_id, data)
        if dup:
            raise DuplicateDocument(dup)
    storage_name = f"{uuid.uuid4().hex}.bin"
    folder = config.settings.documents_dir
    folder.mkdir(parents=True, exist_ok=True)
    (folder / storage_name).write_bytes(security.encrypt(data))
    text = extract_pdf_text(data) if mime == "application/pdf" else None
    try:
        with connect() as conn:
            require_profile(conn, user_id, profile_id)
            if record_id:
                rec = require_record(conn, user_id, record_id)
                if rec["profile_id"] != profile_id:
                    raise UploadRejected("That record belongs to another profile.")
            doc_id = conn.execute(
                "INSERT INTO documents (profile_id, record_id, filename, mime, size, sha256, storage_name, "
                "extracted_text, uploaded_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (profile_id, record_id, safe_filename(filename), mime, len(data), security.sha256_bytes(data),
                 storage_name, text, now_iso())).lastrowid
            audit.log("document.uploaded", user_id, profile_id, target=f"document:{doc_id}", conn=conn)
    except Exception:
        (folder / storage_name).unlink(missing_ok=True)
        raise
    return doc_id


def read_document(user_id: int, document_id: int, log_access: bool = True) -> tuple[dict, bytes]:
    with connect() as conn:
        row = dict(require_document(conn, user_id, document_id))
        if log_access:
            audit.log("document.opened", user_id, row["profile_id"], target=f"document:{document_id}", conn=conn)
    path = config.settings.documents_dir / row["storage_name"]
    if not path.exists():
        raise FileNotFoundError("The stored file is missing.")
    return row, security.decrypt(path.read_bytes())


def read_document_unchecked(row: dict) -> bytes:
    """Decrypt a document whose access was already authorised (used by share links)."""
    return security.decrypt((config.settings.documents_dir / row["storage_name"]).read_bytes())


def attach(user_id: int, document_id: int, record_id: Optional[int]) -> None:
    with connect() as conn:
        doc = require_document(conn, user_id, document_id)
        if record_id:
            rec = require_record(conn, user_id, record_id)
            if rec["profile_id"] != doc["profile_id"]:
                raise ValueError("The document and record belong to different profiles.")
        conn.execute("UPDATE documents SET record_id = ? WHERE id = ?", (record_id, document_id))
        audit.log("document.attached", user_id, doc["profile_id"], target=f"document:{document_id}",
                  detail=f"record:{record_id}", conn=conn)


def get_extracted_text(user_id: int, document_id: int) -> Optional[str]:
    with connect() as conn:
        return require_document(conn, user_id, document_id)["extracted_text"]


def set_extracted_text(user_id: int, document_id: int, text: Optional[str]) -> None:
    with connect() as conn:
        require_document(conn, user_id, document_id)
        conn.execute("UPDATE documents SET extracted_text = ? WHERE id = ?", (text, document_id))


def set_ai_summary(user_id: int, document_id: int, summary: str) -> None:
    with connect() as conn:
        doc = require_document(conn, user_id, document_id)
        conn.execute("UPDATE documents SET ai_summary = ?, ai_summary_at = ? WHERE id = ?",
                     (summary, now_iso(), document_id))
        audit.log("document.ai_summary", user_id, doc["profile_id"], target=f"document:{document_id}", conn=conn)


def list_documents(user_id: int, profile_id: int, unattached_only: bool = False) -> list[dict]:
    sql = ("SELECT d.id, d.filename, d.mime, d.size, d.uploaded_at, d.record_id, r.title AS record_title, "
           "r.type AS record_type FROM documents d LEFT JOIN records r ON r.id = d.record_id WHERE d.profile_id = ?")
    if unattached_only:
        sql += " AND d.record_id IS NULL"
    with connect() as conn:
        require_profile(conn, user_id, profile_id)
        return [dict(r) for r in conn.execute(sql + " ORDER BY d.uploaded_at DESC", (profile_id,))]


def delete_document(user_id: int, document_id: int) -> None:
    with connect() as conn:
        row = require_document(conn, user_id, document_id)
        conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        audit.log("document.deleted", user_id, row["profile_id"], target=f"document:{document_id}", conn=conn)
    (config.settings.documents_dir / row["storage_name"]).unlink(missing_ok=True)
