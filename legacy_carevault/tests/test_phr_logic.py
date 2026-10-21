import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import unittest
import pandas as pd
from unittest.mock import MagicMock
import streamlit as st

from utils.data_loader import (
    init_session_data,
    get_hospital_visits,
    get_diagnostics,
    get_prescriptions,
    get_medication_history,
    get_appointments,
    get_vitals,
    get_dashboard_metrics,
    add_hospital_visit,
    add_diagnostic_report,
    add_prescription,
    add_medication_history,
    refill_prescription,
    get_patient_info
)
from utils.filters import (
    filter_hospital_visits,
    filter_diagnostics,
    filter_prescriptions,
    perform_global_search
)
from utils.helpers import format_date, render_badge, get_badge_class

class TestPHRCoreLogic(unittest.TestCase):
    def setUp(self):
        # Reset session state for testing
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        init_session_data()

    def test_data_loader_counts(self):
        visits = get_hospital_visits()
        self.assertGreaterEqual(len(visits), 12, "Hospital visits should be >= 12")
        
        diagnostics = get_diagnostics()
        self.assertGreaterEqual(len(diagnostics), 15, "Diagnostics should be >= 15")
        
        prescriptions = get_prescriptions()
        self.assertGreaterEqual(len(prescriptions), 8, "Prescriptions should be >= 8")
        
        history = get_medication_history()
        self.assertGreaterEqual(len(history), 15, "Medication history should be >= 15")
        
        appointments = get_appointments()
        self.assertGreaterEqual(len(appointments), 8, "Appointments should be >= 8")
        
        vitals = get_vitals()
        self.assertGreaterEqual(len(vitals), 30, "Vitals should be >= 30")

    def test_dashboard_metrics(self):
        metrics = get_dashboard_metrics()
        self.assertIsNotNone(metrics["next_appointment"])
        self.assertIsNotNone(metrics["last_visit"])
        self.assertEqual(metrics["active_rx_count"], 8)
        self.assertEqual(metrics["total_records"], len(get_hospital_visits()) + len(get_diagnostics()) + len(get_prescriptions()))
        self.assertGreaterEqual(metrics["different_hospitals"], 5)
        self.assertEqual(metrics["total_reports"], 18)
        self.assertEqual(metrics["pending_reports"], 2)
        self.assertEqual(metrics["final_reports"], 16)

    def test_add_hospital_visit(self):
        initial_len = len(get_hospital_visits())
        new_visit = {
            "hospital_name": "Apollo Medical Center",
            "date": "2026-10-20",
            "department": "Cardiology",
            "attending_physician": "Dr. Sarah Mitchell",
            "reason_for_visit": "Test Post-Operative Check",
            "status": "Completed",
            "visit_type": "Outpatient",
            "diagnosis_code": "Z09",
            "summary": "Healing well.",
            "discharge_instructions": "Routine care."
        }
        add_hospital_visit(new_visit)
        visits = get_hospital_visits()
        self.assertEqual(len(visits), initial_len + 1)
        self.assertEqual(visits.iloc[0]["reason_for_visit"], "Test Post-Operative Check")

    def test_add_diagnostic_report(self):
        initial_len = len(get_diagnostics())
        new_diag = {
            "scan_type": "Routine Lipid Panel",
            "category": "Laboratory & Pathology",
            "date": "2026-10-21",
            "facility": "Apollo Medical Center",
            "ordering_doctor": "Dr. Sarah Mitchell",
            "status": "Final Report Ready",
            "summary": "All lipid values within normal limits.",
            "findings": "Cholesterol: 170 mg/dL",
            "impression": "Normal",
            "normal_range": "Normal",
            "accession_no": "ACC-TEST-1"
        }
        add_diagnostic_report(new_diag)
        self.assertEqual(len(get_diagnostics()), initial_len + 1)

    def test_refill_prescription(self):
        rx_df = get_prescriptions()
        first_rx_id = rx_df.iloc[0]["rx_id"]
        initial_refills = int(rx_df.iloc[0]["refills_remaining"])
        success = refill_prescription(first_rx_id)
        self.assertTrue(success)
        updated_refills = int(get_prescriptions().iloc[0]["refills_remaining"])
        self.assertEqual(updated_refills, initial_refills - 1)

    def test_filters(self):
        visits = get_hospital_visits()
        apollo_visits = filter_hospital_visits(visits, hospital="Apollo Medical Center")
        self.assertTrue(all(apollo_visits["hospital_name"] == "Apollo Medical Center"))
        
        cardio_visits = filter_hospital_visits(visits, department="Cardiology")
        self.assertTrue(all(cardio_visits["department"] == "Cardiology"))
        
        search_visits = filter_hospital_visits(visits, search_query="Mitchell")
        self.assertGreater(len(search_visits), 0)

    def test_global_search(self):
        v = get_hospital_visits()
        d = get_diagnostics()
        p = get_prescriptions()
        h = get_medication_history()
        
        res = perform_global_search("Mitchell", v, d, p, h)
        total_found = len(res["visits"]) + len(res["diagnostics"]) + len(res["prescriptions"]) + len(res["history"])
        self.assertGreater(total_found, 0)
        
        empty_res = perform_global_search("NonExistentTermXYZ123", v, d, p, h)
        total_empty = len(empty_res["visits"]) + len(empty_res["diagnostics"]) + len(empty_res["prescriptions"]) + len(empty_res["history"])
        self.assertEqual(total_empty, 0)

    def test_helpers(self):
        self.assertEqual(format_date("2026-10-24"), "24 Oct 2026")
        self.assertIn("badge-ready", render_badge("Final Report Ready"))
        self.assertIn("badge-processing", render_badge("Processing"))
        self.assertIn("badge-danger", render_badge("Allergy"))

if __name__ == "__main__":
    unittest.main()
