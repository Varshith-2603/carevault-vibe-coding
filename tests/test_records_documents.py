from datetime import date

import pytest

from medione import config
from medione.services import documents, records, search
from tests.conftest import pdf_bytes


def test_validation_messages(make_user):
    uid, pid, *_ = make_user()
    with pytest.raises(ValueError, match="record type"):
        records.save_record(uid, pid, {"type": "nope", "title": "x"})
    with pytest.raises(ValueError, match="title"):
        records.save_record(uid, pid, {"type": "other", "title": "  "})
    with pytest.raises(ValueError, match="before"):
        records.save_record(uid, pid, {"type": "admission", "title": "x", "record_date": "2026-02-02",
                                       "end_date": "2026-02-01"})
    with pytest.raises(ValueError, match="valid date"):
        records.save_record(uid, pid, {"type": "other", "title": "x", "record_date": "31/31/2026"})
    with pytest.raises(ValueError, match="source"):
        records.save_record(uid, pid, {"type": "other", "title": "x", "source": "clinician_verified"})


def test_medicines_and_results_round_trip(make_user):
    uid, pid, *_ = make_user()
    rid = records.save_record(
        uid, pid, {"type": "prescription", "title": "Rx", "record_date": date(2026, 3, 1), "source": "ai_extracted"},
        medications=[{"name": "Metformin", "dosage": "500 mg", "frequency": "Once daily", "uncertain": True,
                      "uncertain_note": "dose unclear"}, {"name": ""}])
    rec = records.get_record(uid, rid)
    assert [m["name"] for m in rec["medications"]] == ["Metformin"]  # blank row dropped
    assert rec["medications"][0]["start_date"] == "2026-03-01"
    assert rec["medications"][0]["frequency"] == "Once daily"  # stored exactly as written
    records.mark_reviewed(uid, rid)
    rec = records.get_record(uid, rid)
    assert rec["source"] == "patient_confirmed" and rec["medications"][0]["uncertain"] == 0
    # editing without passing medications keeps them
    records.save_record(uid, pid, {"type": "prescription", "title": "Rx edited", "source": rec["source"]}, record_id=rid)
    assert len(records.get_record(uid, rid)["medications"]) == 1


def test_lab_value_parsing(make_user):
    uid, pid, *_ = make_user()
    rid = records.save_record(uid, pid, {"type": "lab_report", "title": "Labs"}, lab_results=[
        {"test_name": "Platelets", "value_text": "2,50,000", "unit": "/uL"},
        {"test_name": "Urine sugar", "value_text": "Nil"}])
    labs = {l["test_name"]: l for l in records.get_record(uid, rid)["lab_results"]}
    assert labs["Platelets"]["value_num"] == 250000
    assert labs["Urine sugar"]["value_num"] is None and labs["Urine sugar"]["value_text"] == "Nil"


def test_upload_checks_real_file_type_and_size(make_user):
    uid, pid, *_ = make_user()
    with pytest.raises(documents.UploadRejected):
        documents.store_document(uid, pid, "evil.pdf", b"MZ\x90\x00 not a pdf")
    with pytest.raises(documents.UploadRejected):
        documents.store_document(uid, pid, "empty.pdf", b"")
    big = b"%PDF-1.4\n" + b"0" * (config.settings.max_upload_mb * 1024 * 1024 + 1)
    with pytest.raises(documents.UploadRejected, match="larger"):
        documents.store_document(uid, pid, "big.pdf", big)


def test_documents_encrypted_at_rest_and_deduplicated(make_user):
    uid, pid, *_ = make_user()
    data = pdf_bytes("HbA1c 5.9 %")
    doc_id = documents.store_document(uid, pid, "../../etc/passwd.pdf", data)
    row, plain = documents.read_document(uid, doc_id)
    assert plain == data
    assert row["filename"] == "passwd.pdf"
    on_disk = (config.settings.documents_dir / row["storage_name"]).read_bytes()
    assert b"%PDF" not in on_disk and b"HbA1c" not in on_disk
    assert "HbA1c" in (documents.get_extracted_text(uid, doc_id) or "")
    with pytest.raises(documents.DuplicateDocument):
        documents.store_document(uid, pid, "again.pdf", data)
    documents.store_document(uid, pid, "again.pdf", data, allow_duplicate=True)


