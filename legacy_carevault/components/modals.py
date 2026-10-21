"""Backward-compatible entry points for the original dialog helpers.

Dialogs are now drawn centrally by ``components.dialogs.render_active_dialog``;
these functions just request the matching dialog for the current run.
"""
from components.state import open_dialog


def open_add_record_dialog(kind: str = "visit"):
    open_dialog(kind, None, "add")


def open_appointment_dialog(apt_dict: dict):
    open_dialog("appointment", apt_dict.get("apt_id"))


def open_visit_dialog(visit_dict: dict):
    open_dialog("visit", visit_dict.get("visit_id"))


def open_diagnostic_dialog(diag_dict: dict):
    open_dialog("diagnostic", diag_dict.get("record_id"))


def open_prescription_dialog(rx_dict: dict):
    open_dialog("prescription", rx_dict.get("rx_id"))
