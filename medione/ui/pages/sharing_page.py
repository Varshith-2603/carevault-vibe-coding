"""Create, monitor and revoke read-only links to selected records."""
from __future__ import annotations

import streamlit as st

from medione.services import search, sharing
from medione.ui.state import Ctx, flash
from medione.ui.widgets import badge, esc, fmt_date, md, page_header


def _revoke(uid: int, sid: int) -> None:
    sharing.revoke(uid, sid)
    flash("Link turned off. It stops working immediately.", "info")


def render(ctx: Ctx) -> None:
    page_header("Share with a doctor", "Send a read-only link to the records you choose. Nothing else is visible.")
    recs = search.search_records(ctx.uid, ctx.pid)
    if not recs:
        st.info("Add records before sharing.")
        return
    new = st.session_state.pop("share_new_link", None)
    if new:
        with st.container(border=True):
            st.success("Link created. Copy it now — for your security it won't be shown again.")
            st.code(new, language=None)
            st.caption("Anyone who has this link can view the selected records until it expires or you turn it off. "
                       "Send it only to the intended person.")

    with st.expander("Create a new link", expanded=not new, icon=":material/link:"):
        options = {r["id"]: f"{fmt_date(r['record_date'], 'No date')} · {r['title']}" for r in recs}
        with st.form("share_form"):
            chosen = st.multiselect("Records to share *", list(options), format_func=options.get,
                                    placeholder="Choose one or more records")
            label = st.text_input("Who is it for? *", placeholder="e.g. Dr. Kabir Menon – review visit", max_chars=120)
            c1, c2 = st.columns(2)
            expiry = c1.selectbox("Link works for", list(sharing.EXPIRY_CHOICES), index=2)
            files = c2.checkbox("Include the original files", value=True)
            summary = c2.checkbox("Include a one-page summary of the selected records", value=True)
            consent = st.checkbox(f"I agree to share these records of {ctx.profile['full_name']} with this person.")
            submitted = st.form_submit_button("Create link", type="primary")
        if submitted:
            if not consent:
                st.error("Please confirm that you want to share these records.")
            else:
                try:
                    _, token = sharing.create_share(ctx.uid, ctx.pid, chosen, label, sharing.EXPIRY_CHOICES[expiry],
                                                    include_summary=summary, include_files=files)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.session_state["share_new_link"] = sharing.share_url(token)
                    st.rerun()

    st.markdown("#### Your links")
    links = sharing.list_shares(ctx.uid, ctx.pid)
    if not links:
        st.caption("No links yet. Sharing is off until you create one.")
    titles = {r["id"]: r["title"] for r in recs}
    for l in links:
        tone = {"active": "green", "expired": "gray", "revoked": "red"}[l["state"]]
        with st.container(border=True):
            c1, c2 = st.columns([5, 1], vertical_alignment="center")
            with c1:
                md(f"<b>{esc(l['label'])}</b> {badge(l['state'].title(), tone)}<br>"
                   f"<span class='tm-row-meta'>{len(l['record_ids'])} record(s) · created {esc(fmt_date(l['created_at']))} · "
                   f"{'expires' if l['state'] == 'active' else 'expired'} {esc(fmt_date(l['expires_at']))} {esc(l['expires_at'][11:16])} UTC · "
                   f"opened {l['access_count']} time(s){(' · last ' + esc(fmt_date(l['last_access_at']))) if l['last_access_at'] else ''}"
                   f"{' · files included' if l['include_files'] else ''}</span>")
                st.caption("Shared: " + "; ".join(titles.get(i, "(deleted record)") for i in l["record_ids"]))
            with c2:
                if l["state"] == "active":
                    st.button("Turn off", key=f"share_rev_{l['id']}", on_click=_revoke, args=(ctx.uid, l["id"]))
            with st.expander("Access history"):
                log = sharing.access_log(ctx.uid, l["id"])
                if not log:
                    st.caption("Not opened yet.")
                for e in log:
                    st.caption(f"{e['at'][:16].replace('T', ' ')} UTC — {e['action'].replace('share.', '').replace('_', ' ')}")
