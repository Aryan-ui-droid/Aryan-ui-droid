# Academic Result Intelligence Dashboard

AIRAS is a Python and Streamlit based academic result analysis system. It helps faculty upload semester result workbooks, analyze class and subject performance, identify toppers and at-risk students, inspect student-level records, and export structured reports.

## Features

- Faculty login and account creation backed by SQLite
- In-session password change for signed-in users
- Upload and analyze `.xlsx` semester result files
- Auto-detect workbook sheet structure, subject blocks, SGPA, grade, and term labels
- Multi-term support for sheets containing `Term`, `Sem`, or `Semester` sections
- Dashboard tabs for Overview, Subject Intelligence, Grade Sheet, Student Explorer, History, and Reporting
- Export options for CSV, TXT, ZIP bundle, and formatted Excel reports
- Session persistence for uploaded files and user activity history
- Automatic exclusion of blank or invalid student rows from analysis

## Tech Stack

- Python 3.13.5
- Streamlit 1.54.0
- pandas 2.3.3
- openpyxl 3.1.5
- SQLite

## Project Structure

```text
airas/
|-- .streamlit/
|   `-- config.toml
|-- app.py
|-- dashboard.py
|-- report_generator.py
|-- result_engine.py
|-- requirements.txt
|-- render.yaml
|-- data/
|   |-- DS Result.xlsx
|   `-- email_settings.example.json
|-- assets/
|   |-- login image.jpg
|   `-- Screenshots/
`-- README.md
```

## Getting Started

Create and activate a virtual environment:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run the dashboard:

```powershell
python -m streamlit run dashboard.py
```

Streamlit will usually open:

```text
http://127.0.0.1:8501
```

## Usage

1. Create a faculty account from the login screen.
2. Upload an Excel workbook in `.xlsx` format.
3. Select the workbook sheet from the sidebar.
4. Review or edit the detected academic profile.
5. Explore analytics and download exports.

## Render Deployment

This repository includes a ready-to-use `render.yaml` blueprint.

The blueprint configures:

- Python web service named `airas`
- Free Render plan
- External PostgreSQL database through `DATABASE_URL`
- Streamlit start command:

```bash
streamlit run dashboard.py --server.port $PORT --server.address 0.0.0.0
```

Deploy steps:

1. Push this repository to GitHub.
2. In Render, create a new Blueprint service from the GitHub repository.
3. Let Render read `render.yaml`.
4. Wait for the first build and open the generated app URL.
5. In Render Environment, set `DATABASE_URL` to your Neon PostgreSQL connection string.
6. Create the first faculty account in the hosted app.

Important: on Render Free, do not rely on local SQLite files for hosted accounts. Use an external PostgreSQL database such as Neon so user accounts, login sessions, upload history, and stored workbook bytes survive restarts and redeploys.

## Environment

When `DATABASE_URL` is set, the app stores runtime data in PostgreSQL. Without `DATABASE_URL`, it stores its local SQLite database at `AIRAS_DB_PATH` when set. If both variables are missing, it falls back to:

```text
data/app.db
```

Local private/runtime files are intentionally ignored by Git:

- `data/app.db`
- `data/email_settings.json`
- `Final_Result_Report*.xlsx`
- `*.log`
- `__pycache__/`
- `venv/`

## Script-Based Report Generation

To generate a sample report without opening the dashboard:

```powershell
python app.py
```

This uses:

```text
data/DS Result.xlsx
```

## Input Workbook Expectations

The engine works best when the sheet contains:

- A student identifier column such as `Roll No` or `PRN`
- A student name column
- An `SGPA` or `GPA` column
- Subject blocks with result or marks fields such as `Int`, `Ext`, `Tot`, and `P/F`
- Optional term labels like `Term V`, `Sem 5`, or `Semester 5`

It can tolerate metadata rows above the actual header, multi-row headers, subject names with course codes, and workbooks containing multiple sheets.

## Main Modules

`dashboard.py` runs the Streamlit UI, login flow, upload flow, dashboard pages, history, theme handling, and export actions.

`result_engine.py` loads Excel sheets, detects headers and terms, computes class metrics, builds subject analysis, grade summaries, toppers, and student-level reports.

`report_generator.py` builds formatted Excel reports with summary, subject analysis, interpretation, grade sheet, class toppers, and student matrix sheets.

`app.py` is a small script example for generating a report directly from Python.
