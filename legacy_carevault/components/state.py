"""Session-state actions shared by every component: navigation, dialogs and flash messages.

These functions only change ``st.session_state`` so they are safe to use as
widget ``on_click`` callbacks. The dialog itself is drawn once per run by
``components.dialogs.render_active_dialog`` — so only one dialog is ever open.
"""
from typing import Any, Optional
import streamlit as st

DIALOG_KEY = "cv_dialog"
FORM_PREFIX = "frm_"


def navigate(page: str, presets: Optional[dict] = None):
    """Switch page. ``presets`` sets filter widget values on the destination page."""
    st.session_state.current_page = page
    for key, value in (presets or {}).items():
        st.session_state[key] = value
    close_dialog()


def open_dialog(kind: str, record_id: Optional[str] = None, mode: str = "view", **extra: Any):
    """mode: view | edit | add | delete | cancel_appointment"""
    _clear_form_state()
    st.session_state[DIALOG_KEY] = {"kind": kind, "id": record_id, "mode": mode, **extra}


def close_dialog():
    st.session_state.pop(DIALOG_KEY, None)
    _clear_form_state()


def active_dialog() -> Optional[dict]:
    return st.session_state.get(DIALOG_KEY)


def _clear_form_state():
    for key in [k for k in st.session_state.keys() if str(k).startswith(FORM_PREFIX)]:
        del st.session_state[key]


def flash(message: str, icon: str = ":material/check_circle:"):
    """Queue a toast that survives the rerun that follows a save or delete."""
    st.session_state["_cv_flash"] = (message, icon)


def show_flash():
    msg = st.session_state.pop("_cv_flash", None)
    if msg:
        st.toast(msg[0], icon=msg[1])
