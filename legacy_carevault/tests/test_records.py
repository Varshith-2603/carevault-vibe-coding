"""Unit tests for the record registry, validation, filters and exports."""
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st

from utils.data_loader import init_session_data, get_alerts, recent_activity, upcoming_appointments
from utils.exports import appointment_ics, printable_record, to_csv
from utils.filters import filter_by_date, filter_hospital_visits, filter_index, perform_global_search
from utils.records import (
    add_record, build_record_index, clean_values, delete_record, get_df, get_record,
    linked_records, possible_duplicate, update_record, validate,
)


class RecordTests(unittest.TestCase):
    def setUp(self):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        init_session_data()

    def _visit(self, **over):
        v = {"date": "2026-01-02", "hospital_name": "Test Hospital", "department": "ENT",
             "attending_physician": "Dr. Test", "reason_for_visit": "Check-up", "status": "Completed"}
        v.update(over)
        return v

    # --- identifiers -------------------------------------------------------
    def test_ids_never_collide_after_delete(self):
        first = add_record("visit", self._visit())
        delete_record("visit", first)
        second = add_record("visit", self._visit(reason_for_visit="Another"))
        self.assertNotEqual(first, second)
        self.assertEqual(get_df("visit")["visit_id"].is_unique, True)

    def test_vitals_get_ids(self):
        vit = get_df("vital")
        self.assertTrue(vit["vital_id"].ne("").all())
        self.assertTrue(vit["vital_id"].is_unique)

    # --- validation --------------------------------------------------------
    def test_required_fields(self):
        errors = validate("visit", {})
        for f in ("date", "hospital_name", "department", "attending_physician", "reason_for_visit"):
            self.assertIn(f, errors)

    def test_future_visit_date_rejected(self):
        errors = validate("visit", self._visit(date=date.today() + timedelta(days=3)))
        self.assertIn("date", errors)

    def test_prescription_end_before_start(self):
        errors = validate("prescription", {"medication": "X", "dosage": "1 mg", "frequency": "Once daily",
                                           "prescribing_doctor": "Dr. A", "start_date": date(2026, 5, 1),
                                           "end_date": date(2026, 4, 1)})
        self.assertIn("end_date", errors)

    def test_vitals_rules(self):
        self.assertIn("heart_rate", validate("vital", {"date": date(2026, 1, 1)}))
        self.assertIn("diastolic_bp", validate("vital", {"date": date(2026, 1, 1), "systolic_bp": 120}))
        self.assertIn("systolic_bp", validate("vital", {"date": date(2026, 1, 1), "systolic_bp": 70, "diastolic_bp": 90}))
        self.assertEqual(validate("vital", {"date": date(2026, 1, 1), "weight_kg": 70.5}), {})

    def test_missing_optional_values_stay_missing(self):
        """No fabricated defaults: blank optional fields are stored blank."""
        rid = add_record("prescription", clean_values("prescription", {
            "medication": "Testmed", "dosage": "5 mg", "frequency": "Once daily",
            "prescribing_doctor": "Dr. A", "start_date": date(2026, 1, 1), "end_date": None,
            "instructions": "", "refills_remaining": None}))
        rec = get_record("prescription", rid)
        self.assertEqual(rec["end_date"], "")
        self.assertEqual(rec["instructions"], "")

    def test_duplicate_detection(self):
        add_record("visit", self._visit())
        self.assertIsNotNone(possible_duplicate("visit", self._visit()))
        self.assertIsNone(possible_duplicate("visit", self._visit(reason_for_visit="Different")))

    # --- update / delete / links ------------------------------------------
    def test_update_record(self):
        update_record("prescription", "RX-2026-081", {"refills_remaining": 7, "status": "On Hold"})
        rec = get_record("prescription", "RX-2026-081")
        self.assertEqual(int(rec["refills_remaining"]), 7)
        self.assertEqual(rec["status"], "On Hold")

    def test_delete_visit_unlinks_but_keeps_related(self):
        vid = get_df("visit").iloc[0]["visit_id"]
        update_record("diagnostic", "DG-2026-018", {"visit_id": vid})
        self.assertEqual(len(linked_records(vid)), 1)
        delete_record("visit", vid)
        rec = get_record("diagnostic", "DG-2026-018")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["visit_id"], "")

    # --- search & filters --------------------------------------------------
    def test_search_is_literal_and_tokenised(self):
        v = get_df("visit")
        res = perform_global_search("Mitchell cardiac", v, get_df("diagnostic"), get_df("prescription"), get_df("history"))
        self.assertGreater(len(res["visits"]), 0)
        # regex metacharacters are matched literally instead of raising
        res = perform_global_search("(essential", v, get_df("diagnostic"), get_df("prescription"), get_df("history"))
        self.assertGreater(len(res["visits"]), 0)
        res = perform_global_search("[*+?", v, get_df("diagnostic"), get_df("prescription"), get_df("history"))
        self.assertEqual(sum(len(x) for x in res.values()), 0)

    def test_search_by_formatted_date(self):
        idx = build_record_index()
        self.assertGreater(len(filter_index(idx, "Oct 2026")), 0)

    def test_date_range_filter(self):
        v = get_df("visit")
        out = filter_by_date(v, "date", date(2026, 1, 1), date(2026, 12, 31))
        self.assertTrue(out["date"].str.startswith("2026").all())
        self.assertGreater(len(out), 0)

    def test_combined_visit_filters(self):
        out = filter_hospital_visits(get_df("visit"), department="Cardiology", doctor="Dr. Sarah Mitchell",
                                     start=date(2026, 1, 1))
        self.assertTrue((out["department"] == "Cardiology").all())
        self.assertTrue(out["date"].ge("2026-01-01").all())

    # --- derived views -----------------------------------------------------
    def test_upcoming_excludes_past_dates(self):
        today = date.today()
        for d in upcoming_appointments()["date"]:
            self.assertGreaterEqual(d, today.isoformat())

    def test_activity_has_no_future_or_vitals(self):
        act = recent_activity(20)
        self.assertFalse((act["kind"] == "vital").any())
        self.assertTrue(act["date"].le(date.today().isoformat()).all())

    def test_alerts_come_from_data_and_can_be_dismissed(self):
        alerts = get_alerts()
        self.assertTrue(alerts)
        st.session_state.dismissed_alerts = {a["id"] for a in alerts}
        self.assertFalse(any(a["unread"] for a in get_alerts()))

    # --- exports -----------------------------------------------------------
    def test_exports(self):
        ics = appointment_ics(get_record("appointment", "APT-2026-008")).decode()
        self.assertIn("BEGIN:VEVENT", ics)
        self.assertIn("DTSTART:20261024T103000", ics)
        csv = to_csv(get_df("visit"), {"date": "Date", "hospital_name": "Hospital"}).decode("utf-8-sig")
        self.assertTrue(csv.startswith("Date,Hospital"))
        html_doc = printable_record("diagnostic", get_record("diagnostic", "DG-2026-018"), st.session_state.patient_info)
        self.assertIn(b"demo", html_doc.lower())


if __name__ == "__main__":
    unittest.main()
