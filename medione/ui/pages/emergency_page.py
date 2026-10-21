"""Emergency card: critical facts on one card, with a QR code first responders can scan."""
from __future__ import annotations

import base64
import html

import streamlit as st

from medione.services import emergency
from medione.ui.state import Ctx, flash, go
from medione.ui.widgets import disclaimer, esc, fmt_date, md, page_header


NOT_RECORDED = "Not recorded — this does not mean there are none"


def card_html(c: dict) -> str:
    inc = c.get("include") or emergency.DEFAULT_INCLUDE
    allergies = ", ".join(a["what"] + (f" ({a['reaction']})" if a.get("reaction") else "") for a in c["allergies"]) \
        or NOT_RECORDED
    meds = ", ".join(f"{m['name']} {m['dose'] or ''}".strip() for m in c["medicines"]) or NOT_RECORDED
    conds = ", ".join(c["conditions"]) or NOT_RECORDED
    surgeries = ", ".join(c.get("surgeries") or []) or NOT_RECORDED
    contact = " · ".join(x for x in (c["contact_name"], c["contact_phone"]) if x) or "Not recorded"
    age = f"{c['age']} yrs" if c["age"] is not None else "Age not recorded"

    def row(key, label, value, style=""):
        return (f'<div class="full"><div class="k">{label}</div><div class="v" style="{style}">{esc(value)}</div></div>'
                if inc.get(key) else "")
    blood = (f'<div><div class="k">Blood group</div><div class="bg">{esc(c["blood_group"] or "—")}</div></div>'
             if inc.get("blood_group") else "<div></div>")
    updated = f'<div class="full" style="font-size:.75rem;color:#64748B">Information last updated {esc(fmt_date(c.get("updated_at")))}' \
              f' by the card holder.</div>' if c.get("updated_at") else ""
    return f"""<div class="tm-ecard"><div class="top"><span>✚ EMERGENCY MEDICAL CARD</span><span>Call 112</span></div>
<div class="body">
<div><div class="k">Name</div><div class="v">{esc(c['name'])}</div><div class="k" style="margin-top:.3rem">Age / sex</div>
<div class="v">{esc(age)} · {esc(c['sex'] or 'Not recorded')}</div></div>
{blood}
{row("allergies", "Allergies", allergies, "color:#B91C1C")}
{row("conditions", "Conditions", conds)}
{row("medicines", "Current medicines", meds)}
{row("surgeries", "Past surgeries", surgeries)}
{row("contact", "Emergency contact", contact)}
{updated}
</div></div>"""


def _save_include(uid: int, pid: int) -> None:
    emergency.set_include(uid, pid, {k: st.session_state.get(f"em_inc_{k}", True) for k in emergency.SECTIONS})
    flash("Emergency card updated.")


def printable(c: dict, qr_png: bytes | None, url: str | None) -> str:
    qr = (f'<div style="text-align:center"><img src="data:image/png;base64,{base64.b64encode(qr_png).decode()}" '
          f'width="150" alt="QR code"><div style="font-size:11px;color:#475569">Scan for this card online</div></div>'
          if qr_png else "")
    from medione.ui.theme import CSS
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>Emergency card</title>{CSS}"
            "<style>body{font-family:'Plus Jakarta Sans',Arial,sans-serif;margin:24px}</style></head><body>"
            f"<div style='display:flex;gap:18px;align-items:center;flex-wrap:wrap'>{card_html(c)}{qr}</div>"
            "<p style='font-size:11px;color:#475569;max-width:560px'>Information entered by the card holder in "
            f"Thought Medione. Fold and keep in your wallet. {html.escape(url or '')}</p></body></html>")


def _revoke(uid: int, pid: int) -> None:
    emergency.revoke(uid, pid)
    st.session_state.pop("em_new", None)
    flash("Online emergency card turned off. Printed QR codes no longer work.", "info")


def render(ctx: Ctx) -> None:
    page_header("Emergency card", "The few facts a doctor or first responder needs in an emergency.", "shield")
    c = emergency.card_data(ctx.uid, ctx.pid)
    left, right = st.columns([3, 2])
    with left:
        md(card_html(c))
        st.write("")
        missing = [label for key, label, v in (("blood_group", "blood group", c["blood_group"]),
                                               ("contact", "emergency contact", c["contact_phone"]))
                   if c["include"][key] and not v]
        if missing:
            st.warning(f"Add your {' and '.join(missing)} so the card is complete.")
        c1, c2 = st.columns(2)
        c1.button("Edit personal details", on_click=go, args=("Family",), key="em_edit", icon=":material/edit:")
        c2.button("Add an allergy or condition", on_click=go, args=("Add record",), key="em_add", icon=":material/add:")
        st.caption("Allergies, conditions and current medicines come from your records automatically.")
        with st.expander("Choose what the card shows", icon=":material/tune:"):
            include = c["include"]
            for key, label in emergency.SECTIONS.items():
                st.checkbox(label, value=include[key], key=f"em_inc_{key}")
            if not st.session_state.get("em_inc_allergies", True):
                st.warning("Allergies are usually the most important information in an emergency.")
            st.button("Save choices", key="em_inc_save", on_click=_save_include, args=(ctx.uid, ctx.pid), type="primary")
            st.caption("Changes apply to the printed card the next time you download it, and immediately to the "
                       "online card behind the QR code.")
    with right:
        with st.container(border=True):
            st.markdown("**Online card & QR code**")
            st.caption("Print the card with a QR code. Anyone who scans it sees **only this card** — no other records. "
                       "You can turn it off at any time, and each scan is logged.")
            link = emergency.active_link(ctx.uid, ctx.pid)
            new = st.session_state.get("em_new")
            if new and new[0] == ctx.pid:
                url = new[1]
                png = emergency.qr_png(url)
                st.image(png, width=170)
                st.code(url, language=None)
                st.download_button("Download printable card", printable(c, png, url), "emergency-card.html", "text/html",
                                   key="em_dl_new", icon=":material/print:", type="primary")
                st.caption("Save or print it now — for security the link is only shown once.")
            elif link:
                st.success(f"Online card is on (since {fmt_date(link['created_at'])}). "
                           f"Scanned {link['access_count']} time(s).")
                st.caption("Lost the printout? Create a new QR code — the old one stops working.")
            else:
                st.info("Online card is off.")
            c1, c2 = st.columns(2)
            if c1.button("Create new QR code" if link else "Turn on & create QR", key="em_create", type="secondary"):
                token = emergency.create_link(ctx.uid, ctx.pid)
                st.session_state["em_new"] = (ctx.pid, emergency.card_url(token))
                st.rerun()
            if link:
                c2.button("Turn off", key="em_revoke", on_click=_revoke, args=(ctx.uid, ctx.pid))
            st.download_button("Download card without QR", printable(c, None, None), "emergency-card.html", "text/html",
                               key="em_dl_plain", icon=":material/download:")
    disclaimer()


def render_public(token: str) -> None:
    """What someone sees after scanning the QR code."""
    try:
        c = emergency.open_card(token, log_visit=not st.session_state.get(f"_em_seen_{token[:8]}"))
    except emergency.CardUnavailable as exc:
        st.error(str(exc))
        return
    st.session_state[f"_em_seen_{token[:8]}"] = True
    md(card_html(c))
    st.write("")
    st.error("In a medical emergency call **112** (ambulance **108**).")
    st.caption("Information entered by the card holder in Thought Medione. It may be incomplete — confirm with the "
               "patient or family where possible.")
