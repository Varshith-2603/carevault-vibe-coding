"""Schema-driven add/edit forms, rendered inside the record dialog."""
import uuid
from datetime import date, datetime
from typing import Any, Dict, Optional

import streamlit as st

from components.state import FORM_PREFIX, close_dialog, flash, open_dialog
from components.ui import field_error, html_block, notice
from utils.helpers import is_missing, parse_date
from utils.records import (
    RECORD_TYPES, Field, add_record, clean_values, get_df, get_record, possible_duplicate,
    suggestions, update_record, validate, visit_label,
)

MAX_ATTACHMENT_MB = 10
REQUIRED_MARK = ' <span class="cv-required" aria-label="required">*</span>'


def _k(kind: str, name: str) -> str:
    return f"{FORM_PREFIX}{kind}_{name}"


def _to_widget(f: Field, value: Any, mode: str) -> Any:
    if f.kind == "date":
        return parse_date(value) or (date.today() if mode == "add" else None)
    if f.kind == "optional_date":
        return parse_date(value)
    if f.kind == "time":
        if is_missing(value):
            return None
        for fmt in ("%I:%M %p", "%H:%M"):
            try:
                return datetime.strptime(str(value).strip(), fmt).time()
            except ValueError:
                continue
        return None
    if f.kind in ("number", "float"):
        return None if is_missing(value) else (float(value) if f.kind == "float" else int(float(value)))
    if f.kind == "select":
        if not is_missing(value):
            return str(value)
        return f.options[0] if f.options and not f.accept_new else None
    if f.kind == "visit_link":
        return "" if is_missing(value) else str(value)
    return "" if is_missing(value) else str(value)


def _prefill(kind: str, mode: str, record: Optional[Dict[str, Any]], preset: Optional[Dict[str, Any]] = None):
    rt = RECORD_TYPES[kind]
    source = dict(record or {})
    source.update(preset or {})
    for f in rt.fields:
        st.session_state[_k(kind, f.name)] = _to_widget(f, source.get(f.name), mode)
    st.session_state[_k(kind, "_token")] = uuid.uuid4().hex
    st.session_state[_k(kind, "_ready")] = True


def _render_field(kind: str, f: Field, errors: Dict[str, str]):
    key = _k(kind, f.name)
    label = f.label + (" *" if f.required else "")
    common = dict(key=key, help=f.help or None)
    if f.kind == "textarea":
        st.text_area(label, placeholder=f.placeholder or None, height=96, **common)
    elif f.kind in ("date", "optional_date"):
        st.date_input(label, value=None, format="DD/MM/YYYY", **common)
    elif f.kind == "time":
        st.time_input(label, value=None, step=300, format="12h", **common)
    elif f.kind == "number":
        st.number_input(label, value=None, min_value=int(f.min_value) if f.min_value is not None else None,
                        max_value=int(f.max_value) if f.max_value is not None else None, step=1,
                        placeholder="Not recorded", **common)
    elif f.kind == "float":
        st.number_input(label, value=None, min_value=float(f.min_value) if f.min_value is not None else None,
                        max_value=float(f.max_value) if f.max_value is not None else None, step=0.1, format="%.1f",
                        placeholder="Not recorded", **common)
    elif f.kind == "select":
        opts = suggestions(f, st.session_state.get(key))
        st.selectbox(label, opts, index=None, accept_new_options=f.accept_new,
                     placeholder="Choose or type a new one" if f.accept_new else "Choose one", **common)
    elif f.kind == "visit_link":
        visits = get_df("visit")
        opts = [""] + list(visits["visit_id"])
        if st.session_state.get(key) not in opts:
            opts.insert(1, st.session_state.get(key))
        st.selectbox(label, opts, index=0, format_func=lambda v: "No linked visit" if not v else visit_label(v), **common)
    else:
        st.text_input(label, placeholder=f.placeholder or None, max_chars=200, **common)
    if f.name in errors:
        field_error(errors[f.name])


