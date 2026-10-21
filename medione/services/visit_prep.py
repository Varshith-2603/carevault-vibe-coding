"""A one-page sheet to take to an appointment: why you're going, what's changed, what to ask."""
from __future__ import annotations

import html
from datetime import date, timedelta

from medione.models import SEVERITY, VITAL_KINDS
from medione.services import appointments, health, summary


def _e(v) -> str:
    return html.escape(str(v)) if v not in (None, "") else "<span class='nr'>Not recorded</span>"


def visit_prep_html(user_id: int, appointment_id: int) -> str:
    a = appointments.get_appointment(user_id, appointment_id)
    pid = a["profile_id"]
    s = summary.build_summary(user_id, pid)
    concerns = health.list_concerns(user_id, pid, "active")
    since = date.today() - timedelta(days=90)
    vit = [v for v in health.list_vitals(user_id, pid, since=since)]
    p = s["profile"]

    def ul(items, empty="None recorded"):
        return "<ul>" + ("".join(items) if items else f"<li class='nr'>{empty}</li>") + "</ul>"

    questions = [f"<li>{html.escape(q.strip('-• ').strip())}</li>" for q in (a.get("questions") or "").splitlines() if q.strip()]
    concern_items = []
    for c in concerns:
        hist = ", ".join(f"{l['logged_on'][5:]}: {SEVERITY[l['severity']].lower()}" for l in c["logs"][-5:])
        concern_items.append(f"<li><b>{_e(c['title'])}</b>{' (' + html.escape(c['body_area']) + ')' if c['body_area'] else ''}"
                             f" — since {_e(c['started_on'])}; now {SEVERITY[c['severity']].lower()} ({c['trend']})."
                             f"<br><span class='small'>{html.escape(hist)}</span>"
                             f"{'<br>' + html.escape(c['notes']) if c['notes'] else ''}</li>")
    vital_items = []
    for key, spec in VITAL_KINDS.items():
        mine = [v for v in vit if v["kind"] == key]
        if not mine:
            continue
        vals = ", ".join(f"{health.format_vital(v).split(' ')[0]}{'*' if v['flag'] else ''}" for v in mine[-8:])
        vital_items.append(f"<li><b>{spec.label}</b> ({spec.unit}, last {len(mine[-8:])} readings): {vals}</li>")
    med_items = [f"<li><b>{_e(m['name'])}</b> {_e(m['dosage'])} — {_e(m['frequency'])}</li>" for m in s["active_medications"]]
    allergy_items = [f"<li>{_e(r['details'].get('allergen') or r['title'])}</li>" for r in s["allergies"]]
    lab_items = [f"<li>{_e(l['test_name'])}: {_e(l['value_text'] or l['value_num'])} {html.escape(l['unit'] or '')}"
                 f" ({_e(l['record_date'])})</li>" for l in s["latest_lab_values"][:10]]
    when = date.fromisoformat(a["starts_on"]).strftime("%d %b %Y") + (f", {a['time_of_day']}" if a["time_of_day"] else "")
    who = " · ".join(x for x in (a.get("doctor_name"), a.get("facility_name")) if x)
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Visit preparation</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{{font-family:'Plus Jakarta Sans',Segoe UI,Arial,sans-serif;color:#0F2A33;max-width:820px;margin:24px auto;padding:0 16px;line-height:1.45}}
h1{{font-size:22px;margin:0}}h2{{font-size:15px;color:#0F766E;border-bottom:1px solid #D5E7E5;padding-bottom:4px;margin-top:20px}}
.meta{{color:#46616A;font-size:13px}}.nr{{color:#7C9399}}.small{{color:#46616A;font-size:12px}}
.box{{background:#E9F5F3;border-radius:10px;padding:10px 14px;margin-top:10px}}li{{margin:3px 0}}</style></head><body>
<h1>Visit preparation — {_e(p['name'])}</h1>
<div class="meta">Age {_e(p['age'])} · {_e(p['sex'])} · Blood group {_e(p['blood_group'])}</div>
<div class="box"><b>{_e(a['purpose'])}</b><br>{html.escape(when)}{(' · ' + html.escape(who)) if who else ''}</div>
<h2>Questions to ask</h2>{ul(questions, 'No questions written yet')}
<h2>Health concerns I'm having</h2>{ul(concern_items)}
<h2>Allergies</h2>{ul(allergy_items)}
<h2>Medicines I currently take (as prescribed)</h2>{ul(med_items)}
<h2>Home readings — last 90 days</h2>{ul(vital_items)}
<p class="small">* outside the general adult reference range.</p>
<h2>Latest lab results (as printed on reports)</h2>{ul(lab_items)}
<h2>Notes from the visit</h2><div style="height:140px;border:1px dashed #B9D3D0;border-radius:8px"></div>
<p class="small">Prepared {date.today().isoformat()} with Thought Medione from information the patient recorded. Not a medical document.</p>
</body></html>"""
