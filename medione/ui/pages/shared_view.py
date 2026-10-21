"""What a recipient sees when opening a share link. No sign-in, read-only, selected records only."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from medione import APP_NAME
from medione.models import RECORD_TYPES, type_label
from medione.services import sharing, summary
from medione.ui.widgets import badge, esc, fmt_date, kv, md, source_badge


def render(token: str) -> None:
    md(f'<div class="tm-brand"><span class="dot">✚</span>{APP_NAME}</div>')
    try:
        view = sharing.open_share(token, log_visit=not st.session_state.get(f"_share_seen_{token[:8]}"))
    except sharing.ShareUnavailable as exc:
        st.error(str(exc))
        return
    st.session_state[f"_share_seen_{token[:8]}"] = True
    p = view["profile"]
    st.markdown(f"## Records shared by {p['full_name']}")
    st.info(f"Shared for: {view['label']}. Read-only. This link expires {fmt_date(view['expires_at'])} "
            f"{view['expires_at'][11:16]} UTC. Only the records the patient selected are shown.")
    kv([("Date of birth", fmt_date(p["date_of_birth"], "")), ("Sex", p["sex"]), ("Blood group", p["blood_group"])])
    st.caption("Information was entered by the patient or copied from their documents. Items marked "
               "'AI-extracted' may contain reading errors — the original files are the reference.")

    if view["include_summary"]:
        s = summary.build_summary(view["owner_user_id"], view["profile_id"], view["record_ids"])
        st.download_button("Download summary of these records (HTML)", summary.summary_html(s, view["label"]),
                           "shared-medical-summary.html", "text/html", key="sv_summary")

    for r in view["records"]:
        t = RECORD_TYPES.get(r["type"])
        with st.container(border=True):
            md(f"<b>{esc(r['title'])}</b> {badge(type_label(r['type']), 'gray')} {source_badge(r['source'])}")
            rows = [(t.date_label if t else "Date", fmt_date(r["record_date"], "")),
                    ("Doctor", r["doctor_name"]), ("Hospital / clinic / lab", r["facility_name"]),
                    ("Condition (as documented)", r["condition"])]
            for e in (t.extras if t else ()):
                rows.append((e.label, r["details"].get(e.name)))
            rows += [("Summary", r["summary"]), ("Follow-up date", fmt_date(r["follow_up_date"], ""))]
            kv([x for x in rows if x[1]])
            if r["medications"]:
                st.dataframe(pd.DataFrame([{"Medicine": m["name"], "Dose": m["dosage"], "How often": m["frequency"],
                                            "Duration": m["duration"], "Instructions": m["instructions"],
                                            "Status": m["status"], "Unclear in source": "Yes" if m["uncertain"] else ""}
                                           for m in r["medications"]]), hide_index=True, width="stretch")
            if r["lab_results"]:
                st.dataframe(pd.DataFrame([{"Test": l["test_name"], "Result": l["value_text"] or l["value_num"],
                                            "Unit": l["unit"], "Range on report": l["ref_text"] or _rng(l)}
                                           for l in r["lab_results"]]), hide_index=True, width="stretch")
            for d in r["documents"]:
                if st.button(f"Prepare {d['filename']}", key=f"sv_prep_{d['id']}"):
                    try:
                        row, data = sharing.shared_document(token, d["id"])
                    except sharing.ShareUnavailable as exc:
                        st.error(str(exc))
                    else:
                        st.download_button(f"Download {d['filename']}", data, d["filename"], row["mime"],
                                           key=f"sv_dl_{d['id']}")
    st.caption(f"{APP_NAME} is a personal health record app. It does not provide medical advice.")


def _rng(l: dict) -> str:
    lo, hi = l.get("ref_low"), l.get("ref_high")
    if lo is None and hi is None:
        return ""
    return f"{'' if lo is None else f'{lo:g}'} – {'' if hi is None else f'{hi:g}'}"
