"""Medi — the in-app helper chatbot.

Answers come, in order of preference, from:
1. safety rules (emergency words always get the emergency numbers first),
2. the signed-in user's own records for the active profile (appointments, medicines, results, search…),
3. a built-in FAQ and glossary,
4. optionally Claude (only when the server is configured and the user has consented).
Nothing is invented: record answers are read from the database and say so when nothing is found.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from medione.models import SEVERITY, type_label
from medione.services import appointments, dashboard, health, nlsearch, records, search, summary

PAGES = ["Dashboard", "Timeline", "Appointments", "Symptoms", "Vitals", "Medicines", "Lab results", "Reminders",
         "Add record", "Records", "Doctors & facilities", "Emergency card", "Share", "Family", "Settings", "Help"]


@dataclass
class Reply:
    text: str
    source: str = "Thought Medione guide"
    records: list[dict] = field(default_factory=list)
    actions: list[tuple[str, str]] = field(default_factory=list)  # (button label, page)
    suggestions: list[str] = field(default_factory=list)
    urgent: bool = False


EMERGENCY = re.compile(
    r"chest pain|heart attack|can'?t breathe|cannot breathe|trouble breathing|difficulty breathing|"
    r"short(ness)? of breath|unconscious|fainted|passed out|stroke|face drooping|slurred speech|seizure|fits?\b|"
    r"heavy bleeding|bleeding a lot|overdose|poison|swallowed|severe allergic|anaphyla|throat (is )?swelling", re.I)
SELF_HARM = re.compile(r"suicid|kill myself|end my life|self[- ]harm|hurt myself|want to die", re.I)
TREATMENT_ADVICE = re.compile(
    r"\b(should|can|could|may)\s+i\s+(stop|start|skip|double|increase|reduce|decrease|change|quit|take more|take less|"
    r"take)\b|\bhow (much|many) (should|can) i take\b|\bsafe to (stop|take|mix)\b", re.I)

GREETING_SUGGESTIONS = ["When is my next appointment?", "What medicines am I taking?", "Find my latest blood test",
                        "What does HbA1c mean?", "How do I share records with a doctor?"]

GLOSSARY = {
    "hba1c": "HbA1c is a blood test that reflects your average blood sugar over roughly the past 2–3 months.",
    "ldl": "LDL cholesterol is often called 'bad' cholesterol; it's one of the numbers in a lipid profile.",
    "hdl": "HDL cholesterol is often called 'good' cholesterol; it's part of a lipid profile.",
    "triglycerides": "Triglycerides are a type of fat in the blood, measured in a lipid profile.",
    "lipid profile": "A lipid profile is a blood test that measures cholesterol (total, LDL, HDL) and triglycerides.",
    "tsh": "TSH (thyroid-stimulating hormone) is a blood test used to check how the thyroid gland is working.",
    "creatinine": "Creatinine is a waste product filtered by the kidneys; the blood level is used to check kidney function.",
    "haemoglobin": "Haemoglobin (Hb) is the protein in red blood cells that carries oxygen.",
    "hemoglobin": "Haemoglobin (Hb) is the protein in red blood cells that carries oxygen.",
    "cbc": "A CBC (complete blood count) measures red cells, white cells, haemoglobin and platelets.",
    "eosinophils": "Eosinophils are a type of white blood cell, often involved in allergies and asthma.",
    "ige": "IgE is an antibody linked to allergic reactions; a 'total IgE' test measures its level in the blood.",
    "spo2": "SpO₂ is the oxygen saturation of your blood, usually measured with a finger pulse oximeter.",
    "systolic": "Systolic is the top number in a blood-pressure reading — the pressure when the heart beats.",
    "diastolic": "Diastolic is the bottom number in a blood-pressure reading — the pressure between beats.",
    "blood pressure": "Blood pressure is written as two numbers, e.g. 120/80 mmHg: systolic (top) over diastolic (bottom).",
    "fasting": "A fasting test is done after not eating (usually 8–12 hours); water is normally allowed — check with the lab.",
    "prediabetes": "Prediabetes means blood sugar is higher than typical but below the range used to diagnose diabetes.",
    "hypertension": "Hypertension is the medical word for high blood pressure.",
    "ecg": "An ECG records the heart's electrical activity using stickers on the chest, arms and legs.",
    "echo": "An echocardiogram ('echo') is an ultrasound scan of the heart.",
    "lvef": "LVEF (ejection fraction) is the percentage of blood the left side of the heart pumps out with each beat.",
    "lvh": "LVH (left ventricular hypertrophy) means the main pumping chamber's wall is thicker than usual.",
    "spirometry": "Spirometry is a breathing test that measures how much and how fast you can blow air out.",
    "fev1": "FEV1 is how much air you can blow out in the first second of a forceful breath (from spirometry).",
    "mri": "An MRI scan uses strong magnets and radio waves (no X-rays) to make detailed pictures inside the body.",
    "ct": "A CT scan uses X-rays and a computer to make cross-section pictures of the body.",
    "ultrasound": "An ultrasound uses sound waves to make pictures; it doesn't use radiation.",
    "x-ray": "An X-ray uses a small dose of radiation to make pictures, mostly of bones and the chest.",
    "echogenicity": "Echogenicity describes how bright tissue looks on an ultrasound; 'increased' is a description, "
                    "not a diagnosis by itself.",
    "fatty liver": "Fatty liver means extra fat stored in the liver, often noticed on an ultrasound.",
    "vitamin d": "Vitamin D (25-OH) is a blood test of your vitamin D level; vitamin D helps keep bones healthy.",
    "od": "OD on a prescription usually means 'once a day'.",
    "bd": "BD (or BID) on a prescription usually means 'twice a day'.",
    "tds": "TDS (or TID) on a prescription usually means 'three times a day'.",
    "qid": "QID on a prescription usually means 'four times a day'.",
    "sos": "SOS on a prescription usually means 'only if needed'.",
    "hs": "HS on a prescription usually means 'at bedtime'.",
    "ac": "AC on a prescription usually means 'before food'.",
    "pc": "PC on a prescription usually means 'after food'.",
    "stat": "STAT means 'immediately'.",
    "rx": "Rx is a common short form for 'prescription'.",
    "1-0-1": "1-0-1 on an Indian prescription usually means: 1 in the morning, 0 in the afternoon, 1 at night.",
}

FAQ = [
    (("upload", "add record", "add a record", "scan", "photo", "pdf"),
     "Tap **Add record** → *Upload a document*, choose a PDF or photo, then check the details and press Save. "
     "The original file is stored encrypted and never changed.", "Add record"),
    (("share", "send to doctor", "link"),
     "Open **Share**, pick the records, say who it's for and how long the link should work. Only those records are "
     "visible, you can turn the link off any time, and every visit is logged.", "Share"),
    (("emergency card", "qr", "wallet card"),
     "The **Emergency card** shows blood group, allergies, conditions, current medicines and an emergency contact. "
     "You choose what's on it, can print it with a QR code, and can switch the QR off any time.", "Emergency card"),
    (("family", "child", "parent", "spouse", "add member", "mother", "father", "wife", "husband", "son", "daughter",
      "kid", "caregiver"),
     "Use **Family** → *Add a family member*. Each person gets separate records, reminders and links. Switch between "
     "them with *Viewing records of* at the top of the menu.", "Family"),
    (("safe", "privacy", "secure", "who can see", "encrypt"),
     "Only you can see your records after signing in. Files are stored encrypted, share links expire and can be "
     "turned off, and AI features stay off unless you switch them on.", "Help"),
    (("automatic", "automatically", "from prescription", "from my prescription", "auto reminder"),
     "When you upload a prescription, Thought Medione reads the medicines (AI for photos; typed PDFs work without AI). "
     "After you check and save, it adds medicine reminders from what's written — e.g. *1-0-1* → 8:00 and 21:00, "
     "until the course ends — and the follow-up appointment with a reminder the day before. *SOS / when needed* "
     "medicines and unclear details never get a reminder.", "Add record"),
    (("reminder", "notification", "alarm", "remind"),
     "Create reminders under **Reminders**. To get phone notifications, use *Add all to my calendar (.ics)*.",
     "Reminders"),
    (("appointment", "book", "visit sheet"),
     "Book visits under **Appointments**. Write your questions there and download the *visit sheet* before you go.",
     "Appointments"),
    (("symptom", "concern", "diary", "pain"),
     "Track how you feel under **Symptoms**: add a concern, then log its severity every few days. Doctors find the "
     "trend useful.", "Symptoms"),
    (("vital", "reading", "bp", "sugar log", "weight"),
     "Log blood pressure, sugar, pulse, oxygen, temperature or weight under **Vitals**, and see the trend charts.",
     "Vitals"),
    (("export", "download all", "backup", "copy of my data"),
     "Go to **Settings → Your data → Prepare export** to download everything (data and original files) as a ZIP.",
     "Settings"),
    (("delete account", "remove account", "close account"),
     "In **Settings → Delete account**. It permanently removes every profile, record and file — export first.",
     "Settings"),
    (("password", "forgot", "recovery code", "locked"),
     "Change your password in **Settings**. If you forget it, use *Forgot password* on the sign-in page with your "
     "recovery code.", "Settings"),
    (("ai", "artificial", "claude", "read my document"),
     "AI can read uploaded documents and explain them, but only after you switch it on (Settings → AI features). "
     "You always review what it read before anything is saved.", "Settings"),
    (("label", "not yet reviewed", "reviewed by you", "ai-extracted"),
     "Labels show where information came from: *Entered by you*, *AI-extracted · not yet reviewed* (check it!), or "
     "*AI-extracted · reviewed by you*.", "Help"),
    (("duplicate",),
     "When two records look the same (same type, date and similar title) the Dashboard asks you to review them. "
     "Nothing is ever deleted automatically.", "Dashboard"),
    (("lab", "trend", "compare results"),
     "**Lab results** compares the same test across dates — only when the units match — with the change since the "
     "previous result.", "Lab results"),
    (("summary", "history for doctor"),
     "The Dashboard's **Health summary** builds a one-page factual summary of your records (no AI). You can preview "
     "it before downloading.", "Dashboard"),
]
FAQ_TEXT = "\n".join(f"- {a}" for _, a, _ in FAQ)


def _fmt(d: Optional[str]) -> str:
    try:
        return date.fromisoformat(d[:10]).strftime("%d %b %Y") if d else "no date"
    except ValueError:
        return d or "no date"


def _rec(r: dict) -> dict:
    return {"id": r["id"], "title": r["title"], "date": r.get("record_date"), "type": type_label(r["type"])}


def _has(q: str, *patterns: str) -> bool:
    return any(re.search(p, q) for p in patterns)


def answer(user_id: int, profile_id: int, question: str, profile_name: str = "you",
           history: Optional[list[dict]] = None, ai_ready: bool = False) -> Reply:
    q = " " + question.lower().strip() + " "
    if not question.strip():
        return Reply("Hi! I'm **Medi** 👋 Ask me about your appointments, medicines, reports, or how to use the app.",
                     suggestions=GREETING_SUGGESTIONS)

    # 1 ── safety first
    if SELF_HARM.search(q):
        return Reply("I'm really sorry you're feeling this way. You don't have to go through it alone — please talk to "
                     "someone now: call **Tele-MANAS 14416** (free, 24×7 mental-health support in India) or **112** if "
                     "you are in immediate danger.", source="Safety", urgent=True)
    if EMERGENCY.search(q):
        return Reply("⚠️ **This could be an emergency. Call 112 (or 108 for an ambulance) now** — don't wait for an "
                     "app. If you can, show the responders your Emergency card.", source="Safety", urgent=True,
                     actions=[("Open Emergency card", "Emergency card")])
    if TREATMENT_ADVICE.search(q):
        meds = records.list_medications(user_id, profile_id, "active")
        named = [m for m in meds if m["name"].split()[0].lower() in q]
        text = ("I can't advise on starting, stopping or changing a medicine — please ask your doctor or pharmacist; "
                "changing medicines on your own can be harmful.")
        if named:
            m = named[0]
            text += (f"\n\nWhat your prescription says: **{m['name']} {m['dosage'] or ''}** — "
                     f"{m['frequency'] or 'frequency not recorded'}"
                     f"{(', ' + m['instructions']) if m['instructions'] else ''}.")
        return Reply(text, source="Safety", records=[{"id": named[0]["record_id"], "title": named[0]["record_title"] or
                                                       "Prescription", "date": named[0]["prescribed_on"],
                                                       "type": "Prescription"}] if named and named[0]["record_id"] else [])

    if re.fullmatch(r"\s*(hi|hello|hey|hii+|namaste|good (morning|afternoon|evening))[\s!.]*", q):
        return Reply(f"Hello! 😊 I'm **Medi**, your Thought Medione helper. I'm looking at **{profile_name}**'s records. "
                     "What would you like to know?", suggestions=GREETING_SUGGESTIONS)
    if _has(q, r"\b(thanks|thank you|thx|great|awesome)\b") and len(q) < 30:
        return Reply("You're welcome! Anything else I can help with? 🙂", suggestions=GREETING_SUGGESTIONS[:3])
    if _has(q, r"\b(who are you|what can you do|help me|how can you help)\b") or q.strip() in {"help", "?"}:
        return Reply("I can:\n- tell you about upcoming **appointments**, **medicines**, **allergies** and **reminders**\n"
                     "- find records — e.g. *“latest blood test”*, *“prescriptions from last year”*\n"
                     "- show your latest **lab results** and **readings**\n- explain medical words like *HbA1c* or *BD*\n"
                     "- answer questions about using the app\n\nI don't give medical advice — for that, please ask "
                     "your doctor.", suggestions=GREETING_SUGGESTIONS)

    # 2 ── navigation
    m = re.search(r"\b(open|go to|take me to|show me the|navigate to)\s+(the\s+)?([a-z &]+?)\s*(page|screen|tab)?\s*$", q)
    if m:
        target = next((p for p in PAGES if p.lower() in m.group(3) or m.group(3).strip() in p.lower()), None)
        if target and len(m.group(3).strip()) > 2:
            return Reply(f"Sure — here's **{target}**.", actions=[(f"Open {target}", target)])

    # 3 ── the user's own information
    if _has(q, r"appointment", r"\bnext (visit|consult)", r"when (do|should) i (see|visit|meet)"):
        appts = appointments.list_appointments(user_id, profile_id)
        up = appts["upcoming"]
        if not up:
            text = f"There are no upcoming appointments for {profile_name}."
            if appts["needs_update"]:
                text += f" ({len(appts['needs_update'])} past appointment(s) still need an update.)"
            return Reply(text, source="Your records", actions=[("Book an appointment", "Appointments")])
        lines = [f"- **{_fmt(a['starts_on'])}**{(' at ' + a['time_of_day']) if a['time_of_day'] else ''} — "
                 f"{a['purpose']}{(' with ' + a['doctor_name']) if a['doctor_name'] else ''}"
                 f"{(' (' + a['facility_name'] + ')') if a['facility_name'] else ''}" for a in up[:4]]
        first = up[0]
        when = "today" if first["days_away"] == 0 else "tomorrow" if first["days_away"] == 1 else f"in {first['days_away']} days"
        return Reply(f"Your next appointment is **{when}**:\n" + "\n".join(lines) +
                     "\n\nTip: download the *visit sheet* from Appointments before you go.",
                     source="Your records", actions=[("Open Appointments", "Appointments")])

    if _has(q, r"\b(medicine|medicines|medication|meds|tablets?|pills?|drugs?)\b") and \
            not _has(q, r"\b(find|search|prescriptions? from)\b"):
        meds = records.list_medications(user_id, profile_id, "active")
        if not meds:
            return Reply(f"No current medicines are recorded for {profile_name}.", source="Your records",
                         actions=[("Add a prescription", "Add record")])
        lines = [f"- **{m['name']}** {m['dosage'] or ''} — {m['frequency'] or 'frequency not recorded'}"
                 f"{(' · ' + m['instructions']) if m['instructions'] else ''}"
                 f"{' ⚠️ *needs checking*' if m['uncertain'] else ''}" for m in meds]
        return Reply("Current medicines, **as written on the prescriptions**:\n" + "\n".join(lines) +
                     "\n\nNever change a dose without asking your doctor.", source="Your records",
                     actions=[("Open Medicines", "Medicines")])

    if _has(q, r"allerg"):
        s = summary.build_summary(user_id, profile_id)
        if not s["allergies"]:
            return Reply(f"No allergies are recorded for {profile_name}. That doesn't confirm there are none — add any "
                         "you know about.", source="Your records", actions=[("Add an allergy", "Add record")])
        lines = [f"- **{r['details'].get('allergen') or r['title']}**"
                 f"{(' — ' + r['details']['reaction']) if r['details'].get('reaction') else ''}" for r in s["allergies"]]
        return Reply("Recorded allergies:\n" + "\n".join(lines), source="Your records",
                     records=[_rec(r) for r in s["allergies"]][:3])

    if _has(q, r"blood (group|type)"):
        from medione.services.profiles import get_profile
        bg = get_profile(user_id, profile_id)["blood_group"]
        return Reply(f"{profile_name}'s blood group is **{bg}**." if bg else
                     "No blood group is recorded yet. You can add it under Family → Edit details.",
                     source="Your records", actions=[] if bg else [("Edit details", "Family")])

    if _has(q, r"\b(conditions?|diagnos\w+|illness|disease)\b") and not _has(q, r"\bwhat is\b"):
        s = summary.build_summary(user_id, profile_id)
        if not s["diagnoses"]:
            return Reply("No diagnoses documented by a doctor are recorded.", source="Your records")
        lines = [f"- **{r['condition'] or r['title']}** — documented {_fmt(r['record_date'])}"
                 f"{(' by ' + r['doctor_name']) if r.get('doctor_name') else ''}"
                 f" ({r['details'].get('diagnosis_status') or 'status not recorded'})" for r in s["diagnoses"]]
        return Reply("Diagnoses documented in your records:\n" + "\n".join(lines), source="Your records",
                     records=[_rec(r) for r in s["diagnoses"]][:3])

    if _has(q, r"\b(pending|to ?do|needs? (my )?attention|anything due|due today|reminders? (today|for today))\b",
            r"what (do i have|is due|'s due).*today"):
        d = dashboard.build(user_id, profile_id)
        parts = []
        if d["due_today"]:
            parts.append("**Due today:**\n" + "\n".join(f"- {r['title']}{' (overdue)' if r['overdue'] else ''}"
                                                         for r in d["due_today"]))
        if d["todos"]:
            parts.append("**Pending for you:**\n" + "\n".join(f"- {t['title']}" for t in d["todos"][:6]))
        return Reply("\n\n".join(parts) if parts else "Nothing is due and nothing is pending. 🎉",
                     source="Your records", actions=[("Open Dashboard", "Dashboard")])

    vital_words = {"bp": r"\b(bp|blood pressure)\b", "sugar": r"\b(sugar|glucose) (reading|level|log)|my sugar",
                   "pulse": r"\b(pulse|heart rate)\b", "spo2": r"\b(spo2|oxygen)\b", "temp": r"\b(temperature|fever)\b",
                   "weight": r"\bweight\b"}
    for kind, pat in vital_words.items():
        if re.search(pat, q) and not _has(q, r"\bwhat (is|does)\b"):
            rows = health.list_vitals(user_id, profile_id, kind)
            if not rows:
                return Reply("No readings of that kind are logged yet.", source="Your records",
                             actions=[("Log a reading", "Vitals")])
            last = rows[-1]
            text = f"Latest: **{health.format_vital(last)}** on {_fmt(last['measured_on'])}."
            if len(rows) > 1:
                text += f" Previous: {health.format_vital(rows[-2])} on {_fmt(rows[-2]['measured_on'])}."
            recent = rows[-10:]
            flagged = sum(1 for r in recent if r["flag"])
            if flagged:
                text += f"\n\n{flagged} of the last {len(recent)} readings were outside the general adult range — " \
                        "worth mentioning to your doctor."
            return Reply(text, source="Your records", actions=[("Open Vitals", "Vitals")])

    labs = records.list_lab_results(user_id, profile_id)
    tests = sorted({l["test_name"] for l in labs}, key=len, reverse=True)
    test = next((t for t in tests if re.search(rf"\b{re.escape(t.lower())}\b", q)), None)
    if test and not _has(q, r"\bwhat (is|does)|meaning|mean\b"):
        trend = next(t for t in search.lab_trends([l for l in labs if l["test_name"] == test]))
        rows = trend["results"]
        last = rows[-1]
        text = (f"**{test}**: latest **{last['value_text'] or last['value_num']} {last['unit'] or ''}** on "
                f"{_fmt(last['record_date'])}")
        rng = last.get("ref_text") or (f"{last['ref_low'] or ''}–{last['ref_high'] or ''}"
                                       if last.get("ref_low") is not None or last.get("ref_high") is not None else "")
        if rng:
            text += f" (report's range: {rng})"
        text += "."
        if len(rows) > 1:
            prev = rows[-2]
            if trend["comparable"]:
                diff = last["value_num"] - prev["value_num"]
                text += f" Previous: {prev['value_text'] or prev['value_num']} on {_fmt(prev['record_date'])} " \
                        f"({'+' if diff > 0 else ''}{diff:g} {last['unit'] or ''})."
            elif trend["reason"]:
                text += f" {trend['reason']}"
        text += "\n\nThis is a description of the numbers, not an interpretation — your doctor can explain what " \
                "they mean for you."
        return Reply(text, source="Your records", actions=[("Open Lab results", "Lab results")],
                     records=[{"id": last["record_id"], "title": last["record_title"], "date": last["record_date"],
                               "type": "Lab report"}])

    if _has(q, r"\b(summary|summari[sz]e|overview|my history|medical history)\b"):
        s = summary.build_summary(user_id, profile_id)
        text = (f"{profile_name}'s records: **{s['record_count']} records**, "
                f"{len(s['diagnoses'])} documented diagnosis(es), {len(s['active_medications'])} current medicine(s), "
                f"{len(s['allergies'])} allergy record(s), {len(s['surgeries'])} surgery/procedure record(s).\n\n"
                "Open **Health summary** on the Dashboard to preview and download a one-page summary for your doctor.")
        return Reply(text, source="Your records", actions=[("Open Dashboard", "Dashboard")],
                     suggestions=["Summarise my history with AI"] if ai_ready else [])

    # 4 ── explain a word (before search so "what is an MRI" isn't a search)
    m = re.search(r"\b(?:what is|what's|whats|what are|what does|meaning of|define|explain|full form of)\s+(?:an?\s+|the\s+)?"
                  r"([a-z0-9 \-./]+?)(?:\s+mean|\s+stand for)?[\s?.!]*$", q)
    if m:
        term = m.group(1).strip()
        key = next((k for k in sorted(GLOSSARY, key=len, reverse=True) if re.search(rf"(^|\b){re.escape(k)}(\b|$)", term)), None)
        if key:
            return Reply(GLOSSARY[key] + "\n\n*General information — ask your doctor what it means for you.*",
                         source="Medical glossary")
        if ai_ready:
            return _ai(user_id, profile_id, question, history, profile_name)

    faq = _faq(q)
    if faq and _has(q, r"\bhow (do|can|to|does)\b", r"\bcan i\b", r"\bwhere (can|do) i\b", r"\bis (my|it)\b"):
        return faq

    # 5 ── find records
    is_search = _has(q, r"\b(find|search|show|look for|where (is|are)|get|list|latest|last|recent)\b")
    f, results = nlsearch.run(user_id, profile_id, question)
    if is_search or f["types"] or f["doctor_id"] or f["facility_id"] or f["test"] or f["date_from"]:
        if results:
            note = "Looked for: " + "; ".join(f["explain"]) + "." if f["explain"] else ""
            if f.get("relaxed"):
                note += " (Some of your words didn't match, so I searched without them.)"
            return Reply(f"I found **{len(results)}** record(s). {note}", source="Your records",
                         records=[_rec(r) for r in results[:6]],
                         actions=[("See all in Records", "Records")] if len(results) > 6 else [])
        return Reply("I couldn't find a matching record — nothing is stored that fits. " +
                     ("Looked for: " + "; ".join(f["explain"]) + ". " if f["explain"] else "") +
                     "Try fewer words, or check the Records page.", source="Your records",
                     actions=[("Open Records", "Records")])

    # 6 ── how-to questions
    if faq:
        return faq
    if ai_ready:
        return _ai(user_id, profile_id, question, history, profile_name)
    return Reply("Sorry, I didn't catch that. I can answer questions about your appointments, medicines, reports and "
                 "how to use the app. Try one of these:", suggestions=GREETING_SUGGESTIONS)


def _faq(q: str) -> Optional[Reply]:
    best, score = None, 0
    for keys, ans, page in FAQ:
        s = sum(1 for k in keys if re.search(rf"\b{re.escape(k)}", q))
        if s > score:
            best, score = (ans, page), s
    return Reply(best[0], actions=[(f"Open {best[1]}", best[1])]) if best else None


def _ai(user_id: int, profile_id: int, question: str, history: Optional[list[dict]], profile_name: str) -> Reply:
    from medione.ai import tasks as ai_tasks
    from medione.ai.client import AIError, AIUnavailable
    s = summary.build_summary(user_id, profile_id)
    compact = {k: s[k] for k in ("profile", "allergies", "diagnoses", "active_medications", "surgeries", "admissions",
                                 "vaccinations", "latest_lab_values", "recent_tests")}
    compact["active_concerns"] = [{"title": c["title"], "severity": SEVERITY[c["severity"]], "since": c["started_on"]}
                                  for c in health.list_concerns(user_id, profile_id, "active")]
    try:
        out = ai_tasks.chat_answer(question, history or [], json.dumps(compact, default=str), FAQ_TEXT)
    except (AIError, AIUnavailable) as exc:
        return Reply(f"I couldn't reach the AI service right now ({exc}). I can still help with your appointments, "
                     "medicines, reports and app questions.", suggestions=GREETING_SUGGESTIONS[:3])
    text = out["answer"]
    if out.get("see_doctor_note"):
        text += f"\n\n*{out['see_doctor_note']}*"
    return Reply(text, source="AI (Claude) — may contain mistakes")


def ai_history_overview(user_id: int, profile_id: int) -> Reply:
    from medione.ai import tasks as ai_tasks
    from medione.ai.client import AIError, AIUnavailable
    try:
        out = ai_tasks.summarise_history(summary.build_summary(user_id, profile_id))
    except (AIError, AIUnavailable) as exc:
        return Reply(f"The AI overview isn't available right now: {exc}")
    body = out["overview"]
    for title, key in (("Key points", "key_points"), ("Missing, conflicting or unreviewed", "gaps_or_conflicts"),
                       ("Questions you could ask your doctor", "questions_for_doctor")):
        if out[key]:
            body += f"\n\n**{title}**\n" + "\n".join(f"- {p}" for p in out[key])
    return Reply(body, source="AI (Claude) — may contain mistakes, check against your records")
