import streamlit as st
import pandas as pd
from result_engine import ResultEngine

st.set_page_config(page_title="Result Analysis Dashboard", layout="wide")

st.title("🎓 Result Analysis Dashboard")
st.subheader("CSE (Integrated) Data Science - Semester V")

# Load Data
engine = ResultEngine("data/DS Result.xlsx")
engine.load_data()

overview = engine.get_class_overview()
toppers = engine.get_class_toppers()
subject_summary = engine.get_subject_summary()
matrix = engine.get_student_matrix()

# =============================
# CLASS OVERVIEW
# =============================
st.markdown("## 📊 Class Overview")

col1, col2, col3, col4, col5 = st.columns(5)

col1.metric("Total Students", overview["total_students"])
col2.metric("Passed", overview["passed"])
col3.metric("Failed", overview["failed"])
col4.metric("Avg SGPA", overview["average_sgpa"])
col5.metric("Pass %", f"{overview['pass_percentage']}%")

st.divider()

# =============================
# CLASS TOPPERS
# =============================
st.markdown("## 🏆 Top 3 Students")
st.dataframe(toppers, use_container_width=True)

st.divider()

# =============================
# SUBJECT ANALYSIS
# =============================
st.markdown("## 📚 Subject Analysis")

subject_df = pd.DataFrame(subject_summary).T
st.dataframe(subject_df, use_container_width=True)

st.divider()

# =============================
# STUDENT MATRIX
# =============================
st.markdown("## 👨‍🎓 Student Performance Matrix")

for roll, data in matrix.items():
    with st.expander(f"{data['name']} ({roll})"):
        if data["passed_all"]:
            st.success("Passed All Subjects")
        else:
            st.error("Failed Subjects:")
            for sub in data["failed_subjects"]:
                st.write(f"- {sub}")

import os
from report_generator import ReportGenerator

st.divider()
st.markdown("## 📥 Generate Report")

if st.button("Generate Excel Report"):

    report = ReportGenerator(
        engine,
        university="MGM University, Chh. Sambhajinagar",
        department="CSE (Integrated) Data Science",
        semester="V",
        academic_year="2025-26"
    )

    output_file = "Final_Result_Report.xlsx"
    report.generate_report(output_file)

    st.success("Excel Report Generated Successfully!")

    with open(output_file, "rb") as file:
        st.download_button(
            label="Download Report",
            data=file,
            file_name=output_file,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )                