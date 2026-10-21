"""A single record: details, medicines, results, original files, review, edit and delete."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from medione.ai import tasks as ai_tasks
from medione.ai.client import AIError, AIUnavailable, is_configured
from medione.models import RECORD_TYPES, UPLOAD_EXTENSIONS, type_label
from medione.services import documents, records, reminders, schedule
from medione.services.access import AccessDenied
from medione.ui.record_form import record_form, resolve_people
from medione.ui.state import Ctx, flash, go
from medione.ui.widgets import ai_block, badge, disclaimer, esc, fmt_date, kv, md, source_badge


def _back() -> None:
    go(st.session_state.get("back_to") or "Records")


def _reviewed(uid: int, rid: int) -> None:
    records.mark_reviewed(uid, rid)
    flash("Marked as reviewed by you.")


def _range(l: dict) -> str:
    if l.get("ref_text"):
        return l["ref_text"]
    lo, hi = l.get("ref_low"), l.get("ref_high")
    if lo is None and hi is None:
        return "Not printed"
    return f"{'' if lo is None else f'{lo:g}'} – {'' if hi is None else f'{hi:g}'}"


def _position(l: dict) -> str:
    v, lo, hi = l.get("value_num"), l.get("ref_low"), l.get("ref_high")
    if v is None or (lo is None and hi is None):
        return ""
    if hi is not None and v > hi:
        return "Above report range"
    if lo is not None and v < lo:
        return "Below report range"
    return "Within report range"


QUICK_QUESTIONS = ["Explain this report in simple English", "Summarise the findings written in this report",
                   "What do the abbreviations in this document mean?", "What questions could I ask my doctor about this?"]


def _ask_document(ctx: Ctx, d: dict) -> None:
    """Ask the AI about this one document; the answer keeps the document's words apart from general information."""
    with st.expander("Ask about this document", icon=":material/forum:"):
        pick = st.pills("Quick questions", QUICK_QUESTIONS, key=f"rec_qq_{d['id']}", label_visibility="collapsed")
        typed = st.text_input("…or type your own question", key=f"rec_q_{d['id']}",
                              placeholder="e.g. What does 'mild LVH' mean in this report?")
        question = typed.strip() or (pick or "")
        if st.button("Ask", key=f"rec_q_go_{d['id']}", disabled=not question.strip(), icon=":material/send:"):
            try:
                _, data = documents.read_document(ctx.uid, d["id"], log_access=False)
                with st.spinner("Reading the document…"):
                    st.session_state[f"rec_qa_{d['id']}"] = (question, ai_tasks.ask_document(data, d["mime"], question))
            except (AIError, AIUnavailable, FileNotFoundError, ValueError) as exc:
                st.error(str(exc))
        qa = st.session_state.get(f"rec_qa_{d['id']}")
        if qa:
            q, out = qa
            body = f"**You asked:** {q}\n\n**What this document says:** {out['answer_from_document']}"
            if out.get("general_information"):
                body += f"\n\n**General information (not from your document):** {out['general_information']}"
            if out.get("uncertain_parts"):
                body += f"\n\n_Unclear or unreadable: {out['uncertain_parts']}_"
            if out["questions_for_doctor"]:
                body += "\n\n**You could ask your doctor:**\n" + "\n".join(f"- {x}" for x in out["questions_for_doctor"])
            ai_block("answer about this document", body)


def _apply_plan(uid: int, rid: int) -> None:
    plan = schedule.apply_plan(uid, rid)
    msg = ("**Set up automatically:**\n" + "\n".join(f"- {c}" for c in plan.created)) if plan.created \
        else "Nothing new to set up."
    if plan.skipped:
        msg += "\n\n**Not set up:**\n" + "\n".join(f"- {n}: {why}" for n, why in plan.skipped)
    flash(msg, "success" if plan.created else "info")


def _auto_reminders(ctx: Ctx, rec: dict) -> None:
    linked = [r for r in reminders.list_reminders(ctx.uid, ctx.pid) if r["source_record_id"] == rec["id"]]
    plan = schedule.build_plan(ctx.uid, rec["id"])
    with st.expander(f"Reminders from this prescription ({len(linked)} set up)", icon=":material/notifications_active:",
                     expanded=bool(plan.medicine_reminders or (plan.follow_up and not plan.follow_up["existing"]))):
        for r in linked:
            st.markdown(f"- ⏰ **{r['title']}** — {r['time_of_day'] or 'any time'}, "
                        f"{'next ' + fmt_date(r['next_due']) if r['next_due'] else 'finished'}")
        todo = [f"- {d['title']} at {d['time_of_day']}" for d in plan.medicine_reminders]
        if plan.follow_up and not plan.follow_up["existing"]:
            todo.append(f"- 📅 {plan.follow_up['purpose']} on {plan.follow_up['date'].strftime('%d %b %Y')} "
                        f"({plan.follow_up['how']})")
        if todo:
            st.markdown("**Can be added automatically:**\n" + "\n".join(todo))
            st.button("Add these reminders", key="rec_auto_rem", on_click=_apply_plan, args=(ctx.uid, rec["id"]),
                      type="primary", icon=":material/add_alarm:")
        elif not linked:
            st.caption("Nothing can be set up automatically.")
        for n, why in plan.skipped:
            st.caption(f"Not set up — {n}: {why}")
        st.caption("Times come from what the prescription says (e.g. 1-0-1 → 08:00 and 21:00). Change or delete them in "
                   "Reminders. Reminders are not medical advice.")


