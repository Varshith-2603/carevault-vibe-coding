# Thought Medione

A personal health records app for individuals and families. Upload prescriptions, lab reports, scans and discharge
summaries; keep them organised on a timeline; set reminders; and share selected records with a doctor through a
secure, expiring link. Optional AI (Claude) reads documents and explains them in plain language, and you review
everything it produces before it is saved.

Built with Python, Streamlit and SQLite. Original files are stored encrypted.

> **Status:** working product foundation, tested locally. It is **not yet production-ready for real patient data**.
> Read [Before going live](#before-going-live) first.

---

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501 and either create an account or click **Explore with sample data**. You land on the
**Dashboard**. The sample account has four family profiles (Ananya, her husband Vikram, father Ravi and son Aarav), and
is entirely fictional and is created on first use. You can also create it from the command line:

```bash
python -m medione.seed      # demo@thoughtmedione.example / Sample-Health-2026
```

## Features

**Dashboard (first screen after sign-in).** It shows:

- **At-a-glance facts:** blood group, allergies and conditions.
- **Quick actions:** upload a record, book an appointment, log a symptom, log a reading, open the emergency card.
- **Upcoming appointments,** each with a one-page *visit sheet* to take along.
- **Pending for you:** AI readings to check, possible duplicates, past appointments to update, follow-up dates
  written in records with no appointment booked, vaccines due, medicine courses ending, and insurance about to lapse.
- **Health watch:** active symptoms with their trend, home readings outside general ranges, and lab values outside
  the report's own range.
- **Today:** reminders due today, latest readings with mini-trends, current medicines and recent records.

### Everyday problems this solves

| Real-world problem | How Thought Medione helps |
|---|---|
| Paper prescriptions and reports get lost; tests are repeated | Encrypted originals, search by anything, timeline |
| Forgetting what to ask in a 5-minute consultation | Questions saved on the appointment plus a printable **visit sheet** (questions, symptoms, medicines, readings, results) |
| "Since when? Is it getting worse?" is hard to answer | **Symptom diary** with severity over time and a worse/better trend |
| Doctors can't see BP/sugar between visits | **Vitals** log with charts. Readings outside general adult ranges are highlighted. |
| In an emergency nobody knows allergies, blood group or medicines | **Emergency card** with a QR code that shows only those facts. It can be turned off at any time, and every scan is logged. |
| Missed follow-ups and vaccine doses | Follow-up and next-dose dates written in records surface on the dashboard |
| Insurance lapses; claim papers scattered | Policy and bill record types, an expiry nudge, and claim status per bill |
| Managing parents' and children's care | Separate family profiles, each with its own dashboard |

### All features

| Area | What it does |
|---|---|
| Appointments | Book a visit (doctor, place, type, time). Add questions and preparation notes, and download a calendar invite and the visit sheet. Afterwards, mark it completed, missed or cancelled and note the outcome. |
| Symptoms & concerns | Track what's bothering you, log severity over time, and mark it resolved. Emergency warning signs to call 112 for are always shown. |
| Vitals | Blood pressure, sugar (fasting, after a meal or random), pulse, SpO₂, temperature and weight. Charts include general reference bands, and readings are checked for obvious typos. |
| Emergency card | A wallet card (printable HTML) plus an optional online version behind a QR code. It shows only blood group, allergies, conditions, current medicines and the emergency contact. |
| Accounts | Email and password sign-in. Repeated wrong passwords lock the account temporarily. Sign-up shows a one-time **recovery code** for resetting the password (there's no email service). Sessions end after 30 minutes idle. |
| Family profiles | Separate records, reminders and share links per person. Adding someone requires confirming you're authorised to manage their records. |
| Records | 16 record types: consultations, admissions and discharge summaries, prescriptions, lab, imaging, ECG and other reports, diagnoses, surgeries, procedures, vaccinations, allergies, family history, referrals, certificates and other documents. Each type has its own fields. |
| Provenance | Every record shows where it came from: *Entered by you*, *AI-extracted, not yet reviewed*, or *AI-extracted, reviewed by you*. *Verified by a clinician* is reserved for a future provider integration and can't be set by patients. |
| Documents | PDF, JPG, PNG and WEBP up to 15 MB. The real file type is checked, not just the extension. Files are encrypted at rest and never modified. Text in PDFs is extracted locally for search. Uploading the exact same file twice is detected. |
| Prescriptions | Medicines are stored exactly as written (dose, frequency, duration, instructions). Unclear items are flagged *Needs checking* until you confirm them. The app never changes or suggests treatment. |
| Timeline | All records in date order, plus follow-up dates written in records. Each entry opens the full record and its files. |
| Search | Every word you type must match somewhere in the record: fields, doctor, facility, medicines, tests, or text inside the PDF. You can also filter by type, dates, doctor, facility, condition, medicine, test and source, and export the results to CSV. With AI on, you can ask in your own words; results always come from your real records. |
| Duplicates | Records with the same type, same date and a near-identical title are flagged for you to review. Nothing is deleted automatically. |
| Lab results | Values for the same test are compared over time with a chart, but only when every report uses the same unit. The reference range shown is the one printed on each report. |
| Doctors and facilities | A directory linked to records. Nothing about a doctor (specialty, credentials) is looked up or invented. |
| Reminders | Reminders for medicines, follow-ups, tests, check-ups and vaccinations, either one-off or repeating. They show in the app and can be downloaded as a calendar file (`.ics`) for phone notifications. The app never works out dosing times itself; you choose them. |
| Sharing | Off by default. You choose the records, who the link is for, and how long it lasts (1 hour to 30 days). You can turn a link off at any time, and every visit is logged. Recipients see only the selected records, plus an optional summary limited to those records. |
| Health summary | A one-page HTML summary of allergies, medicines, diagnoses, procedures, tests and vaccinations, built **without AI**. |
| **Medi** (help chatbot) | An animated robot in the bottom-right corner of every page ("May I help you?"). Tap it to ask about appointments, medicines, allergies, lab results, readings and what's pending, to find records in plain words, to explain medical terms and prescription short forms (BD, OD, SOS…), or to ask how to use the app. It answers from your own records and a built-in guide **without AI**. Emergency words always get the emergency numbers first, and it never advises on changing medicines. With AI switched on it can also answer open questions and write a history overview. |
| **Automatic reminders from prescriptions** | Upload a prescription and the medicines are read straight away (AI for photos and handwriting; typed PDFs are read without AI). After you check and save, medicine reminders are created from what's written (1-0-1, BD, TDS, OD after dinner, HS, weekly, every 8 h…) and run until the course ends. The follow-up appointment is added from a written date or from "review after 2 weeks", with a reminder the day before. Medicines marked SOS or "when needed", unclear entries and finished courses are skipped, with the reason shown. You can switch this off before saving, or trigger it later from the record page. |
| Plain-language search | *"latest blood test"*, *"prescriptions from last year"*, *"MRI from March"*, *"records from Dr. Iyer"* — understood without AI (Records → *Ask in your own words*). It says clearly when nothing matches. |
| Ask about a document | With AI on: ask your own question about an uploaded report. Answers keep **what the document says** separate from general information. |
| Change history | Every edit to a record is kept with before/after values, so verified details are never silently lost. |
| Your data | Download everything (data plus original files) as a ZIP, view the activity log, or delete the account and all its data. |

## Configuration

All settings come from environment variables; none are stored in the code.

| Variable | Default | Purpose |
|---|---|---|
| `MEDIONE_ENV` | `development` | Set `production` to require an encryption key and disable the demo account |
| `MEDIONE_ENCRYPTION_KEY` | generated in `instance/secret.key` | Fernet key for documents. **Required in production.** Generate one with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Losing it makes stored files unreadable. |
| `MEDIONE_DATA_DIR` | `./instance` | Database and encrypted files |
| `MEDIONE_BASE_URL` | `http://localhost:8501` | Used to build share links (set to your public `https://` address) |
| `MEDIONE_ENABLE_DEMO` | on in development | Shows the **Explore with sample data** button |
| `MEDIONE_SESSION_TIMEOUT_MIN` | `30` | Idle sign-out |
| `MEDIONE_MAX_UPLOAD_MB` | `15` | Upload limit (keep `server.maxUploadSize` in `.streamlit/config.toml` in step) |
| `MEDIONE_PBKDF2_ITERATIONS` | `600000` | Password hashing cost |
| `ANTHROPIC_API_KEY` | not set | Turns on AI features (or use `ant auth login` plus `MEDIONE_AI_ENABLED=1`) |
| `MEDIONE_AI_MODEL` | `claude-opus-5-5` | Claude model used for AI features |

`instance/` holds the database, documents and key. It is in `.gitignore`. **Never commit it.**

## AI features

- **When it's on:** only when the server has Anthropic credentials *and* the signed-in user has accepted the
  consent notice (Settings → AI features). Consent can be withdrawn at any time.
- **What gets sent:** only the active profile's records or the one document being processed, and only when the user
  presses an AI button.
- **Safety rules:** these are enforced in the system prompt (`medione/ai/client.py`). The AI must not invent missing
  values, must flag unclear text, must copy wording as written, must not diagnose, and must not suggest starting,
  stopping or changing treatment.
- **Structured output:** responses are constrained JSON, so extractions open in an editable form for review rather
  than being saved directly.
- **Refusals:** the requests opt into Anthropic's server-side refusal fallback (`fallbacks: "default"`). If a request
  is still refused, the user gets a clear error.
- **Without AI:** everything else works without AI. Without it, users type in the details, helped by the text
  extracted locally from PDFs.

## Security model

- **Access control:** every data function takes the signed-in user's id and checks ownership in SQL. The UI can't
  reach another account's or another profile's data by passing a different id. Tests cover this.
- **Passwords:** PBKDF2-SHA256 (600k iterations) with a random salt. Recovery codes are hashed the same way and can
  only be used once.
- **Share links:** 256-bit random tokens. Only their SHA-256 hash is stored. Each visit re-checks expiry,
  revocation and record ownership.
- **Uploads:** files are checked for size and magic bytes, then encrypted with Fernet and saved under random names.
  File names are sanitised.
- **Audit log:** records sign-ins, failures, lockouts, record changes, document opens, and share creation, visits
  and revocation. It never stores passwords, tokens or medical content.
- **Streamlit:** XSRF protection is on (it was off in the old demo). Error details are hidden from users and usage
  statistics are off.

## Tests

```bash
pip install pytest
python -m pytest tests -q
```

The 102 tests cover:

- Authentication, lockout and recovery.
- Isolation between users and between family profiles.
- Share-link scope, expiry and revocation.
- Upload validation, encryption at rest and duplicate detection.
- Search, the timeline, duplicates and lab trends.
- Reminder scheduling and the calendar export.
- Appointments, the symptom diary, vital-sign flags and validation, the emergency card's scope and revocation, and
  the dashboard to-do logic.
- The AI wrapper, using a fake client.
- Headless runs of the real Streamlit app: every page, sign-up, record creation, profile switching, review, and the
  public share view.

## Before going live

These are **not done**. Each one needs a decision or a human review.

1. **Hosting and HTTPS.**
   - Run behind a TLS-terminating reverse proxy.
   - Set `MEDIONE_ENV=production`, `MEDIONE_BASE_URL` and `MEDIONE_ENCRYPTION_KEY` (stored in a secrets manager).
   - Restrict who can reach the server.
2. **Database encryption and backups.**
   - Documents are encrypted, but the SQLite database (record text) is not. Use an encrypted disk/volume or SQLCipher.
   - Set up encrypted, tested backups of `instance/` and a separate backup of the key.
   - For multiple servers or larger scale, move to PostgreSQL.
3. **Sessions.** A Streamlit session ends when the page is refreshed, so users sign in again. That is safe, but a
   cookie-based session layer would make it more convenient.
4. **Account recovery.** Recovery codes only. Adding email verification and email/OTP recovery needs an email or SMS
   provider.
5. **Rate limiting.** Lockout is per account. Add IP-level rate limiting at the proxy.
6. **India: DPDP Act, 2023 and DPDP Rules, 2025.** A legal review is needed before real users. The rules come into
   force in phases, so confirm the current dates. Items to cover:
   - Consent notice wording and record-keeping.
   - A grievance officer and a contact process.
   - Erasure and correction (built in) and data retention periods.
   - A breach-notification procedure.
   - Verifiable parental consent for children's profiles.
   - Cross-border transfer when AI is used (the Claude API may process data outside India).
   - Anthropic's data-processing terms.
   - ABDM/ABHA requirements if you integrate with India's digital health stack later.

   **This app does not claim regulatory compliance.**
7. **Security review.** Have an independent penetration test and code review done before handling real health data.
8. **Medical and clinical review.** Have a clinician review AI prompts, labels and disclaimers.

## Project structure

```
app.py                    Entry point: share-link route, sign-in gate, sidebar, page router
medione/
  config.py               Environment-based settings
  db.py                   SQLite schema (additive changes only)
  security.py             Password hashing, tokens, document encryption
  auth.py                 Accounts, lockout, recovery, consent, account deletion
  audit.py                Activity log
  models.py               Record types, categories, provenance labels
  seed.py                 Fictional sample account (+ tiny PDF generator)
  services/               Ownership-checked data services
    access.py profiles.py directory.py records.py documents.py search.py
    summary.py reminders.py sharing.py exports.py
    appointments.py health.py emergency.py dashboard.py visit_prep.py
  ai/client.py            Claude wrapper with safety rules and structured output
  ai/tasks.py             Extraction, summaries, explanations, search-to-filters
  services/helpbot.py     Medi's answers (records, FAQ, glossary, safety rules)
  services/nlsearch.py    Plain-language search without AI
  ui/                     Streamlit screens (ui/pages/*), Medi chatbot (ui/chatbot.py), widgets, theme
tests/                    pytest suites
legacy_carevault/         The previous CareVault demo, archived unchanged
```

## Medical disclaimer

Thought Medione stores and organises health information. It does not provide medical advice, diagnosis or treatment,
and it is not connected to any hospital system. In an emergency call **112** (India).
