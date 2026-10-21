# CareVault — Personal Health Record (PHR) Dashboard

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.35%2B-red.svg)](https://streamlit.io/)
[![Plotly](https://img.shields.io/badge/Plotly-5.18%2B-teal.svg)](https://plotly.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A **Personal Health Record (PHR) demo application** built with Python, Streamlit, Pandas, and Plotly. Designed with the aesthetics and rigor of an enterprise healthcare SaaS platform, CareVault provides patients with a centralized, unified portal to track clinical encounters, diagnostic reports, medication regimens, and health vitals.

---

## 🌟 Key Features

### Pages
* **Dashboard** – greeting, five summary cards that open the matching page, next appointments, an interactive vitals chart, the Emergency Medical ID, and a recent-activity feed built from real record dates.
* **Appointments** – upcoming / past / cancelled views; add, edit, mark completed, cancel (with confirmation) and download a calendar invite (`.ics`).
* **Hospital Visits** – combined filters (hospital, department, doctor, status, date range, search), list or sortable table view, CSV export, full visit details with linked records.
* **Scans & Diagnostics** – report library filtered by imaging / laboratory / other, status, facility, doctor and test. The report viewer flags reports that are not final, shows a placeholder when no file is attached, and accepts a PDF or image upload.
* **Prescriptions & Medicines** – active prescriptions and medication history kept separate; log a collected refill (record-only, no pharmacy contact).
* **Health Vitals** – heart rate, blood pressure, weight and SpO₂ trends with period selection, latest vs previous reading, and optional general reference bands. Readings dated in the future are flagged and kept out of charts.
* **All Records** – one searchable, filterable library of every record type, with CSV export and a printable health summary.
* **Settings** – profile and emergency details (with validation), in-app alert preferences, full JSON export, and reset of demo data.
* **Help & Support** – quick guide, FAQ and emergency numbers.

### Working with records
* Every record type can be **added, viewed, edited and deleted** from one schema-driven form with inline validation, a duplicate warning, and protection against double submission.
* Deleting always asks for confirmation. Deleting a visit keeps the records linked to it and only removes the link.
* Reports, prescriptions, past medicines and appointments can be **linked to the hospital visit** they came from, and each linked record can be opened from the other.
* Missing information shows as *Not recorded* or *Not provided*. Nothing is filled in with invented values.
* Global search (top of every page) matches every word you type across hospitals, doctors, departments, reasons, tests, medicines, appointments and dates (for example `Oct 2026`).

## ⚠️ Demo limitations
* All data is fictional and lives only in memory for the current browser session. Reloading the page resets it.
* There is no login, encryption or backend. Don't enter real medical information.
* CareVault records information. It does not interpret results, give medical advice or contact clinics and pharmacies.

## 🎨 Design system
Theme colours, radius and font are set in `.streamlit/config.toml`. Components are styled in `assets/styles.css` through Streamlit's stable `st-key-*` container classes. Reusable UI pieces live in `components/ui.py`, and record types are described once in `utils/records.py`.

## 📁 Project Structure

```
app.py                      # Page router; draws one dialog per run
components/
  ui.py                     # Design-system primitives (cards, badges, rows, notices)
  state.py                  # Navigation / dialog / flash-message state helpers
  dialogs.py                # Record details, report viewer, confirmations
  forms.py                  # Schema-driven add/edit forms with validation
  filters.py                # Reusable search & filter panel
  page.py, tables.py        # List/table toolbar, table view, CSV export
  cards.py, charts.py       # Dashboard cards, record cards, Plotly charts
  header.py, sidebar.py     # Header (search, alerts, Add record) and navigation
  modals.py                 # Backward-compatible dialog entry points
pages/                      # dashboard, appointments, hospital_visits, diagnostics,
                            # prescriptions, vitals, records, settings, help_support
utils/
  records.py                # Record registry, IDs, CRUD, validation, search index
  data_loader.py            # CSV loading, session state, metrics, alerts
  filters.py, exports.py, helpers.py
data/                       # Fictional demo CSVs
tests/                      # pytest suites (logic + AppTest UI flows)
tests/browser/              # Optional Playwright E2E + responsive screenshot scripts
```

## 🧪 Tests
```bash
pip install pytest
cd tests && python -m pytest -q
```
Optional browser checks need `pip install playwright`, Google Chrome, and the app running on port 8599:
```bash
streamlit run app.py --server.port 8599
python tests/browser/e2e_flows.py <screenshot-folder>
```

---

## 🚀 Installation & Running Locally

### 1. Prerequisites
* Python 3.10 or higher installed.

### 2. Clone and Navigate
```bash
cd d:\projecttt
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the Streamlit Application
```bash
streamlit run app.py
```

The application will start and open automatically in your browser at `http://localhost:8501`.

---

## 🔮 Future Improvements
* **FHIR / HL7 Interoperability**: Support for SMART on FHIR JSON imports and exports.
* **Wearable Integration**: Direct API sync with Apple HealthKit, Google Health Connect, and Garmin.
* **AI Medical Assistant**: Local LLM summarization of clinical lab results and discharge instructions.
* **FastAPI + PostgreSQL Backend**: Migration to persistent relational storage with RBAC authentication.

---

## ⚠️ Medical Disclaimer
> **DEMO / SAMPLE APPLICATION**: All patient identities, diagnostic findings, prescriptions, and healthcare facilities shown in this dashboard are purely fictitious and generated for demonstration purposes only. This application does not provide real medical advice, diagnosis, or treatment.
