"""Session state: who is signed in, which profile is active, navigation and flash messages."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import streamlit as st

from medione import config
from medione.auth import User, get_user
from medione.services.profiles import list_profiles

# Keys that belong to one profile's context and must be cleared when switching profile.
PROFILE_SCOPED_PREFIXES = ("rec_", "upl_", "flt_", "share_", "ai_", "rem_", "med_", "dir_", "edit_", "ap_", "appt_", "bot_",
                           "conc_", "vit_", "em_")


@dataclass
class Ctx:
    user: User
    profile: dict
    profiles: list[dict]

    @property
    def uid(self) -> int:
        return self.user.id

    @property
    def pid(self) -> int:
        return self.profile["id"]


def sign_in(user: User) -> None:
    st.session_state.clear()
    st.session_state["uid"] = user.id
    st.session_state["last_seen"] = time.time()
    st.session_state["page"] = "Dashboard"


def sign_out(message: str = "") -> None:
    st.session_state.clear()
    if message:
        st.session_state["flash"] = ("info", message)


def check_timeout() -> None:
    if "uid" not in st.session_state:
        return
    idle = time.time() - st.session_state.get("last_seen", time.time())
    if idle > config.settings.session_timeout_min * 60:
        sign_out("You were signed out after a period of inactivity. Please sign in again.")
    else:
        st.session_state["last_seen"] = time.time()


def current_context() -> Optional[Ctx]:
    uid = st.session_state.get("uid")
    if not uid:
        return None
    user = get_user(uid)
    if user is None:
        sign_out()
        return None
    profiles = list_profiles(uid)
    if not profiles:
        sign_out()
        return None
    wanted = st.session_state.get("profile_id")
    profile = next((p for p in profiles if p["id"] == wanted), profiles[0])
    st.session_state["profile_id"] = profile["id"]
    return Ctx(user, profile, profiles)


def switch_profile(profile_id: int) -> None:
    for key in list(st.session_state.keys()):
        if key.startswith(PROFILE_SCOPED_PREFIXES):
            del st.session_state[key]
    st.session_state["profile_id"] = profile_id
    if st.session_state.get("page") == "Record":
        st.session_state["page"] = "Dashboard"


def go(page: str, **values) -> None:
    """Navigate (safe to use as an on_click callback)."""
    st.session_state["page"] = page
    for k, v in values.items():
        st.session_state[k] = v


def open_record(record_id: int) -> None:
    st.session_state["back_to"] = st.session_state.get("page", "Dashboard")
    st.session_state["page"] = "Record"
    st.session_state["rec_open_id"] = record_id
    st.session_state.pop("rec_edit", None)


def flash(message: str, kind: str = "success") -> None:
    st.session_state["flash"] = (kind, message)


def show_flash() -> None:
    item = st.session_state.pop("flash", None)
    if item:
        kind, message = item
        {"success": st.success, "info": st.info, "warning": st.warning, "error": st.error}[kind](message)
