"""Add a record: upload a document (optionally read by AI) or type the details in."""
from __future__ import annotations

import streamlit as st

from medione import config
from medione.ai import tasks as ai_tasks
from medione.ai.client import AIError, AIUnavailable, is_configured
from medione.models import RECORD_TYPES, UPLOAD_EXTENSIONS
from medione.services import directory, documents, records, rx_parser, schedule
from medione.ui.record_form import record_form, resolve_people, type_picker
from medione.ui.state import Ctx, flash, open_record
from medione.ui.widgets import disclaimer, esc, fmt_date, md, page_header


def _reset() -> None:
    for k in list(st.session_state):
        if k.startswith("upl_"):
            del st.session_state[k]


def _draft_from_ai(ctx: Ctx, result: dict) -> dict:
    """Map AI output onto the form. Doctor/facility are matched to existing names only; new ones are prefilled as text."""
    docs = {d["name"].lower(): d["id"] for d in directory.list_doctors(ctx.uid)}
    facs = {f["name"].lower(): f["id"] for f in directory.list_facilities(ctx.uid)}
    doctor, facility = (result.get("doctor_name") or "").strip(), (result.get("facility_name") or "").strip()
    rtype = result["document_type"]
    allowed_extras = {e.name for e in RECORD_TYPES[rtype].extras}
    initial = {
        "title": result.get("title"), "record_date": result.get("record_date"), "end_date": result.get("end_date"),
        "follow_up_date": result.get("follow_up_date"), "condition": result.get("condition"),
        "summary": result.get("summary"),
        "doctor_id": docs.get(doctor.lower()), "new_doctor": "" if doctor.lower() in docs else doctor,
        "facility_id": facs.get(facility.lower()), "new_facility": "" if facility.lower() in facs else facility,
        "details": {f["name"]: f["value"] for f in result.get("extra_fields", []) if f["name"] in allowed_extras},
    }
    meds = [{"name": m["name"], "dosage": m.get("dosage"), "frequency": m.get("frequency"),
             "duration": m.get("duration"), "instructions": m.get("instructions"), "status": "active",
             "uncertain": bool(m.get("uncertain")), "uncertain_note": m.get("uncertain_reason")}
            for m in result.get("medications", [])]
    labs = [{"test_name": l["test_name"], "value_text": l.get("value"), "unit": l.get("unit"),
             "ref_low": l.get("ref_low"), "ref_high": l.get("ref_high"), "ref_text": l.get("ref_text"),
             "uncertain": bool(l.get("uncertain"))} for l in result.get("lab_results", [])]
    return {"type": rtype, "initial": initial, "meds": meds, "labs": labs,
            "uncertain": tuple(result.get("uncertain_fields") or ()), "note": result.get("legibility_note"),
            "from_ai": True}


def _upload_step(ctx: Ctx) -> None:
    ai_ready = is_configured() and bool(ctx.user.ai_consent_at)
    st.markdown("#### 1 · Choose the file")
    st.caption(f"PDF, JPG, PNG or WEBP, up to {config.settings.max_upload_mb} MB. The original is stored encrypted "
               "and never changed.")
    up = st.file_uploader("Medical document", type=UPLOAD_EXTENSIONS, key="upl_file", label_visibility="collapsed")
    use_ai = False
    if ai_ready:
        use_ai = st.toggle("Read the document with AI and fill in the form for me", value=True, key="upl_use_ai",
                           help="The file is sent to the Claude API (Anthropic) for reading. You review everything before it is saved.")
    elif is_configured():
        st.info("AI reading is off. You can turn it on in Settings → AI features.")
    if up is None:
        return
    data = up.getvalue()
    try:
        documents.validate_upload(up.name, data)
    except documents.UploadRejected as exc:
        st.error(str(exc))
        return
    dup = documents.find_duplicate(ctx.uid, ctx.pid, data)
    allow_dup = False
    if dup:
        where = f"attached to “{dup['record_title']}”" if dup["record_title"] else "not attached to a record"
        st.warning(f"You uploaded this exact file on {fmt_date(dup['uploaded_at'])} ({where}). "
                   "Saving it again would create a duplicate.")
        c1, c2 = st.columns(2)
        if dup["record_id"]:
            c1.button("Open the existing record", on_click=open_record, args=(dup["record_id"],), key="upl_dup_open")
        allow_dup = c2.checkbox("It's a different document — upload anyway", key="upl_dup_ok")
        if not allow_dup:
            return
    # Read the document straight away — no extra click needed.
    st.session_state["upl_bytes"] = data
    st.session_state["upl_name"] = up.name
    st.session_state["upl_allow_dup"] = allow_dup
    mime = documents.sniff_mime(data)
    text = documents.extract_pdf_text(data) if mime == "application/pdf" else None
    st.session_state["upl_text"] = text
    draft = {"type": "other", "initial": {}, "meds": [], "labs": [], "uncertain": (), "note": None, "from_ai": False,
             "method": None}
    if use_ai:
        try:
            with st.spinner("Reading your document with AI… this can take up to a minute."):
                draft = {**_draft_from_ai(ctx, ai_tasks.extract_document(data, mime, text)), "method": "ai"}
        except (AIError, AIUnavailable) as exc:
            st.session_state["upl_ai_error"] = str(exc)
    if draft["method"] is None and text:
        parsed = rx_parser.parse_text(text)
        if parsed:
            draft = {**_draft_from_ai(ctx, parsed), "method": "auto"}
    st.session_state["upl_draft"] = draft
    st.rerun()


