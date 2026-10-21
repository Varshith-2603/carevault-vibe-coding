"""Sign in, create an account, recover access with a recovery code."""
from __future__ import annotations

import streamlit as st

from medione import APP_NAME, auth, config
from medione.ui.state import show_flash, sign_in
from medione.ui.widgets import md


def _show_new_recovery_code() -> bool:
    """After sign-up or reset: show the recovery code once. Returns True while it is displayed."""
    pending = st.session_state.get("pending_recovery")
    if not pending:
        return False
    code, user_id = pending
    with st.container(border=True):
        st.markdown("### Save your recovery code")
        st.write("This is the only way to get back into your account if you forget your password. "
                 "It won't be shown again. Store it somewhere safe (not in this app).")
        st.code(code, language=None)
        saved = st.checkbox("I have saved my recovery code", key="recovery_saved")
        if st.button("Continue", type="primary", disabled=not saved, key="recovery_continue"):
            user = auth.get_user(user_id)
            st.session_state.pop("pending_recovery", None)
            if user:
                sign_in(user)
            st.rerun()
    return True


def render() -> None:
    st.write("")
    hero, mid = st.columns([1.05, 1], gap="large")
    with hero:
        md(f"""<div class="tm-hero" style="flex-direction:column;min-height:520px;justify-content:space-between">
<div style="z-index:1"><div class="tm-brand" style="color:#fff"><span class="dot">✚</span>{APP_NAME}</div>
<h1 style="margin-top:1.6rem;font-size:2rem;line-height:1.2">Your family's medical records — organised, private and
ready when a doctor asks.</h1>
<div class="who" style="margin-top:.8rem">No more lost prescriptions, forgotten reports or repeated tests.</div></div>
<div style="z-index:1;display:grid;gap:.6rem;margin-top:1.4rem">
<div class="tm-chip"><b>One place</b>Prescriptions, lab reports, scans and discharge summaries for every family member</div>
<div class="tm-chip"><b>Stay on track</b>Appointments, medicine reminders, symptom diary and home readings</div>
<div class="tm-chip"><b>Safe sharing</b>Expiring links for doctors and a QR emergency card — you stay in control</div>
</div></div>""")
    with mid:
        st.markdown("### Welcome")
        st.caption("Sign in or create a free account.")
        show_flash()
        if _show_new_recovery_code():
            return
        tab_in, tab_up, tab_reset = st.tabs(["Sign in", "Create account", "Forgot password"])

        with tab_in:
            with st.form("login_form"):
                email = st.text_input("Email", key="login_email", autocomplete="email")
                password = st.text_input("Password", type="password", key="login_password",
                                         autocomplete="current-password")
                submitted = st.form_submit_button("Sign in", type="primary", width="stretch")
            if submitted:
                try:
                    user = auth.login(email, password)
                except auth.AuthError as exc:
                    st.error(str(exc))
                else:
                    sign_in(user)
                    st.rerun()
            if config.settings.enable_demo:
                st.divider()
                st.caption("Just looking around? Open a fictional sample account. Don't add real medical data to it.")
                if st.button("Explore with sample data", key="demo_login", width="stretch"):
                    from medione.seed import DEMO_EMAIL, DEMO_PASSWORD, seed_demo
                    with st.spinner("Preparing the sample account…"):
                        seed_demo()
                        user = auth.login(DEMO_EMAIL, DEMO_PASSWORD)
                    sign_in(user)
                    st.rerun()

        with tab_up:
            with st.form("register_form"):
                name = st.text_input("Your name", key="reg_name", max_chars=80)
                full_name = st.text_input("Full name for your medical profile", key="reg_full_name", max_chars=120,
                                          help="As it appears on your medical documents.")
                email = st.text_input("Email", key="reg_email", autocomplete="email")
                password = st.text_input("Password", type="password", key="reg_password", autocomplete="new-password",
                                         help="At least 10 characters with upper- and lower-case letters and a number.")
                confirm = st.text_input("Confirm password", type="password", key="reg_confirm")
                agree = st.checkbox(
                    "I understand that Thought Medione stores my health information to organise it for me, "
                    "that I can export or delete it at any time, and that it does not give medical advice.",
                    key="reg_agree")
                submitted = st.form_submit_button("Create account", type="primary", width="stretch")
            if submitted:
                if password != confirm:
                    st.error("The two passwords don't match.")
                elif not agree:
                    st.error("Please confirm you understand how your information is used.")
                else:
                    try:
                        user, code = auth.register(email, name, password, full_name)
                    except auth.AuthError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state["pending_recovery"] = (code, user.id)
                        st.rerun()

        with tab_reset:
            st.caption("Use the recovery code you saved when you created your account.")
            with st.form("reset_form"):
                email = st.text_input("Email", key="reset_email")
                code = st.text_input("Recovery code", key="reset_code", placeholder="XXXX-XXXX-XXXX-XXXX")
                new_pw = st.text_input("New password", type="password", key="reset_password")
                submitted = st.form_submit_button("Reset password", type="primary", width="stretch")
            if submitted:
                try:
                    fresh = auth.reset_with_recovery_code(email, code, new_pw)
                except auth.AuthError as exc:
                    st.error(str(exc))
                else:
                    user = auth.login(email, new_pw)
                    st.session_state["pending_recovery"] = (fresh, user.id)
                    st.rerun()
        st.write("")
        st.caption("Thought Medione does not give medical advice. In an emergency call 112 (India).")