def _history(ctx: Ctx, rec: dict) -> None:
    hist = records.record_history(ctx.uid, rec["id"])
    if not hist:
        return
    with st.expander(f"Change history ({len(hist)})", icon=":material/history:"):
        st.caption("Every change to this record is kept here so earlier values are never silently lost.")
        for h in hist:
            st.markdown(f"**{fmt_date(h['changed_at'])} {h['changed_at'][11:16]} UTC** — {h['summary']}")
            rows = [{"Field": records.HISTORY_LABELS.get(c["field"], c["field"].replace("details.", "").replace("_", " ")
                                                         .capitalize()),
                     "Before": "" if c["before"] is None else str(c["before"]),
                     "After": "" if c["after"] is None else str(c["after"])}
                    for c in h["changes"] if h["summary"] != "Record created"]
            if rows:
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def _documents(ctx: Ctx, rec: dict) -> None:
    st.markdown("#### Original documents")
    if not rec["documents"]:
        st.caption("No file attached.")
    ai_ready = is_configured() and bool(ctx.user.ai_consent_at)
    for d in rec["documents"]:
        with st.container(border=True):
            md(f"📎 <b>{esc(d['filename'])}</b> · {d['size'] // 1024 + 1} KB · uploaded {esc(fmt_date(d['uploaded_at']))}")
            c1, c2, c3 = st.columns(3)
            show = c1.toggle("Preview", key=f"rec_prev_{d['id']}")
            if c2.button("Prepare download", key=f"rec_dlprep_{d['id']}"):
                st.session_state[f"rec_dl_{d['id']}"] = True
            if st.session_state.get(f"rec_dl_{d['id']}") or show:
                try:
                    row, data = documents.read_document(ctx.uid, d["id"])
                except (FileNotFoundError, ValueError) as exc:
                    st.error(str(exc))
                    continue
                if st.session_state.get(f"rec_dl_{d['id']}"):
                    c2.download_button("Download", data, d["filename"], row["mime"], key=f"rec_dl_btn_{d['id']}")
                if show:
                    if row["mime"].startswith("image/"):
                        st.image(data)
                    else:
                        st.caption("PDF preview isn't shown in the app — download to view the original.")
            if ai_ready and c3.button("Explain with AI", key=f"rec_ai_{d['id']}", icon=":material/auto_awesome:"):
                try:
                    _, data = documents.read_document(ctx.uid, d["id"], log_access=False)
                    with st.spinner("Reading…"):
                        out = ai_tasks.summarise_document(data, d["mime"])
                    body = out["summary"]
                    if out["terms_explained"]:
                        body += "\n\n" + "\n".join(f"- **{t['term']}** — {t['meaning']}" for t in out["terms_explained"])
                    if out.get("unclear_parts"):
                        body += f"\n\n_Couldn't read: {out['unclear_parts']}_"
                    documents.set_ai_summary(ctx.uid, d["id"], body)
                    st.rerun()
                except (AIError, AIUnavailable) as exc:
                    st.error(str(exc))
            if d.get("ai_summary"):
                ai_block(f"explanation from {fmt_date(d['ai_summary_at'])}", d["ai_summary"])
            if ai_ready:
                _ask_document(ctx, d)
            if d["has_text"]:
                with st.expander("Text found in this file"):
                    st.caption("Extracted locally from the PDF's text layer.")
                    st.text((documents.get_extracted_text(ctx.uid, d["id"]) or "")[:8000])

    with st.expander("Attach another file to this record"):
        up = st.file_uploader("File", type=UPLOAD_EXTENSIONS, key=f"rec_attach_{rec['id']}")
        if up is not None and st.button("Attach", key=f"rec_attach_btn_{rec['id']}"):
            try:
                documents.store_document(ctx.uid, ctx.pid, up.name, up.getvalue(), record_id=rec["id"])
            except documents.DuplicateDocument as exc:
                st.warning(f"This exact file is already stored ({exc.existing['filename']}).")
            except documents.UploadRejected as exc:
                st.error(str(exc))
            else:
                flash("File attached.")
                st.rerun()


def _delete(ctx: Ctx, rec: dict) -> None:
    with st.expander("Delete this record", icon=":material/delete:"):
        st.warning("Deleting can't be undone.")
        with_files = st.checkbox("Also delete the attached original files", key=f"rec_del_files_{rec['id']}",
                                 disabled=not rec["documents"])
        sure = st.checkbox("Yes, delete this record", key=f"rec_del_sure_{rec['id']}")
        if st.button("Delete permanently", type="primary", disabled=not sure, key=f"rec_del_{rec['id']}"):
            records.delete_record(ctx.uid, rec["id"], delete_files=with_files)
            flash("Record deleted." + ("" if with_files or not rec["documents"] else
                                       " Its files were kept and are listed under Documents."))
            _back()
            st.rerun()


