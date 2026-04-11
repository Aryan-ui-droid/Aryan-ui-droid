# 📊 Academic Result Intelligence Dashboard (AIRAS)

A **Python + Streamlit based academic result analysis system** that helps faculty and institutions analyze semester result workbooks, track performance, identify toppers, and generate structured reports.

---

## 🚀 Overview

This project simplifies academic result analysis from Excel workbooks 📁.  
It automatically detects key academic fields and presents insights through an **interactive dashboard**.

### 🎯 Key Capabilities:
- 📈 Student result analysis  
- 📊 Subject-wise pass/fail tracking  
- 🧠 SGPA-based performance insights  
- 🏆 Topper identification  
- 🔍 Student-level drill-down reports  
- 📤 Exportable Excel reports  
- 🕘 Upload history tracking  
- 🔐 Faculty login & session management  

---

## ✨ Features

- 🔐 Secure faculty login & account creation  
- 📥 Upload `.xlsx` result workbooks  
- 🤖 Automatic detection of:
  - 🆔 Roll / PRN column  
  - 👤 Student name column  
  - 📊 SGPA / GPA column  
  - 📝 Grade column  
  - 📚 Subject result blocks  
  - 🏫 Term / Semester labels  

---

## 📊 Dashboard Modules

- 📌 **Overview** – Complete class performance summary  
- 📚 **Subject Intelligence** – Subject-wise insights  
- 📄 **Grade Sheet** – Student grade distribution  
- 🔎 **Student Explorer** – Individual student analysis  
- 🕘 **History** – Uploaded file tracking  
- 📤 **Reporting** – Export reports  

---

## 📈 Analytics Features

- 📊 Subject-wise pass percentage  
- ❌ Failed subject matrix (student-wise)  
- 🏆 Topper detection  
- 📉 Performance trends  

---

## 📤 Export Options

- 📄 Excel Reports  
- 📁 CSV Files  
- 📝 TXT Files  
- 📦 ZIP Downloads  

---

## 🛠️ Tech Stack

- 🐍 Python  
- 🌐 Streamlit  
- 📊 Pandas  
- 📂 Openpyxl  
- 🗄️ SQLite  

---

## 📁 Project Structure

```text
.
├── dashboard.py              # Main Streamlit dashboard
├── result_engine.py          # Core result analysis engine
├── report_generator.py       # Excel report generation
├── app.py                    # Script-based execution entry point
├── data/
│   ├── DS Result.xlsx        # Sample input workbook
│   └── app.db                # SQLite database
├── assets/
│   └── login image.jpg       # Login page background image
├── Final_Result_Report.xlsx
├── Final_Result_Report_Term_I.xlsx
├── Final_Result_Report_Term_III.xlsx
├── Final_Result_Report_Term_IV.xlsx
├── Final_Result_Report_Term_V.xlsx
├── Final_Result_Report_Term_VII.xlsx
└── requirements.txt
