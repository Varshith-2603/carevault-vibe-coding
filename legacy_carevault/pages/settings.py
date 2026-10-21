import json
import re

import streamlit as st

from components.header import render_top_header
from components.state import flash
from components.ui import field_error, html_block, notice
from utils.data_loader import export_bundle, get_patient_info, reset_demo_data
from utils.helpers import display, is_missing, render_disclaimer

BLOOD_TYPES = ["Not provided", "O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"]
TABS = ["Profile & emergency", "Alerts", "Data & privacy"]
_TAB_FROM_PRESET = {"profile": TABS[0], "alerts": TABS[1], "data": TABS[2]}
PHONE_RE = re.compile(r"^[+()0-9\s\-]{6,20}$")


def _profile_tab(patient):
    errors = st.session_state.get("_cv_profile_errors", {})
    html_block('<p class="cv-form-hint">This information appears on your Emergency Medical ID. Leave a field blank if '
               'you prefer not to provide it — it will show as <em>Not provided</em>.</p>')
    with st.form("profile_form", border=False, enter_to_submit=False):
        html_block('<div class="cv-form-section">About you</div>')
        c1, c2 = st.columns(2, gap="medium")
        with c1:
            name = st.text_input("Full name *", value=display(patient.get("name"), ""), key="set_name", max_chars=80)
            if "name" in errors:
                field_error(errors["name"])
            age = st.number_input("Age (years)", value=None if is_missing(patient.get("age")) else int(patient["age"]),
                                  min_value=0, max_value=120, step=1, key="set_age", placeholder="Not provided")
            st.text_input("Patient ID", value=display(patient.get("patient_id"), ""), disabled=True,
                          help="Assigned by CareVault. It can't be changed.")
        with c2:
            gender = st.text_input("Gender", value=display(patient.get("gender"), ""), key="set_gender", max_chars=40)
            current_blood = display(patient.get("blood_type"), "Not provided")
            blood = st.selectbox("Blood type", BLOOD_TYPES,
                                 index=BLOOD_TYPES.index(current_blood) if current_blood in BLOOD_TYPES else 0,
                                 key="set_blood")

        html_block('<div class="cv-form-section">Emergency information</div>')
        c3, c4 = st.columns(2, gap="medium")
        with c3:
            allergies = st.text_input("Known allergies", value=display(patient.get("allergies"), ""), key="set_allergies",
                                      placeholder="e.g. Penicillin — leave blank if not provided",
                                      help="If you have no known allergies, type 'No known allergies'.")
            conditions = st.text_input("Medical conditions", value=display(patient.get("primary_condition"), ""),
                                       key="set_conditions", placeholder="Conditions responders should know about")
            donor_opts = ["Not provided", "Yes", "No"]
            donor_cur = display(patient.get("organ_donor"), "Not provided")
            donor = st.selectbox("Organ donor", donor_opts,
                                 index=donor_opts.index(donor_cur) if donor_cur in donor_opts else 0, key="set_donor")
        with c4:
            contact = st.text_input("Emergency contact", value=display(patient.get("emergency_contact"), ""),
                                    key="set_contact", placeholder="Name (relationship)")
            phone = st.text_input("Emergency contact phone", value=display(patient.get("emergency_phone"), ""),
                                  key="set_phone", placeholder="+91 98765 43210")
            if "phone" in errors:
                field_error(errors["phone"])

        html_block('<div class="cv-form-section">Insurance</div>')
        c5, c6 = st.columns(2, gap="medium")
        with c5:
            insurance = st.text_input("Insurance provider", value=display(patient.get("insurance_provider"), ""), key="set_ins_name")
        with c6:
            policy = st.text_input("Policy number", value=display(patient.get("policy_no"), ""), key="set_ins_num")

        saved = st.form_submit_button("Save profile", type="primary", icon=":material/save:", key="save_profile_btn")

    if saved:
        errs = {}
        if not name.strip():
            errs["name"] = "Please enter your name."
        if phone.strip() and not PHONE_RE.match(phone.strip()):
            errs["phone"] = "Use digits, spaces, +, - or brackets only (6–20 characters)."
        st.session_state["_cv_profile_errors"] = errs
        if not errs:
            st.session_state.patient_info.update({
                "name": name.strip(), "age": age, "gender": gender.strip(),
                "blood_type": "" if blood == "Not provided" else blood,
                "allergies": allergies.strip(), "primary_condition": conditions.strip(),
                "organ_donor": "" if donor == "Not provided" else donor,
                "emergency_contact": contact.strip(), "emergency_phone": phone.strip(),
                "insurance_provider": insurance.strip(), "policy_no": policy.strip(),
            })
            flash("Profile saved.")
        st.rerun()