def render(ctx: Ctx) -> None:
    rid = st.session_state.get("rec_open_id")
    st.button("← Back", on_click=_back, key="rec_back", type="tertiary")
    try:
        rec = records.get_record(ctx.uid, rid) if rid else None
    except AccessDenied:
        rec = None
    if not rec or rec["profile_id"] != ctx.pid:
        st.info("This record isn't available in the selected profile.")
        return
    t = RECORD_TYPES.get(rec["type"])

    if st.session_state.get("rec_edit") == rec["id"]:
        st.markdown(f"## Edit · {rec['title']}")
        initial = dict(rec)
        result = record_form(ctx, f"rec_edit_form_{rec['id']}", rec["type"], initial,
                             rec["medications"] if (t and t.has_medications) or rec["medications"] else None,
                             rec["lab_results"] if (t and t.has_lab_results) or rec["lab_results"] else None,
                             submit_label="Save changes")
        if st.button("Cancel editing", key="rec_edit_cancel"):
            st.session_state.pop("rec_edit", None)
            st.rerun()
        if result:
            data = result["data"]
            data["source"] = rec["source"] if rec["source"] != "clinician_verified" else "patient_confirmed"
            try:
                records.save_record(ctx.uid, ctx.pid, resolve_people(ctx, data), result["meds"], result["labs"],
                                    record_id=rec["id"])
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state.pop("rec_edit", None)
                flash("Changes saved.")
                st.rerun()
        return

    st.markdown(f"## {rec['title']}")
    md(f"{badge(type_label(rec['type']), 'gray')} {source_badge(rec['source'])}")
    if rec["source"] in ("ai_extracted", "auto_extracted"):
        st.warning("These details were read from the document by AI and haven't been checked yet. Compare them with "
                   "the original below, edit anything that's wrong, then confirm.")
        st.button("I've checked this against the original", on_click=_reviewed, args=(ctx.uid, rec["id"]),
                  key="rec_reviewed", type="primary")
    st.write("")
    rows = [(t.date_label if t else "Date", fmt_date(rec["record_date"], ""))]
    if t and t.end_date_label:
        rows.append((t.end_date_label, fmt_date(rec["end_date"], "")))
    rows += [("Doctor", (rec["doctor_name"] or "") + (f" ({rec['doctor_specialty']})" if rec["doctor_specialty"] else "")),
             ("Hospital / clinic / lab", rec["facility_name"]),
             ("Condition (as documented)", rec["condition"])]
    for e in (t.extras if t else ()):
        val = rec["details"].get(e.name)
        rows.append((e.label, fmt_date(val, "") if e.kind == "date" else val))
    rows += [("Follow-up date", fmt_date(rec["follow_up_date"], "")), ("Summary", rec["summary"]),
             ("Your notes", rec["notes"]), ("Added", fmt_date(rec["created_at"])),
             ("Last changed", fmt_date(rec["updated_at"]))]
    kv(rows)

    if rec["medications"]:
        st.markdown("#### Medicines (as written)")
        for m in rec["medications"]:
            flag = " " + badge("Needs checking", "orange") if m["uncertain"] else ""
            status = badge(m["status"].title(), "green" if m["status"] == "active" else "gray")
            md(f"• <b>{esc(m['name'])}</b> {esc(m['dosage'] or '')} — {esc(m['frequency'] or 'frequency not recorded')}"
               f"{(' · ' + esc(m['duration'])) if m['duration'] else ''}{(' · ' + esc(m['instructions'])) if m['instructions'] else ''}"
               f" {status}{flag}" + (f"<br><span class='tm-row-meta'>⚠ {esc(m['uncertain_note'])}</span>" if m["uncertain"] and m["uncertain_note"] else ""))
        st.caption("Copied from the prescription. Thought Medione never changes doses — ask your doctor before changing any medicine.")
    if rec["lab_results"]:
        st.markdown("#### Test results (as printed)")
        df = pd.DataFrame([{"Test": l["test_name"], "Result": l["value_text"] if l["value_text"] is not None else l["value_num"],
                            "Unit": l["unit"], "Report's reference range": _range(l), "Compared with that range": _position(l),
                            "Needs checking": "Yes" if l["uncertain"] else ""} for l in rec["lab_results"]])
        st.dataframe(df, hide_index=True, width="stretch")
        st.caption("Ranges are the ones printed on this report. Whether a result matters for you is for your doctor to judge.")

    _documents(ctx, rec)
    _history(ctx, rec)
    st.divider()
    c1, c2 = st.columns(2)
    if c1.button("Edit record", icon=":material/edit:", key="rec_edit_btn"):
        st.session_state["rec_edit"] = rec["id"]
        st.rerun()
    if rec["follow_up_date"] or rec["medications"]:
        c2.button("Create a reminder by hand", icon=":material/alarm:", key="rec_to_rem",
                  on_click=go, args=("Reminders",), kwargs={"rem_from_record": rec["id"]})
    if rec["type"] == "prescription" or rec["medications"]:
        _auto_reminders(ctx, rec)
    _delete(ctx, rec)
    disclaimer()