def test_delete_record_keeps_files_unless_asked(make_user):
    uid, pid, *_ = make_user()
    rid = records.save_record(uid, pid, {"type": "other", "title": "x"})
    doc = documents.store_document(uid, pid, "a.pdf", pdf_bytes(), record_id=rid)
    records.delete_record(uid, rid)
    assert [d["id"] for d in documents.list_documents(uid, pid, unattached_only=True)] == [doc]
    rid2 = records.save_record(uid, pid, {"type": "other", "title": "y"})
    doc2 = documents.store_document(uid, pid, "b.pdf", pdf_bytes(), record_id=rid2)
    row, _ = documents.read_document(uid, doc2)
    records.delete_record(uid, rid2, delete_files=True)
    assert not (config.settings.documents_dir / row["storage_name"]).exists()


def test_search_filters_and_timeline(make_user):
    uid, pid, *_ = make_user()
    a = records.save_record(uid, pid, {"type": "lab_report", "title": "Blood test", "record_date": "2025-05-01",
                                       "follow_up_date": "2025-08-01"},
                            lab_results=[{"test_name": "TSH", "value_text": "2.1"}])
    records.save_record(uid, pid, {"type": "prescription", "title": "Rx", "record_date": "2026-01-10",
                                   "condition": "Hypothyroidism"}, medications=[{"name": "Levothyroxine"}])
    assert [r["id"] for r in search.search_records(uid, pid, "tsh")] == [a]
    assert len(search.search_records(uid, pid, "levothyroxine rx")) == 1
    assert search.search_records(uid, pid, "levothyroxine tsh") == []  # every word must match
    assert len(search.search_records(uid, pid, "may 2025")) == 1
    assert len(search.search_records(uid, pid, date_from=date(2026, 1, 1))) == 1
    assert len(search.search_records(uid, pid, medication="levo")) == 1
    assert len(search.search_records(uid, pid, test="tsh")) == 1
    assert len(search.search_records(uid, pid, condition="hypothyroid")) == 1
    events = search.timeline(uid, pid)
    assert [e["date"] for e in events] == ["2026-01-10", "2025-08-01", "2025-05-01"]
    assert events[1]["is_follow_up"]


def test_duplicates_flagged_not_deleted(make_user):
    uid, pid, *_ = make_user()
    a = records.save_record(uid, pid, {"type": "imaging", "title": "Ultrasound abdomen", "record_date": "2026-01-01"})
    b = records.save_record(uid, pid, {"type": "imaging", "title": "Abdomen ultrasound", "record_date": "2026-01-01"})
    records.save_record(uid, pid, {"type": "imaging", "title": "Chest X-ray", "record_date": "2026-01-01"})
    pairs = search.possible_duplicates(uid, pid)
    assert [(x["id"], y["id"]) for x, y in pairs] == [(a, b)]
    search.dismiss_duplicate(uid, pid, b, a)
    assert search.possible_duplicates(uid, pid) == []
    assert len(search.search_records(uid, pid)) == 3


def test_lab_trends_only_compare_same_units():
    rows = [
        {"test_name": "Glucose", "value_num": 104, "unit": "mg/dL", "record_date": "2025-01-01", "ref_high": 99},
        {"test_name": "glucose", "value_num": 5.5, "unit": "mmol/L", "record_date": "2025-06-01"},
        {"test_name": "HbA1c", "value_num": 5.9, "unit": "%", "record_date": "2025-01-01"},
        {"test_name": "HbA1c", "value_num": 5.6, "unit": "%", "record_date": "2025-06-01"},
    ]
    trends = {t["test_name"]: t for t in search.lab_trends(rows)}
    assert not trends["Glucose"]["comparable"] and "different units" in trends["Glucose"]["reason"]
    assert trends["HbA1c"]["comparable"]
    assert trends["Glucose"]["results"][0]["outside_report_range"] == "above"
