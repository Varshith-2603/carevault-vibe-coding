"""Understands everyday search requests without AI.

"Find my latest blood test report", "prescriptions from last year", "MRI from March",
"records from Dr. Iyer", "results for HbA1c" -> structured filters for search.search_records.
Results always come from the user's stored records; nothing is invented.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from typing import Optional

from medione.models import type_label
from medione.services import directory, search

TYPE_WORDS = [
    (r"blood tests?|blood reports?|lab(oratory)? (test|report|result)s?|labs?|cbc|lipid|sugar tests?|thyroid tests?|"
     r"test results?",
     ["lab_report"]),
    (r"prescriptions?|rx\b|medicine slips?", ["prescription"]),
    (r"mri|ct scan|\bct\b|x-?ray|ultrasound|sonography|scan|imaging|mammogram", ["imaging"]),
    (r"ecg|ekg|echo(cardiogram)?|tmt", ["ecg", "other_diagnostic"]),
    (r"discharge( summary)?|admission|hospital stay|hospitali[sz]ed", ["admission"]),
    (r"vaccin\w*|immuni[sz]\w*|jab|shot", ["vaccination"]),
    (r"surgery|surgeries|operation", ["surgery", "procedure"]),
    (r"procedure", ["procedure"]),
    (r"referral", ["referral"]),
    (r"certificate", ["certificate"]),
    (r"insurance|policy", ["insurance"]),
    (r"bills?|receipts?|invoice", ["bill"]),
    (r"consultations?|doctor visits?|visits?|check-?ups?", ["consultation"]),
    (r"allerg\w*", ["allergy"]),
    (r"diagnos\w*", ["diagnosis"]),
    (r"family history", ["family_history"]),
    (r"spirometry|lung function", ["other_diagnostic"]),
]
# Words that mean a particular imaging modality: kept as keywords so "MRI" doesn't match every scan
KEEP_WORDS = {"mri", "ct", "x-ray", "xray", "ultrasound", "echo", "mammogram", "spirometry"}
STOP = set("""find show me my the a an of for from in on at with all any please get open give list our his her their
records record report reports document documents file files latest last recent newest most previous old older
earliest first i want to see where is was are what which when did do have results result and or by about
during between since this that these those dr doctor hospital clinic lab""".split())
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m} | \
         {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}


def _month_range(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def parse(user_id: int, profile_id: int, text: str, today: Optional[date] = None) -> dict:
    today = today or date.today()
    q = " " + text.lower().strip() + " "
    out: dict = {"types": [], "date_from": None, "date_to": None, "doctor_id": None, "facility_id": None,
                 "test": "", "medication": "", "condition": "", "latest": False, "oldest": False, "keywords": "",
                 "explain": []}
    consumed: list[str] = []

    # names first (so "Dr. Menon" isn't read as a keyword)
    doctors = [(d, [p for p in re.findall(r"[a-z]+", d["name"].lower()) if p not in {"dr", "ms", "mr", "mrs"}])
               for d in directory.list_doctors(user_id)]
    hit = next(((d, parts) for d, parts in doctors if parts and all(re.search(rf"\b{p}\b", q) for p in parts)), None)
    if hit is None:  # a single name part (first name or surname) that identifies exactly one doctor
        partial = [(d, parts) for d, parts in doctors
                   if any(len(p) > 2 and p not in STOP and re.search(rf"\b{p}\b", q) for p in parts)]
        hit = partial[0] if len(partial) == 1 else None
    if hit:
        d, parts = hit
        out["doctor_id"] = d["id"]
        out["explain"].append(f"doctor {d['name']}")
        consumed += parts
    for f in sorted(directory.list_facilities(user_id), key=lambda f: -len(f["name"])):
        words = [w for w in re.findall(r"[a-z]+", f["name"].lower()) if len(w) > 3 and w not in STOP
                 and w not in {"multispecialty", "centre", "center", "diagnostics", "clinic", "hospital", "studio"}]
        if words and any(re.search(rf"\b{w}\b", q) for w in words):
            out["facility_id"] = f["id"]
            out["explain"].append(f"at {f['name']}")
            consumed += words
            q = q.replace(f["name"].lower(), " ")  # so "Sunrise Diagnostics" isn't read as "diagnosis"
            break

    known = search.distinct_values(user_id, profile_id)
    for t in sorted(known["tests"], key=len, reverse=True):
        if re.search(rf"\b{re.escape(t.lower())}\b", q):
            out["test"] = t
            out["explain"].append(f"test {t}")
            consumed += re.findall(r"[a-z0-9]+", t.lower())
            break
    for m in sorted(known["medications"], key=len, reverse=True):
        first = re.findall(r"[a-z]+", m.lower())[:1]
        if first and len(first[0]) > 3 and re.search(rf"\b{first[0]}\b", q):
            out["medication"] = m
            out["explain"].append(f"medicine {m}")
            consumed += first
            break
    for c in known["conditions"]:
        if re.search(rf"\b{re.escape(c.lower())}\b", q):
            out["condition"] = c
            out["explain"].append(f"condition {c}")
            consumed += re.findall(r"[a-z]+", c.lower())
            break

    for pattern, types in TYPE_WORDS:
        m = re.search(rf"\b({pattern})\b", q)
        if m:
            for t in types:
                if t not in out["types"]:
                    out["types"].append(t)
            consumed += [w for w in re.findall(r"[a-z\-]+", m.group(0)) if w not in KEEP_WORDS]
    if out["test"] and "lab_report" not in out["types"]:
        out["types"].append("lab_report")
    if out["types"]:
        out["explain"].insert(0, " / ".join(type_label(t).lower() for t in out["types"][:3]))

    if re.search(r"\b(latest|last|most recent|newest|recent)\b", q) and not re.search(r"\blast (year|month|week|\d+)", q):
        out["latest"] = True
    if re.search(r"\b(oldest|earliest|first)\b", q):
        out["oldest"] = True

    # dates
    y = today.year
    if re.search(r"\blast year\b", q):
        out["date_from"], out["date_to"] = date(y - 1, 1, 1), date(y - 1, 12, 31)
    elif re.search(r"\bthis year\b", q):
        out["date_from"], out["date_to"] = date(y, 1, 1), today
    elif re.search(r"\blast month\b", q):
        first = today.replace(day=1) - timedelta(days=1)
        out["date_from"], out["date_to"] = _month_range(first.year, first.month)
    elif re.search(r"\bthis month\b", q):
        out["date_from"], out["date_to"] = today.replace(day=1), today
    else:
        m = re.search(r"\b(?:last|past)\s+(\d+)\s+(day|week|month|year)s?\b", q)
        if m:
            n, unit = int(m.group(1)), m.group(2)
            days = {"day": 1, "week": 7, "month": 30, "year": 365}[unit] * n
            out["date_from"], out["date_to"] = today - timedelta(days=days), today
    if out["date_from"] is None:
        month = next((MONTHS[w] for w in re.findall(r"[a-z]+", q) if w in MONTHS and len(w) >= 3 and w != "may"
                      or (w == "may" and re.search(r"\b(in|from|of|during) may\b", q))), None)
        year_m = re.search(r"\b(19|20)\d{2}\b", q)
        if month and year_m:
            out["date_from"], out["date_to"] = _month_range(int(year_m.group(0)), month)
        elif month:
            yr = y if month <= today.month else y - 1
            out["date_from"], out["date_to"] = _month_range(yr, month)
        elif year_m:
            yr = int(year_m.group(0))
            out["date_from"], out["date_to"] = date(yr, 1, 1), date(yr, 12, 31)
    if out["date_from"]:
        out["explain"].append(f"{out['date_from'].strftime('%d %b %Y')} – {out['date_to'].strftime('%d %b %Y')}")

    date_words = set(MONTHS) | {"year", "month", "week", "day", "days", "weeks", "months", "years", "past", "ago"}
    words = [w for w in re.findall(r"[a-z0-9\-]+", q)
             if w not in STOP and w not in consumed and w not in date_words and not re.fullmatch(r"\d+", w)
             and len(w) > 1]
    out["keywords"] = " ".join(words)
    if out["keywords"]:
        out["explain"].append(f"words “{out['keywords']}”")
    if out["latest"]:
        out["explain"].append("most recent first")
    return out


def run(user_id: int, profile_id: int, text: str, today: Optional[date] = None) -> tuple[dict, list[dict]]:
    """Parse and search. If unknown words block every match, retry without them (and say so)."""
    f = parse(user_id, profile_id, text, today)

    def go(keywords: str) -> list[dict]:
        return search.search_records(user_id, profile_id, keywords, f["types"] or None, f["date_from"], f["date_to"],
                                     f["doctor_id"], f["facility_id"], f["condition"], f["medication"], f["test"])
    results = go(f["keywords"])
    f["relaxed"] = False
    if not results and f["keywords"] and (f["types"] or f["doctor_id"] or f["facility_id"] or f["test"]):
        results = go("")
        f["relaxed"] = bool(results)
    if f["oldest"]:
        results = list(reversed(results))
    if (f["latest"] or f["oldest"]) and results:
        results = results[:1]
    return f, results