def _alerts_tab():
    prefs = st.session_state.alert_prefs
    html_block('<p class="cv-form-hint">Alerts appear under the <strong>Alerts</strong> button at the top of every page. '
               'They are worked out from your records. CareVault does not send texts or emails.</p>')
    with st.form("alerts_form", border=False, enter_to_submit=False):
        apts = st.toggle("Upcoming appointments", value=prefs.get("appointments", True), key="pref_apts")
        days = st.slider("Show appointments this many days ahead", 1, 90, int(prefs.get("appointment_days", 30)),
                         key="pref_days")
        reports = st.toggle("Diagnostic reports that are not final yet", value=prefs.get("reports", True), key="pref_reports")
        refills = st.toggle("Active prescriptions with 1 refill or fewer", value=prefs.get("refills", True), key="pref_refills")
        if st.form_submit_button("Save alert settings", type="primary", icon=":material/save:"):
            st.session_state.alert_prefs = {"appointments": apts, "appointment_days": days, "reports": reports,
                                            "refills": refills}
            flash("Alert settings saved.")
            st.rerun()


def _data_tab(patient):
    st.markdown("**Download all your records**")
    st.caption("A JSON file with your profile and every visit, report, prescription, past medicine, appointment and "
               "vitals reading — including anything you added in this session. Report files you attached are not included.")
    st.download_button(
        "Download complete record (JSON)", data=json.dumps(export_bundle(), indent=2, default=str),
        file_name=f"CareVault_PHR_{display(patient.get('patient_id'), 'export')}.json", mime="application/json",
        type="primary", icon=":material/download:", on_click="ignore", key="export_json_btn",
    )
    st.caption("For a filtered CSV or a printable summary, go to **All Records**.")

    st.divider()
    st.markdown("**How your data is handled in this demo**")
    html_block(notice(
        "This is a demonstration app. Records are kept only in memory for your current browser session and are "
        "reset when you reload the page. There is no login, encryption or cloud storage, so don't enter real "
        "medical information.", "warning", "shield"))

    st.divider()
    st.markdown("**Reset demo data**")
    st.caption("Puts back the original demo records and profile. Everything you added, edited or deleted is lost.")
    confirm = st.checkbox("I understand my changes will be lost", key="reset_confirm")
    if st.button("Reset demo data", key="reset_demo_btn", disabled=not confirm, icon=":material/restart_alt:"):
        reset_demo_data()
        for key in [k for k in st.session_state.keys() if str(k).startswith(("set_", "pref_"))] + ["reset_confirm"]:
            st.session_state.pop(key, None)
        flash("Demo data has been reset.")
        st.rerun()


def render_settings_page():
    """Profile and emergency details, in-app alert settings, export and privacy."""
    render_top_header(
        title="Settings",
        subtitle="Your profile, emergency details, alerts and data.",
    )
    patient = get_patient_info()
    preset = st.session_state.pop("_cv_settings_tab", None)
    if preset in _TAB_FROM_PRESET:
        st.session_state["settings_tabs"] = _TAB_FROM_PRESET[preset]
    tab_profile, tab_alerts, tab_data = st.tabs(TABS, key="settings_tabs", on_change="rerun")
    with tab_profile:
        _profile_tab(patient)
    with tab_alerts:
        _alerts_tab()
    with tab_data:
        _data_tab(patient)
    render_disclaimer()
