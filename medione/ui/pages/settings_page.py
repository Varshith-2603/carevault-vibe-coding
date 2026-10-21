"""Account security, AI consent, data export, activity log and account deletion."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from medione import audit, auth
from medione.ai.client import is_configured
from medione.services import documents, exports
from medione.ui.pages.assistant import consent_panel
from medione.ui.state import Ctx, flash, sign_out
from medione.ui.widgets import fmt_date, kv, page_header


def _withdraw(uid: int) -> None:
    auth.set_ai_consent(uid, False)
    flash("AI features turned off.", "info")


def render(ctx: Ctx) -> None:
    page_header("Settings", "Account, privacy and your data.")
    tab_acc, tab_ai, tab_data, tab_log, tab_del = st.tabs(
        ["Account & security", "AI features", "Your data", "Activity log", "Delete account"])

    with tab_acc:
        kv([("Name", ctx.user.display_name), ("Email", ctx.user.email)])
        st.markdown("#### Change password")
        with st.form("set_pw", clear_on_submit=True):
            cur = st.text_input("Current password", type="password")
            new = st.text_input("New password", type="password",
                                help="At least 10 characters with upper- and lower-case letters and a number.")
            again = st.text_input("Confirm new password", type="password")
            if st.form_submit_button("Change password", type="primary"):
                if new != again:
                    st.error("The new passwords don't match.")
                else:
                    try:
                        auth.change_password(ctx.uid, cur, new)
                    except auth.AuthError as exc:
                        st.error(str(exc))
                    else:
                        st.success("Password changed.")
        st.markdown("#### Recovery code")
        st.caption("Lost your recovery code? Create a new one. The old one stops working.")
        with st.form("set_rc", clear_on_submit=True):
            pw = st.text_input("Password", type="password")
            if st.form_submit_button("Create new recovery code"):
                try:
                    code = auth.regenerate_recovery_code(ctx.uid, pw)
                except auth.AuthError as exc:
                    st.error(str(exc))
                else:
                    st.success("Save this code somewhere safe. It won't be shown again.")
                    st.code(code, language=None)

    with tab_ai:
        if not is_configured():
            st.info("AI features aren't set up on this server.")
        elif ctx.user.ai_consent_at:
            st.success(f"AI features are on (since {fmt_date(ctx.user.ai_consent_at)}).")
            st.button("Turn off AI features", on_click=_withdraw, args=(ctx.uid,), key="set_ai_off")
        else:
            consent_panel(ctx, "set_ai")

    with tab_data:
        st.markdown("#### Download everything")
        st.caption("A ZIP with all profiles, records, medicines, results, reminders and your original files "
                   "(decrypted). Keep it somewhere safe.")
        if st.button("Prepare export", key="set_export"):
            with st.spinner("Preparing…"):
                st.session_state["set_export_zip"] = exports.export_all(ctx.uid)
        if st.session_state.get("set_export_zip"):
            st.download_button("Download ZIP", st.session_state["set_export_zip"], "thought-medione-export.zip",
                               "application/zip", key="set_export_dl")
        st.markdown("#### Files not attached to a record")
        loose = documents.list_documents(ctx.uid, ctx.pid, unattached_only=True)
        if not loose:
            st.caption("None.")
        for d in loose:
            c1, c2 = st.columns([4, 1])
            c1.write(f"📎 {d['filename']} · uploaded {fmt_date(d['uploaded_at'])}")
            if c2.checkbox("Delete", key=f"set_loose_ok_{d['id']}"):
                if c2.button("Confirm", key=f"set_loose_del_{d['id']}"):
                    documents.delete_document(ctx.uid, d["id"])
                    flash("File deleted.", "info")
                    st.rerun()

    with tab_log:
        st.caption("Security-relevant activity on your account (sign-ins, changes, shares, downloads). "
                   "No medical details are stored in this log.")
        log = audit.recent(ctx.uid)
        if log:
            st.dataframe(pd.DataFrame([{"When (UTC)": e["at"][:19].replace("T", " "), "Action": e["action"],
                                        "Item": e["target"], "Detail": e["detail"]} for e in log]),
                         hide_index=True, width="stretch")

    with tab_del:
        st.error("Deleting your account permanently removes every profile, record, file, reminder and share link. "
                 "Download an export first if you want a copy.")
        with st.form("set_delete"):
            pw = st.text_input("Password", type="password")
            typed = st.text_input("Type DELETE to confirm")
            if st.form_submit_button("Delete my account permanently"):
                if typed.strip() != "DELETE":
                    st.error("Type DELETE in capitals to confirm.")
                else:
                    try:
                        auth.delete_account(ctx.uid, pw)
                    except auth.AuthError as exc:
                        st.error(str(exc))
                    else:
                        sign_out("Your account and all its data have been deleted.")
                        st.rerun()
