import pandas as pd


class ResultEngine:

    def __init__(self, file_path):
        self.file_path = file_path
        self.df = None

    # ---------------------------------------
    # LOAD + CLEAN
    # ---------------------------------------

    def load_data(self):
        self.df = pd.read_excel(self.file_path, header=[5, 6], engine="openpyxl")

        self.df.columns = [
            "_".join([str(i) for i in col if "Unnamed" not in str(i)])
            .strip()
            .lower()
            .replace(" ", "_")
            .replace("-", "_")
            .replace("/", "_")
            .replace("(", "")
            .replace(")", "")
            .replace(".", "")
            .replace("%", "percent")
            for col in self.df.columns
        ]

        print("Excel loaded successfully.\n")
        print(self.df.columns.tolist())

    # ---------------------------------------
    # CLASS OVERVIEW
    # ---------------------------------------

    def get_class_overview(self):

        total_students = len(self.df)

        passed = len(self.df[self.df["sem_5_grade"] != "F"])
        failed = len(self.df[self.df["sem_5_grade"] == "F"])

        avg_sgpa = round(self.df["sem_5_sgpa"].mean(), 2)

        pass_percentage = round((passed / total_students) * 100, 2)

        distinction = len(self.df[self.df["sem_5_sgpa"] >= 8])

        return {
            "total_students": total_students,
            "passed": passed,
            "failed": failed,
            "average_sgpa": avg_sgpa,
            "pass_percentage": pass_percentage,
            "distinction_count": distinction
        }

    # ---------------------------------------
    # CLASS TOPPERS
    # ---------------------------------------

    def get_class_toppers(self, top_n=3):

        sorted_df = self.df.sort_values(
            by=["sem_5_sgpa", "sem_5_percent"],
            ascending=False
       )
        sorted_df = sorted_df.reset_index(drop=True)

        top_df = sorted_df.head(top_n)

        top_df.index = top_df.index + 1

        return top_df[[
            "student_name",
            "roll_no",
            "sem_5_sgpa",
            "sem_5_percent",
            "sem_5_grade"
        ]]

    # ---------------------------------------
    # SUBJECT SUMMARY
    # ---------------------------------------

    def get_subject_summary(self):

        subject_tot_cols = [col for col in self.df.columns if col.endswith("_tot")]
        subject_pf_cols = [col for col in self.df.columns if col.endswith("_p_f")]

        report = {}

        for tot_col in subject_tot_cols:

            subject_name = tot_col.replace("_tot", "").upper()

            pf_col = tot_col.replace("_tot", "_p_f")

           # Convert total column safely to numeric
            self.df[tot_col] = pd.to_numeric(self.df[tot_col], errors="coerce")

            # Remove rows where total marks are NaN
            valid_students = self.df[self.df[tot_col].notna()]

            appeared = len(valid_students)

            # Find corresponding P/F column
            pf_col = tot_col.replace("_tot", "_p_f")

            passed = len(valid_students[valid_students[pf_col] == "P"])
            failed = len(valid_students[valid_students[pf_col] == "F"])

            pass_percent = round((passed / appeared) * 100, 2) if appeared > 0 else 0

            # Convert total column to numeric safely
            self.df[tot_col] = pd.to_numeric(self.df[tot_col], errors="coerce")

            topper_row = valid_students.loc[valid_students[tot_col].idxmax()]

            report[subject_name] = {
                "appeared": appeared,
                "passed": passed,
                "failed": failed,
                "pass_percent": pass_percent,
                "topper_name": topper_row["student_name"],
                "topper_prn": topper_row["roll_no"],
                "topper_marks": topper_row[tot_col]
            }

        return report

    # ---------------------------------------
    # STUDENT MATRIX
    # ---------------------------------------

    def get_student_matrix(self):

        subject_pf_cols = [col for col in self.df.columns if col.endswith("_p_f")]

        matrix = {}

        for _, row in self.df.iterrows():

            failed_subjects = []

            for col in subject_pf_cols:
                if row[col] == "F":
                    subject_name = col.replace("_p_f", "").upper()
                    failed_subjects.append(subject_name)

            matrix[row["roll_no"]] = {
                "name": row["student_name"],
                "passed_all": len(failed_subjects) == 0,
                "failed_subjects": failed_subjects
            }

        return matrix