"""Family profiles: separate records for people the account holder looks after."""
from __future__ import annotations

from datetime import date

import streamlit as st

from medione.models import BLOOD_GROUPS, RELATIONSHIPS, SEXES
from medione.services import profiles, records
from medione.ui.record_form import to_date
from medione.ui.state import Ctx, flash, switch_profile
from medione.ui.widgets import badge, esc, fmt_date, md, page_header

CONSENT = ("I am authorised to manage this person's health records — I am their parent or legal guardian, "
           "or they have given me permission.")


def profile_fields(prefix: str, p: dict, allow_relationship: bool) -> dict:
    c1, c2 = st.columns(2)
    out = {"full_name": c1.text_input("Full name *", value=p.get("full_name") or "", key=f"{prefix}_name")}
    if allow_relationship:
        rels = [r for r in RELATIONSHIPS if r != "self"]
        cur = p.get("relationship") if p.get("relationship") in rels else rels[0]
        out["relationship"] = c2.selectbox("Relationship to you", rels, index=rels.index(cur), key=f"{prefix}_rel")
    out["date_of_birth"] = c1.date_input("Date of birth", value=to_date(p.get("date_of_birth")), key=f"{prefix}_dob",
                                         min_value=date(1900, 1, 1), max_value=date.today(), format="DD/MM/YYYY")
    sexes = list(SEXES)
    out["sex"] = c2.selectbox("Sex", sexes, index=sexes.index(p["sex"]) if p.get("sex") in sexes else None,
                              key=f"{prefix}_sex", placeholder="Choose…")
    bgs = list(BLOOD_GROUPS)
    out["blood_group"] = c1.selectbox("Blood group", bgs, index=bgs.index(p["blood_group"]) if p.get("blood_group") in bgs else None,
                                      key=f"{prefix}_bg", placeholder="Choose…")
    out["phone"] = c2.text_input("Phone", value=p.get("phone") or "", key=f"{prefix}_phone")
    out["emergency_contact_name"] = c1.text_input("Emergency contact", value=p.get("emergency_contact_name") or "",
                                                  key=f"{prefix}_ecn")
    out["emergency_contact_phone"] = c2.text_input("Emergency contact phone", value=p.get("emergency_contact_phone") or "",
                                                   key=f"{prefix}_ecp")
    if out["date_of_birth"]:
        out["date_of_birth"] = out["date_of_birth"].isoformat()
    return out


def render(ctx: Ctx) -> None:
    page_header("Family profiles", "Each person has their own separate records, reminders and share links.")
    for p in ctx.profiles:
        counts = records.profile_counts(ctx.uid, p["id"])
        active = p["id"] == ctx.pid
        with st.container(border=True):
            c1, c2 = st.columns([4, 1], vertical_alignment="center")
            with c1:
                md(f"<b>{esc(p['full_name'])}</b> {badge('You' if p['relationship'] == 'self' else p['relationship'], 'blue')}"
                   f"{' ' + badge('Selected', 'green') if active else ''}<br><span class='tm-row-meta'>"
                   f"{counts['total']} records · born {esc(fmt_date(p['date_of_birth']))}"
                   f"{(' · added ' + esc(fmt_date(p['consent_at']))) if p['relationship'] != 'self' else ''}</span>")
            if not active:
                c2.button("Switch to", key=f"fam_sw_{p['id']}", on_click=switch_profile, args=(p["id"],))
            with st.expander("Edit details"):
                with st.form(f"fam_edit_{p['id']}"):
                    vals = profile_fields(f"fam_e{p['id']}", p, p["relationship"] != "self")
                    if st.form_submit_button("Save", type="primary"):
                        try:
                            profiles.update_profile(ctx.uid, p["id"], vals)
                        except ValueError as exc:
                            st.error(str(exc))
                        else:
                            flash("Profile updated.")
                            st.rerun()
                if p["relationship"] != "self":
                    st.markdown("**Remove this profile**")
                    st.caption("Permanently deletes all of this person's records, files, reminders and share links.")
                    typed = st.text_input(f"Type “{p['full_name']}” to confirm", key=f"fam_del_txt_{p['id']}")
                    if st.button("Delete profile and all its records", key=f"fam_del_{p['id']}",
                                 disabled=typed.strip() != p["full_name"]):
                        profiles.delete_profile(ctx.uid, p["id"])
                        if active:
                            switch_profile(profiles.self_profile_id(ctx.uid))
                        flash("Profile deleted.", "info")
                        st.rerun()

    with st.expander("Add a family member", icon=":material/person_add:"):
        with st.form("fam_new", clear_on_submit=True):
            vals = profile_fields("fam_new", {}, True)
            consent = st.checkbox(CONSENT, key="fam_new_consent")
            if st.form_submit_button("Add profile", type="primary"):
                try:
                    pid = profiles.create_profile(ctx.uid, vals, CONSENT if consent else "")
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    switch_profile(pid)
                    flash(f"Added {vals['full_name']}. You're now viewing their profile.")
                    st.rerun()
    st.caption("Adult family members should normally keep their own account. Add someone here only if you look "
               "after their care and have their permission.")
