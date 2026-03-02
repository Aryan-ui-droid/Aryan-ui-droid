import pandas as pd

class ReportGenerator:

    def __init__(self, engine, university, department, semester, academic_year):
        self.engine = engine
        self.df = engine.df

        self.university = university
        self.department = department
        self.semester = semester
        self.academic_year = academic_year
    def add_header(self, ws):
        from openpyxl.styles import Font, Alignment

        # University
        ws.merge_cells("A1:F1")
        ws["A1"] = self.university
        ws["A1"].font = Font(size=14, bold=True)
        ws["A1"].alignment = Alignment(horizontal="center")

        # Department
        ws.merge_cells("A2:F2")
        ws["A2"] = f"Department of {self.department}"
        ws["A2"].alignment = Alignment(horizontal="center")

        # Title
        ws.merge_cells("A3:F3")
        ws["A3"] = f"RESULT ANALYSIS REPORT - SEMESTER {self.semester}"
        ws["A3"].font = Font(bold=True)
        ws["A3"].alignment = Alignment(horizontal="center")

        # Academic Year
        ws.merge_cells("A4:F4")
        ws["A4"] = f"Academic Year: {self.academic_year}"
        ws["A4"].alignment = Alignment(horizontal="center")
    def generate_report(self, output_file):

        from openpyxl.styles import Font, Alignment
        from openpyxl.utils import get_column_letter

        # -------------------------
        # FETCH DATA
        # -------------------------
        overview = self.engine.get_class_overview()
        toppers_df = self.engine.get_class_toppers()
        subject_summary = self.engine.get_subject_summary()
        matrix = self.engine.get_student_matrix()

        subject_df = pd.DataFrame(subject_summary).T.reset_index()
        subject_df.rename(columns={"index": "Subject"}, inplace=True)

        matrix_data = []
        for roll, data in matrix.items():
            matrix_data.append({
                "Roll No": roll,
                "Student Name": data["name"],
                "Passed All Subjects": data["passed_all"],
                "Failed Subjects": ", ".join(data["failed_subjects"])
           })

        matrix_df = pd.DataFrame(matrix_data)

        # -------------------------
        # WRITE TO EXCEL
        # -------------------------
        with pd.ExcelWriter(output_file, engine="openpyxl") as writer:

            # =========================
            # 1️⃣ SUMMARY SHEET
            # =========================
            overview_df = pd.DataFrame([overview])
            overview_df.to_excel(
                writer,
                sheet_name="Summary",
                startrow=6,
                index=False
            )

            ws = writer.sheets["Summary"]
            self.add_header(ws)
            workbook = writer.book
            ws = writer.sheets["Summary"]

            # University Header Section
            ws.merge_cells("A1:F1")
            ws["A1"] = self.university
            ws["A1"].font = Font(size=14, bold=True)
            ws["A1"].alignment = Alignment(horizontal="center")

            ws.merge_cells("A2:F2")
            ws["A2"] = f"Department of {self.department}"
            ws["A2"].alignment = Alignment(horizontal="center")

            ws.merge_cells("A3:F3")
            ws["A3"] = f"RESULT ANALYSIS REPORT - SEMESTER {self.semester}"
            ws["A3"].font = Font(bold=True)
            ws["A3"].alignment = Alignment(horizontal="center")

            ws.merge_cells("A4:F4")
            ws["A4"] = f"Academic Year: {self.academic_year}"
            ws["A4"].alignment = Alignment(horizontal="center")

            # =========================
            # 2️⃣ SUBJECT ANALYSIS
            # =========================
            subject_df.to_excel(
                writer,
                sheet_name="Subject Analysis",
                startrow=6,
                index=False
            )

            ws = writer.sheets["Subject Analysis"]
            self.add_header(ws)
            # =========================
            # 3️⃣ CLASS TOPPERS
            # =========================
            toppers_df.to_excel(
                writer,
                sheet_name="Class Toppers",
                startrow=6,
                index=False
            )

            ws = writer.sheets["Class Toppers"]
            self.add_header(ws)
            # =========================
            # 4️⃣ STUDENT MATRIX
            # =========================
            matrix_df.to_excel(
                writer,
                sheet_name="Student Matrix",
                startrow=6,
                index=False
            )

            ws = writer.sheets["Student Matrix"]
            self.add_header(ws)
        print(f"\n✅ Professional Academic Report Generated → {output_file}")