def render_record_form(kind: str, mode: str, record_id: Optional[str] = None, preset: Optional[Dict[str, Any]] = None):
    """Draw the form for ``kind`` in add or edit mode. Handles validation, saving and closing."""
    rt = RECORD_TYPES[kind]
    record = get_record(kind, record_id) if record_id else None
    if mode == "edit" and record is None:
        html_block(notice("This record no longer exists. It may have been deleted.", "warning"))
        return
    if not st.session_state.get(_k(kind, "_ready")):
        _prefill(kind, mode, record, preset)

    errors: Dict[str, str] = st.session_state.get(_k(kind, "_errors"), {})
    duplicate_of = st.session_state.get(_k(kind, "_duplicate"))

    html_block('<p class="cv-form-hint">Fields marked <strong>*</strong> are required. Everything else is optional — '
               'leave it blank if it wasn\'t recorded.</p>')
    if errors:
        n = len(errors)
        html_block(notice(f"Please check {n} field{'s' if n != 1 else ''} below.", "danger"))

    with st.form(key=f"cvform_{kind}_{mode}", border=False, enter_to_submit=False):
        for section, fields in rt.sections:
            html_block(f'<div class="cv-form-section">{section}</div>')
            short = [f for f in fields if f.kind != "textarea"]
            long = [f for f in fields if f.kind == "textarea"]
            for i in range(0, len(short), 2):
                cols = st.columns(2, gap="medium")
                for col, f in zip(cols, short[i:i + 2]):
                    with col:
                        _render_field(kind, f, errors)
            for f in long:
                _render_field(kind, f, errors)

        if kind == "diagnostic":
            html_block('<div class="cv-form-section">Report file</div>')
            existing = st.session_state.get("attachments", {}).get((kind, record_id)) if record_id else None
            if existing:
                st.checkbox(f"Remove the attached file ({existing['name']})", key=_k(kind, "_remove_file"))
            st.file_uploader(
                "Attach the report (optional)", type=["pdf", "png", "jpg", "jpeg"], key=_k(kind, "_file"),
                help=f"PDF or image, up to {MAX_ATTACHMENT_MB} MB. Files are kept only for this browser session.",
            )

        if duplicate_of:
            html_block(notice(
                f"A very similar record already exists ({duplicate_of}) with the same date and name. "
                "Tick the box below if you really want to save another one.", "warning"))
            st.checkbox("Yes, save it anyway", key=_k(kind, "_dup_ok"))

        st.divider()
        c1, c2 = st.columns(2, gap="small")
        with c1:
            cancelled = st.form_submit_button("Cancel", width="stretch", icon=":material/close:")
        with c2:
            submitted = st.form_submit_button(
                "Save record" if mode == "add" else "Save changes", type="primary", width="stretch",
                icon=":material/save:",
            )

    if cancelled:
        if mode == "edit":
            open_dialog(kind, record_id, "view")
        else:
            close_dialog()
        st.rerun()

    if submitted:
        _handle_submit(kind, mode, record_id)


def _handle_submit(kind: str, mode: str, record_id: Optional[str]):
    rt = RECORD_TYPES[kind]
    token = st.session_state.get(_k(kind, "_token"))
    used = st.session_state.setdefault("_cv_used_tokens", set())
    if token in used:  # a second click on Save while the first was processing
        return

    raw = {f.name: st.session_state.get(_k(kind, f.name)) for f in rt.fields}
    errors = validate(kind, raw)

    upload = st.session_state.get(_k(kind, "_file"))
    if upload is not None and upload.size > MAX_ATTACHMENT_MB * 1024 * 1024:
        errors["_file"] = f"The file is larger than {MAX_ATTACHMENT_MB} MB."

    values = clean_values(kind, raw)
    if not errors and mode == "add" and not st.session_state.get(_k(kind, "_dup_ok")):
        dup = possible_duplicate(kind, values)
        if dup:
            st.session_state[_k(kind, "_duplicate")] = dup
            st.session_state[_k(kind, "_errors")] = {}
            st.rerun()

    if errors:
        st.session_state[_k(kind, "_errors")] = errors
        if "_file" in errors:
            st.toast(errors["_file"], icon=":material/error:")
        st.rerun()

    used.add(token)
    if mode == "add":
        saved_id = add_record(kind, values)
        flash(f"{rt.label} saved.")
    else:
        update_record(kind, record_id, values)
        saved_id = record_id
        flash("Changes saved.")

    attachments = st.session_state.setdefault("attachments", {})
    if st.session_state.get(_k(kind, "_remove_file")):
        attachments.pop((kind, saved_id), None)
    if upload is not None:
        attachments[(kind, saved_id)] = {"name": upload.name, "type": upload.type, "data": upload.getvalue()}

    open_dialog(kind, saved_id, "view")
    st.rerun()
