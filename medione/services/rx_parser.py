"""Read a typed (text) PDF prescription without AI.

Used when AI isn't switched on. It only recognises clearly printed lines such as
"1. Tab. Metformin 500 mg - once daily after dinner - 3 months". Handwriting and
photos need the AI reader. The result has the same shape as the AI extraction so the
same review screen is used, and the record is labelled "auto-read · not yet reviewed".
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

FORMS = r"(?:tab(?:let)?s?|cap(?:sule)?s?|syp|syrup|susp(?:ension)?|inj(?:ection)?|inhaler|drops?|oint(?:ment)?|gel|cream|sachet)"
DOSE = r"(\d+(?:[.,]\d+)?(?:\s*/\s*\d+(?:[.,]\d+)?)?\s*(?:mg|mcg|µg|g|ml|iu|units?|%)(?:\s*/\s*\d*\s*ml)?)"
FREQ = (r"(\b[0-2½]\s*-\s*[0-2½]\s*-\s*[0-2½](?:\s*-\s*[0-2½](?!\s*(?:\d|days?\b|weeks?\b|months?\b)))?(?![\d.])|\b(?:once|twice|thrice|one time|two times|three times|four times)"
        r"(?: a| per)? ?(?:day|daily|week|weekly)?\b|\b(?:od|bd|bid|tds|tid|qid|hs|sos|prn)\b|\bdaily\b|"
        r"\bevery \d+ ?(?:hours|hrs|h)\b|\bwhen needed\b|\bas needed\b|\bweekly\b|\d puffs? [a-z ]*?(?:daily|sos|when needed))")
DURATION = r"(\b(?:for |x |× )?\d+\s*(?:days?|weeks?|months?)\b|\blong ?term\b|\bcontinue\b)"
INSTR = (r"(\b(?:before|after|with) (?:food|meals?|breakfast|lunch|dinner)\b|\bempty stomach\b|\bat bed ?time\b|"
         r"\bin the (?:morning|evening|night)\b|\bmorning\b|\bnight\b)")
DATE_RES = [
    (r"\b(\d{4})-(\d{2})-(\d{2})\b", lambda m: date(int(m[1]), int(m[2]), int(m[3]))),
    (r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b", lambda m: date(int(m[3]), int(m[2]), int(m[1]))),
]


def _date(text: str) -> Optional[str]:
    for pattern, build in DATE_RES:
        m = re.search(pattern, text)
        if m:
            try:
                return build(m).isoformat()
            except ValueError:
                continue
    return None


def parse_text(text: str) -> Optional[dict]:
    """Return an extraction dict (same keys as the AI extractor) or None if this doesn't look like a prescription."""
    if not text or not text.strip():
        return None
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    meds = []
    for ln in lines:
        low = ln.lower()
        if not (re.search(rf"\b{FORMS}\b", low) or re.match(r"^\d+[.)]\s+\S+.*\d\s*(mg|mcg|ml|iu|g)\b", low)):
            continue
        dose = re.search(DOSE, low)
        if not dose:
            continue
        body = re.sub(r"^\d+[.)]\s*", "", ln)
        body = re.sub(rf"^{FORMS}\.?\s*", "", body, flags=re.I)
        dose_in_body = re.search(DOSE, body.lower())
        name = body[:dose_in_body.start()].strip(" -–:,.") if dose_in_body else ""
        if len(name) < 3:
            continue
        freq = re.search(FREQ, low)
        dur = re.search(DURATION, low)
        instr = re.findall(INSTR, low)
        meds.append({
            "name": name, "dosage": body[dose_in_body.start():dose_in_body.end()].strip(),
            "frequency": ln[freq.start():freq.end()].strip() if freq else None,
            "duration": re.sub(r"^(for|x|×)\s+", "", dur.group(0).strip()) if dur else None, "route": None,
            "instructions": ", ".join(dict.fromkeys(i.capitalize() for i in instr)) or None,
            "uncertain": not freq, "uncertain_reason": None if freq else "How often to take it wasn't found — check it.",
        })
    if not meds:
        return None
    joined = "\n".join(lines)
    doctor = re.search(r"\b(Dr\.?\s+[A-Z][A-Za-z.]*(?:\s+[A-Z][A-Za-z.]*){0,3})", joined)
    record_date = None
    for ln in lines:
        if re.search(r"\bdate\b", ln, re.I):
            record_date = _date(ln)
            if record_date:
                break
    record_date = record_date or _date(joined)
    follow = None
    for ln in lines:
        if re.search(r"follow[- ]?up|review|next visit", ln, re.I):
            follow = _date(ln)
            if follow:
                break
    advice = [ln for ln in lines if re.search(r"\b(advice|advised|review|follow[- ]?up|avoid|rinse|walk|diet)\b", ln, re.I)
              and not re.search(DOSE, ln.lower())]
    facility = re.sub(r"\s*-\s*prescription.*$", "", lines[0], flags=re.I).strip() if lines else None
    uncertain = ["record_date"] if not record_date else []
    return {
        "document_type": "prescription",
        "title": f"Prescription – {doctor.group(1).strip()}" if doctor else "Prescription",
        "record_date": record_date, "end_date": None, "follow_up_date": follow,
        "doctor_name": doctor.group(1).strip().rstrip(",.") if doctor else None,
        "facility_name": facility if facility and not re.search(DOSE, facility.lower()) and len(facility) < 80 else None,
        "condition": None, "summary": None,
        "extra_fields": [{"name": "doctor_instructions", "value": " ".join(advice)}] if advice else [],
        "medications": meds, "lab_results": [], "uncertain_fields": uncertain,
        "legibility_note": "Read automatically from the PDF's text (no AI). Check every medicine against the original.",
    }
