import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from streamlit.testing.v1 import AppTest

def test_all_pages_flow():
    print("Testing Dashboard page...")
    at = AppTest.from_file("../app.py", default_timeout=30).run()
    assert len(at.exception) == 0, f"Dashboard threw exception: {at.exception}"
    
    # Test Hospital Visits
    print("Testing Hospital Visits page...")
    at.session_state["current_page"] = "Hospital Visits"
    at.run()
    assert len(at.exception) == 0, f"Hospital Visits threw exception: {at.exception}"
    
    # Test Scans & Diagnostics
    print("Testing Scans & Diagnostics page...")
    at.session_state["current_page"] = "Scans & Diagnostics"
    at.run()
    assert len(at.exception) == 0, f"Scans & Diagnostics threw exception: {at.exception}"
    
    # Test Prescriptions & Medicines
    print("Testing Prescriptions & Medicines page...")
    at.session_state["current_page"] = "Prescriptions & Medicines"
    at.run()
    assert len(at.exception) == 0, f"Prescriptions threw exception: {at.exception}"
    
    # Test Settings
    print("Testing Settings page...")
    at.session_state["current_page"] = "Settings"
    at.run()
    assert len(at.exception) == 0, f"Settings threw exception: {at.exception}"
    
    # Test Help & Support
    print("Testing Help & Support page...")
    at.session_state["current_page"] = "Help & Support"
    at.run()
    assert len(at.exception) == 0, f"Help & Support threw exception: {at.exception}"
    
    # Test Global Search on Dashboard
    print("Testing Global Search...")
    at.session_state["current_page"] = "Dashboard"
    at.session_state["global_search_query"] = "Apollo"
    at.run()
    assert len(at.exception) == 0, f"Search threw exception: {at.exception}"
    
    print("ALL APP PAGES AND FLOWS TESTED SUCCESSFULLY WITH 0 EXCEPTIONS!")

if __name__ == "__main__":
    test_all_pages_flow()
