import streamlit as st

from components.header import render_top_header
from components.state import navigate, open_dialog
from components.ui import html_block, icon, section_header
from utils.helpers import render_disclaimer

GUIDE = [
    ("Find a record", "Type in the search box at the top of any page and press Enter. You'll see matching records "
                      "from every section on the All Records page.", ("All Records", None)),
    ("Add something new", "Press Add record at the top of any page. Choose what kind of record it is, fill in what "
                          "you know, and press Save record. Only fields marked * are required.", (None, "add")),
    ("Look at a report", "Open Scans & Diagnostics and press View report on any card. Reports that aren't final are "
                         "clearly marked.", ("Scans & Diagnostics", None)),
    ("Check your medicines", "Prescriptions & Medicines shows active prescriptions first. Switch to Medication "
                             "history for past medicines.", ("Prescriptions & Medicines", None)),
    ("Change or remove a record", "Open the record and press Edit or Delete. Deleting always asks you to confirm.", (None, None)),
    ("Share with a doctor", "On All Records, download a printable health summary or a CSV of your search results.",
     ("All Records", None)),
]

FAQ = [
    ("Is this my real medical record?",
     "No. CareVault is a demo. Every patient, doctor, hospital and result shown is fictional."),
    ("Where is my data stored?",
     "Only in memory for this browser session. Reloading the page resets everything, so please don't enter real "
     "medical information."),
    ("Does CareVault contact my pharmacy or clinic?",
     "No. Actions such as 'Log a refill collected' or 'Cancel appointment' only update your own records. Contact "
     "your pharmacy or clinic directly."),
    ("Can CareVault tell me what my results mean?",
     "No. It shows results exactly as recorded and doesn't interpret them. Ask a qualified healthcare professional."),
    ("How do I link a report to a hospital visit?",
     "Open the report, press Edit, and choose the visit under 'Related hospital visit'. The link then appears on both records."),
    ("What does 'Not recorded' mean?",
     "That piece of information wasn't entered. It doesn't mean a result was normal or negative."),
]


def render_help_support_page():
    render_top_header(
        title="Help & Support",
        subtitle="How to use CareVault, and where to get urgent help.",
    )
    html_block(
        f"""
        <div class="cv-emergency-banner" role="note">
            <div class="cv-emergency-banner-title">{icon('alert', 20)}<span>In a medical emergency, call your local emergency number now</span></div>
            <p>Don't use this app in an emergency. Common numbers: <strong>112</strong> (India and most of Europe),
            <strong>108</strong> (ambulance in many Indian states), <strong>911</strong> (US and Canada).
            For poisoning in the US, call Poison Help at <strong>1-800-222-1222</strong>.</p>
        </div>
        """
    )

    col1, col2 = st.columns([6, 5], gap="large")
    with col1:
        section_header("Quick guide", "The most common tasks, step by step.")
        for i, (title, text, target) in enumerate(GUIDE):
            with st.container(border=True, key=f"cvguide_{i}"):
                c1, c2 = st.columns([4, 1.4], vertical_alignment="center")
                with c1:
                    st.markdown(f"**{i + 1}. {title}**")
                    st.caption(text)
                with c2:
                    page, action = target
                    if action == "add":
                        st.button("Add record", key=f"guide_btn_{i}", on_click=open_dialog, args=("visit", None, "add"),
                                  width="stretch", icon=":material/add:")
                    elif page:
                        st.button("Go there", key=f"guide_btn_{i}", on_click=navigate, args=(page,), width="stretch",
                                  icon=":material/arrow_forward:", icon_position="right")
    with col2:
        section_header("Common questions")
        for q, a in FAQ:
            with st.expander(q):
                st.write(a)
        section_header("Contact support")
        st.info("Support messaging isn't available in this demo, so there's no form to send. "
                "For questions about your health, contact your doctor or clinic.", icon=":material/info:")
    render_disclaimer()
