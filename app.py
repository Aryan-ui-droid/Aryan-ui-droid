from report_generator import ReportGenerator
from result_engine import ResultEngine

if __name__ == "__main__":

    file_path = "data/DS Result.xlsx"   # Make sure name matches your Excel file

    engine = ResultEngine(file_path)

    # Load Data
    engine.load_data()

    # ------------------------------------------------
    # CLASS OVERVIEW
    # ------------------------------------------------
    print("\n--- CLASS OVERVIEW ---")
    overview = engine.get_class_overview()
    for key, value in overview.items():
        print(f"{key}: {value}")

    # ------------------------------------------------
    # CLASS TOPPERS
    # ------------------------------------------------
    print("\n--- CLASS TOPPERS ---")
    toppers = engine.get_class_toppers()
    for i, row in toppers.iterrows():
     print(f"\nRank {i}:")
     print(f"Name: {row['student_name']}")
     print(f"PRN: {row['roll_no']}")
     print(f"SGPA: {row['sem_5_sgpa']}")
     print(f"Percentage: {row['sem_5_percent']}")
     print(f"Grade: {row['sem_5_grade']}")

    # ------------------------------------------------
    # SUBJECT SUMMARY
    # ------------------------------------------------
    print("\n--- SUBJECT SUMMARY ---")
    subject_summary = engine.get_subject_summary()

    for subject, data in subject_summary.items():
        print(f"\nSubject: {subject}")
        for k, v in data.items():
            print(f"  {k}: {v}")

    # ------------------------------------------------
    # STUDENT MATRIX
    # ------------------------------------------------
    print("\n--- STUDENT MATRIX ---")
    matrix = engine.get_student_matrix()

    for roll, data in matrix.items():
        print(f"\n{data['name']} ({roll})")
        if data["passed_all"]:
            print("  Passed All Subjects")
        else:
            print("  Failed Subjects:")
            for sub in data["failed_subjects"]:
                print(f"   - {sub}")

    print("\n--- GENERATING EXCEL REPORT ---")

    report = ReportGenerator(
    engine,
    university="MGM University, Chh. Sambhajinagar",
    department="CSE (Integrated) Data Science",
    semester="V",
    academic_year="2025-26"
   )
    report.generate_report("Final_Result_Report.xlsx")
         