def _review_step(ctx: Ctx) -> None:
    draft = st.session_state["upl_draft"]
    name = st.session_state["upl_name"]
    method = draft.get("method")
    st.markdown(f"#### 2 · {'Check what was read from your document' if draft['from_ai'] else 'Describe the document'}")
    md(f"File: <b>{esc(name)}</b>")
    if st.session_state.get("upl_ai_error"):
        st.warning(f"AI reading didn't work: {st.session_state['upl_ai_error']}" +
                   (" The typed text of the PDF was read instead." if method == "auto" else
                    " Please fill in the details yourself."))
    if draft["from_ai"]:
        who = "The AI" if method == "ai" else "Thought Medione (from the PDF's typed text, without AI)"
        st.info(f"{who} read the details below. Compare every field with the original — especially medicine names, "
                "doses and dates. Fields marked ⚠ were unclear. Nothing is saved until you press Save.")
    elif draft["type"] == "other" and not st.session_state.get("upl_ai_error"):
        st.info("This file couldn't be read automatically (photos and handwriting need AI — switch it on in Settings → "
                "AI features). Please fill in the details below.")
        if draft.get("note"):
            st.warning(f"Readability note: {draft['note']}")
        if any(m.get("uncertain") for m in draft["meds"]) or any(l.get("uncertain") for l in draft["labs"]):
            st.warning("Some medicines or results are marked *Needs checking*. They will stay flagged until you confirm them.")
    if st.session_state.get("upl_text"):
        with st.expander("Text found in the PDF (to help you copy details)"):
            st.text(st.session_state["upl_text"][:6000])
    rtype = type_picker("upl_type", draft["type"])
    auto = _auto_reminder_choice(rtype, draft["meds"], draft["initial"], "upl_auto_rem")
    result = record_form(ctx, f"upl_form_{rtype}", rtype, draft["initial"], draft["meds"], draft["labs"],
                         draft["uncertain"], "Save record and document", show_review_confirm=draft["from_ai"])
    st.button("Cancel", on_click=_reset, key="upl_cancel")
    if result:
        data = result["data"]
        unreviewed = "ai_extracted" if method == "ai" else "auto_extracted"
        data["source"] = ("patient_confirmed" if result["reviewed"] else unreviewed) if draft["from_ai"] else "patient"
        if result["reviewed"]:
            for row in (result["meds"] or []) + (result["labs"] or []):
                row["uncertain"] = False
        try:
            rid = records.save_record(ctx.uid, ctx.pid, resolve_people(ctx, data), result["meds"], result["labs"])
            documents.store_document(ctx.uid, ctx.pid, name, st.session_state["upl_bytes"], record_id=rid,
                                     allow_duplicate=st.session_state.get("upl_allow_dup", False))
        except ValueError as exc:
            st.error(str(exc))
            return
        _reset()
        flash("Saved. The original document is attached to the record." + (_setup_reminders(ctx, rid) if auto else ""))
        open_record(rid)
        st.rerun()


def _auto_reminder_choice(rtype: str, meds: list, initial: dict, key: str) -> bool:
    """Checkbox (on by default) plus a preview of what the prescription would turn into."""
    if rtype != "prescription" and not meds:
        return False
    with st.container(border=True):
        auto = st.checkbox("After saving, automatically add **medicine reminders** and the **next appointment** from "
                           "this prescription", value=True, key=key)
        lines = []
        for m in meds:
            if not m.get("name"):
                continue
            label = " ".join(x for x in (m["name"], m.get("dosage")) if x)
            if m.get("uncertain"):
                lines.append(f"- {label}: ⚠️ confirm the details first (tick *I have checked…* below)")
                continue
            slots, _, how = schedule.parse_times(m.get("frequency"), m.get("instructions"))
            lines.append(f"- {label}: " + (", ".join(f"{t} ({lab})" for lab, t in slots) + f" — {how}"
                                           if slots else f"no reminder — {how}"))
        if initial.get("follow_up_date"):
            lines.append(f"- Next appointment: {initial['follow_up_date']} (date read from the prescription)")
        if lines:
            st.caption("Based on what was read (you can change times later in Reminders):\n" + "\n".join(lines))
        st.caption("Reminders only repeat what the prescription says — they are not medical advice. Medicines taken "
                   "“only when needed” never get a reminder.")
    return auto


def _setup_reminders(ctx: Ctx, rid: int) -> str:
    plan = schedule.apply_plan(ctx.uid, rid)
    text = ""
    if plan.created:
        text += "\n\n**Set up automatically:**\n" + "\n".join(f"- {c}" for c in plan.created)
    if plan.skipped:
        text += "\n\n**Not set up:**\n" + "\n".join(f"- {n}: {why}" for n, why in plan.skipped)
    return text


def _manual(ctx: Ctx) -> None:
    rtype = type_picker("upl_manual_type")
    auto = _auto_reminder_choice(rtype, [], {}, "upl_manual_auto_rem")
    result = record_form(ctx, f"upl_manual_{rtype}", rtype)
    if result:
        try:
            rid = records.save_record(ctx.uid, ctx.pid, resolve_people(ctx, result["data"]), result["meds"], result["labs"])
        except ValueError as exc:
            st.error(str(exc))
            return
        flash("Record saved." + (_setup_reminders(ctx, rid) if auto else ""))
        open_record(rid)
        st.rerun()


def render(ctx: Ctx) -> None:
    page_header("Add record", f"Adding to {ctx.profile['full_name']}'s records.")
    if "upl_draft" in st.session_state:
        _review_step(ctx)
    else:
        mode = st.segmented_control("How do you want to add it?", ["Upload a document", "Type it in"],
                                    default="Upload a document", key="upl_mode", required=True)
        if mode == "Upload a document":
            _upload_step(ctx)
        else:
            _manual(ctx)
    disclaimer()
