import io
import os
import sqlite3
from hashlib import pbkdf2_hmac, sha1
from secrets import token_hex
from base64 import b64encode
import re
import zipfile
from datetime import datetime

import pandas as pd
import streamlit as st

from report_generator import ReportGenerator
from result_engine import ResultEngine

st.set_page_config(page_title="Result Analysis Dashboard", page_icon="R", layout="wide")

THEMES = {
    "Cobalt Sunrise": {
        "bg_a": "#f4f9ff",
        "bg_b": "#fff6ec",
        "ink": "#12233f",
        "muted": "#4a5e7a",
        "accent": "#0f62b5",
        "accent_alt": "#1f8a70",
        "success": "#1f9d55",
        "danger": "#c93c2b",
        "panel": "#ffffff",
        "palette": ["#0f62b5", "#f39c3d", "#1f8a70", "#c93c2b", "#6b9ac4", "#ffd166"],
    },
    "Emerald Brass": {
        "bg_a": "#f2faf6",
        "bg_b": "#fff8ee",
        "ink": "#17322a",
        "muted": "#4b635b",
        "accent": "#198f77",
        "accent_alt": "#b57f1b",
        "success": "#0f9b5f",
        "danger": "#b9382b",
        "panel": "#ffffff",
        "palette": ["#198f77", "#b57f1b", "#3f7fbc", "#d64545", "#46b3a8", "#f3c669"],
    },
    "Slate Citrus": {
        "bg_a": "#f5f7fa",
        "bg_b": "#eef7ee",
        "ink": "#1a2d3a",
        "muted": "#576b76",
        "accent": "#2f6fed",
        "accent_alt": "#6f9f2f",
        "success": "#2f9e44",
        "danger": "#cf3a3a",
        "panel": "#ffffff",
        "palette": ["#2f6fed", "#6f9f2f", "#f2994a", "#cf3a3a", "#56ccf2", "#ef5f2f"],
    },
}
DEFAULT_THEME_NAME = "Cobalt Sunrise"

PRIORITY_ORDER = {"High": 0, "Medium": 1, "Low": 2, "Info": 3}
ENGINE_CACHE_VERSION = "term-v2"
SUMMARY_FILTER_LABELS = {
    "total": "All Students",
    "passed": "Passed Students",
    "failed": "Failed Students",
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "app.db")


def ensure_db():
    os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            department TEXT,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            uploaded_at TEXT NOT NULL,
            filename TEXT NOT NULL,
            sheet_name TEXT,
            total_students INTEGER,
            passed INTEGER,
            failed INTEGER,
            pass_percent REAL,
            average_sgpa REAL,
            institution TEXT,
            department TEXT,
            class_name TEXT,
            semester TEXT,
            academic_year TEXT,
            file_hash TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS session_uploads (
            token TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            file_bytes BLOB NOT NULL,
            uploaded_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def hash_password(password, salt=None):
    if salt is None:
        salt = token_hex(16)
    hashed = pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000).hex()
    return hashed, salt


def create_user(username, name, department, password, is_admin=0):
    username = username.strip().lower()
    name = name.strip()
    if not username or not name or not password:
        return False, "Username, name, and password are required."
    password_hash, salt = hash_password(password)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO users (username, name, department, password_hash, salt, is_admin, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (username, name, department.strip(), password_hash, salt, is_admin, datetime.now().isoformat()),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return False, "Username already exists."
    conn.close()
    return True, "Account created."


def authenticate_user(username, password):
    username = username.strip().lower()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    hashed = pbkdf2_hmac("sha256", password.encode("utf-8"), row["salt"].encode("utf-8"), 120000).hex()
    if hashed != row["password_hash"]:
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "name": row["name"],
        "department": row["department"],
        "is_admin": bool(row["is_admin"]),
    }


def create_session(user_id):
    token = token_hex(24)
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO sessions (token, user_id, created_at, last_seen)
        VALUES (?, ?, ?, ?)
        """,
        (token, user_id, now, now),
    )
    conn.commit()
    conn.close()
    return token


def get_user_by_session(token):
    if not token:
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT u.*
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.token = ?
        """,
        (token,),
    )
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE sessions SET last_seen = ? WHERE token = ?", (datetime.now().isoformat(), token))
        conn.commit()
    conn.close()
    if row is None:
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "name": row["name"],
        "department": row["department"],
        "is_admin": bool(row["is_admin"]),
    }


def delete_session(token):
    if not token:
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()


def save_session_upload(token, filename, file_bytes):
    if not token or not file_bytes:
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR REPLACE INTO session_uploads (token, filename, file_bytes, uploaded_at)
        VALUES (?, ?, ?, ?)
        """,
        (token, filename, sqlite3.Binary(file_bytes), datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def load_session_upload(token):
    if not token:
        return None, None
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT filename, file_bytes
        FROM session_uploads
        WHERE token = ?
        """,
        (token,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None, None
    return row[0], row[1]


def delete_session_upload(token):
    if not token:
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM session_uploads WHERE token = ?", (token,))
    conn.commit()
    conn.close()


def get_query_param(name):
    try:
        params = st.query_params
        value = params.get(name, "")
        if isinstance(value, list):
            return value[0] if value else ""
        return value or ""
    except Exception:
        try:
            params = st.experimental_get_query_params()
            return params.get(name, [""])[0]
        except Exception:
            return ""


def set_query_param(name, value):
    try:
        st.query_params[name] = value
    except Exception:
        try:
            st.experimental_set_query_params(**{name: value})
        except Exception:
            pass


def clear_query_params():
    try:
        st.query_params.clear()
    except Exception:
        try:
            st.experimental_set_query_params()
        except Exception:
            pass


def record_history(user_id, file_bytes, filename, sheet_name, overview, profile):
    file_hash = sha1(file_bytes).hexdigest()
    signature = f"{user_id}:{file_hash}:{sheet_name}:{profile.get('institution')}:{profile.get('department')}:{profile.get('class_name')}:{profile.get('semester')}:{profile.get('academic_year')}"
    if st.session_state.get("last_history_signature") == signature:
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO history (
            user_id, uploaded_at, filename, sheet_name, total_students, passed, failed,
            pass_percent, average_sgpa, institution, department, class_name, semester,
            academic_year, file_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            datetime.now().isoformat(),
            filename,
            sheet_name,
            overview.get("total_students"),
            overview.get("passed"),
            overview.get("failed"),
            overview.get("pass_percent"),
            overview.get("average_sgpa"),
            profile.get("institution"),
            profile.get("department"),
            profile.get("class_name"),
            profile.get("semester"),
            profile.get("academic_year"),
            file_hash,
        ),
    )
    conn.commit()
    conn.close()
    st.session_state["last_history_signature"] = signature


def fetch_history(user_id, limit=200):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT uploaded_at, filename, sheet_name, total_students, passed, failed, pass_percent,
               average_sgpa, institution, department, class_name, semester, academic_year
        FROM history
        WHERE user_id = ?
        ORDER BY uploaded_at DESC
        LIMIT ?
        """,
        (user_id, limit),
    )
    rows = cur.fetchall()
    conn.close()
    if not rows:
        return pd.DataFrame(
            columns=[
                "uploaded_at",
                "filename",
                "sheet_name",
                "total_students",
                "passed",
                "failed",
                "pass_percent",
                "average_sgpa",
                "institution",
                "department",
                "class_name",
                "semester",
                "academic_year",
            ]
        )
    return pd.DataFrame([dict(row) for row in rows])


def grade_from_sgpa(sgpa):
    if pd.isna(sgpa):
        return "-"
    if sgpa >= 9.0:
        return "O"
    if sgpa >= 8.0:
        return "A+"
    if sgpa >= 7.0:
        return "A"
    if sgpa >= 6.0:
        return "B+"
    if sgpa >= 5.0:
        return "B"
    if sgpa >= 4.0:
        return "C"
    return "F"


def get_summary_filter_state_key(term_key):
    return f"summary_filter_{term_key or 'all'}"


def clear_summary_filter_state():
    for key in list(st.session_state.keys()):
        if str(key).startswith("summary_filter_"):
            del st.session_state[key]


def normalize_summary_filter(summary_filter):
    summary_filter = (summary_filter or "").strip().lower()
    return summary_filter if summary_filter in SUMMARY_FILTER_LABELS else ""


def apply_student_filters(
    matrix_df,
    student_search="",
    matrix_statuses=None,
    show_only_failed=False,
    summary_filter="",
    ignore_status_filters=False,
):
    filtered_df = matrix_df.copy()
    summary_filter = normalize_summary_filter(summary_filter)

    if summary_filter == "passed":
        filtered_df = filtered_df[filtered_df["Status"] == "Passed"]
    elif summary_filter == "failed":
        filtered_df = filtered_df[filtered_df["Status"] == "Failed"]

    if not ignore_status_filters:
        if matrix_statuses:
            filtered_df = filtered_df[filtered_df["Status"].isin(matrix_statuses)]
        if show_only_failed:
            filtered_df = filtered_df[filtered_df["Status"] == "Failed"]

    student_search = (student_search or "").strip()
    if student_search:
        mask = (
            filtered_df["Student Name"].str.contains(student_search, case=False, na=False)
            | filtered_df["PRN No"].str.contains(student_search, case=False, na=False)
        )
        filtered_df = filtered_df[mask]

    return filtered_df.reset_index(drop=True)


def apply_theme(theme):
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&family=DM+Serif+Display&display=swap');
        :root {{
            --ink: {theme['ink']};
            --muted: {theme['muted']};
            --accent: {theme['accent']};
            --accent-alt: {theme['accent_alt']};
            --panel: {theme['panel']};
            --success: {theme['success']};
            --danger: {theme['danger']};
            --soft-border: rgba(126, 157, 190, 0.28);
            --strong-border: rgba(84, 122, 167, 0.46);
            --surface-strong: rgba(255, 255, 255, 0.84);
            --surface-soft: rgba(245, 250, 255, 0.68);
            --surface-muted: rgba(255, 255, 255, 0.58);
            --glass-border: rgba(255, 255, 255, 0.52);
            --shell-border: rgba(255, 255, 255, 0.4);
            --soft-shadow: 0 22px 54px rgba(18, 35, 63, 0.12);
            --hover-shadow: 0 30px 68px rgba(18, 35, 63, 0.18);
        }}
        @keyframes float-up {{
            0% {{ transform: translateY(0px); opacity: 0.95; }}
            50% {{ transform: translateY(-7px); opacity: 1; }}
            100% {{ transform: translateY(0px); opacity: 0.95; }}
        }}
        @keyframes drift {{
            0% {{ transform: translateX(0px) translateY(0px) scale(1); }}
            50% {{ transform: translateX(12px) translateY(-10px) scale(1.04); }}
            100% {{ transform: translateX(0px) translateY(0px) scale(1); }}
        }}
        @keyframes glow-pulse {{
            0% {{ box-shadow: 0 0 0 0 rgba(15, 98, 181, 0.22); }}
            70% {{ box-shadow: 0 0 0 14px rgba(15, 98, 181, 0.0); }}
            100% {{ box-shadow: 0 0 0 0 rgba(15, 98, 181, 0.0); }}
        }}
        @keyframes fade-slide {{
            0% {{ opacity: 0; transform: translateY(18px); }}
            100% {{ opacity: 1; transform: translateY(0); }}
        }}
        @keyframes shimmer {{
            0% {{ transform: translateX(-135%); }}
            100% {{ transform: translateX(135%); }}
        }}
        .stApp {{
            color: var(--ink);
        }}
        [data-testid="stAppViewContainer"] {{
            background:
                radial-gradient(1280px 720px at -10% -8%, rgba(95, 166, 255, 0.26) 0%, transparent 62%),
                radial-gradient(1100px 640px at 108% -8%, rgba(255, 188, 96, 0.24) 0%, transparent 60%),
                radial-gradient(1180px 700px at 92% 112%, rgba(45, 180, 150, 0.2) 0%, transparent 58%),
                radial-gradient(980px 620px at 8% 102%, rgba(124, 160, 255, 0.16) 0%, transparent 56%),
                linear-gradient(140deg, #ecf4ff 0%, #eef6ff 26%, #fdf3e9 58%, #eff8f2 100%);
            background-attachment: fixed;
            position: relative;
            overflow-x: clip;
        }}
        [data-testid="stAppViewContainer"]::before {{
            content: "";
            position: fixed;
            inset: -12% -8%;
            background:
                radial-gradient(34% 28% at 14% 16%, rgba(255, 255, 255, 0.55) 0%, transparent 74%),
                radial-gradient(30% 24% at 84% 18%, rgba(255, 255, 255, 0.42) 0%, transparent 74%),
                radial-gradient(26% 22% at 70% 82%, rgba(255, 255, 255, 0.28) 0%, transparent 74%);
            pointer-events: none;
            z-index: 0;
            filter: blur(42px);
            animation: drift 18s ease-in-out infinite;
        }}
        [data-testid="stAppViewContainer"]::after {{
            content: "";
            position: fixed;
            inset: 0;
            background:
                linear-gradient(rgba(255, 255, 255, 0.06) 1px, transparent 1px),
                linear-gradient(90deg, rgba(255, 255, 255, 0.06) 1px, transparent 1px);
            background-size: 30px 30px;
            mask-image: radial-gradient(circle at 50% 44%, black 0%, rgba(0, 0, 0, 0.42) 68%, transparent 100%);
            pointer-events: none;
            z-index: 0;
            opacity: 0.38;
        }}
        [data-testid="stAppViewContainer"] > .main {{
            position: relative;
            z-index: 1;
        }}
        html, body, [class*="css"] {{
            font-family: 'Manrope', sans-serif;
            color: var(--ink);
        }}
        body {{
            letter-spacing: 0.01em;
        }}
        [data-testid="stHeader"] {{
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.7) 0%, rgba(255, 255, 255, 0.16) 100%);
            backdrop-filter: blur(12px);
        }}
        [data-testid="stMainBlockContainer"] {{
            position: relative;
            isolation: isolate;
            max-width: 1380px;
            padding-top: 2rem;
            padding-right: 2.2rem;
            padding-bottom: 3rem;
            padding-left: 2.2rem;
            margin-top: 0.8rem;
            margin-bottom: 1.8rem;
            border: 1px solid var(--shell-border);
            border-radius: 34px;
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.34) 0%, rgba(255, 255, 255, 0.18) 100%);
            box-shadow: 0 26px 64px rgba(12, 29, 50, 0.16);
            backdrop-filter: blur(18px);
            animation: fade-slide 0.55s ease-out;
        }}
        [data-testid="stSidebar"] {{
            position: relative;
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.76) 0%, rgba(244, 248, 255, 0.64) 100%);
            border-right: 1px solid var(--shell-border);
            box-shadow: inset -1px 0 0 rgba(255, 255, 255, 0.52);
            backdrop-filter: blur(18px);
        }}
        [data-testid="stSidebar"]::before {{
            content: "";
            position: absolute;
            inset: 0 0 auto 0;
            height: 240px;
            background:
                radial-gradient(360px 180px at 18% 12%, rgba(15, 98, 181, 0.14) 0%, transparent 72%),
                radial-gradient(280px 160px at 92% 8%, rgba(31, 138, 112, 0.14) 0%, transparent 74%);
            pointer-events: none;
        }}
        [data-testid="stSidebar"] > div:first-child {{
            height: 100vh;
            overflow-y: auto !important;
            overflow-x: hidden;
            padding: 1.05rem 1rem 1.4rem 1rem;
            padding-bottom: 24px;
        }}
        [data-testid="stSidebarContent"],
        [data-testid="stSidebarUserContent"] {{
            overflow-y: auto !important;
            max-height: 100vh;
        }}
        [data-testid="stSidebar"] > div:first-child::-webkit-scrollbar {{
            width: 10px;
        }}
        [data-testid="stSidebar"] > div:first-child::-webkit-scrollbar-thumb {{
            background: linear-gradient(180deg, {theme['accent']} 0%, {theme['accent_alt']} 100%);
            border-radius: 999px;
        }}
        [data-testid="stSidebar"] > div:first-child::-webkit-scrollbar-track {{
            background: rgba(255, 255, 255, 0.4);
            border-radius: 999px;
        }}
        [data-testid="stSidebar"] * {{
            color: var(--ink);
        }}
        h1, h2, h3, h4 {{
            font-family: 'DM Serif Display', serif;
            color: var(--ink);
            letter-spacing: 0.01em;
        }}
        p, label {{
            color: var(--muted);
        }}
        .sidebar-brand {{
            position: relative;
            overflow: hidden;
            margin-bottom: 16px;
            padding: 18px 18px 16px;
            border-radius: 22px;
            border: 1px solid var(--soft-border);
            background: linear-gradient(145deg, rgba(255, 255, 255, 0.96) 0%, rgba(247, 251, 255, 0.84) 100%);
            box-shadow: var(--soft-shadow);
        }}
        .sidebar-brand::after {{
            content: "";
            position: absolute;
            width: 150px;
            height: 150px;
            right: -55px;
            top: -70px;
            background: radial-gradient(circle, rgba(15, 98, 181, 0.18) 0%, transparent 70%);
            pointer-events: none;
        }}
        .sidebar-brand__kicker {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 6px 10px;
            border-radius: 999px;
            font-size: 0.72rem;
            font-weight: 800;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            color: var(--accent);
            background: rgba(15, 98, 181, 0.08);
            border: 1px solid rgba(15, 98, 181, 0.14);
        }}
        .sidebar-brand__title {{
            margin: 12px 0 6px;
            font-family: 'DM Serif Display', serif;
            font-size: 1.48rem;
            line-height: 1.12;
            color: var(--ink);
        }}
        .sidebar-brand__text {{
            font-size: 0.92rem;
            line-height: 1.65;
            color: var(--muted);
        }}
        .sidebar-section-title {{
            margin: 18px 0 10px;
            font-size: 0.76rem;
            font-weight: 800;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            color: var(--accent-alt);
        }}
        .sidebar-session-chip {{
            margin-top: 10px;
            padding: 12px 14px;
            border-radius: 16px;
            background: rgba(255, 255, 255, 0.74);
            border: 1px solid var(--soft-border);
            box-shadow: 0 12px 26px rgba(18, 35, 63, 0.06);
            color: var(--muted);
            font-size: 0.9rem;
            line-height: 1.55;
        }}
        .hero-wrap {{
            background:
                linear-gradient(125deg, rgba(255, 255, 255, 0.82) 0%, rgba(255, 255, 255, 0.62) 44%, rgba(255, 255, 255, 0.72) 100%),
                linear-gradient(135deg, {theme['bg_a']} 0%, {theme['bg_b']} 100%);
            border: 1px solid rgba(255, 255, 255, 0.55);
            border-radius: 26px;
            padding: 28px 30px 24px 30px;
            margin-bottom: 14px;
            box-shadow: var(--soft-shadow);
            position: relative;
            overflow: hidden;
            backdrop-filter: blur(12px);
            min-height: 290px;
        }}
        .hero-wrap::before {{
            content: "";
            position: absolute;
            inset: 0;
            background: linear-gradient(120deg, transparent 0%, rgba(255, 255, 255, 0.66) 45%, transparent 100%);
            transform: translateX(-120%);
            animation: shimmer 10s ease-in-out infinite;
            pointer-events: none;
        }}
        .hero-wrap::after {{
            content: "";
            position: absolute;
            width: 260px;
            height: 260px;
            right: -110px;
            bottom: -140px;
            background: linear-gradient(135deg, rgba(31, 138, 112, 0.24) 0%, rgba(15, 98, 181, 0.22) 100%);
            clip-path: polygon(0 0, 100% 28%, 76% 100%, 10% 86%);
            transform: rotate(14deg);
            z-index: 1;
            filter: blur(0.2px);
        }}
        .hero-title {{
            margin: 0;
            font-size: clamp(2rem, 3vw, 3rem);
            line-height: 1.05;
            position: relative;
            z-index: 2;
        }}
        .hero-subtitle {{
            margin: 10px 0 0 0;
            color: var(--muted);
            font-size: 1.02rem;
            font-weight: 600;
            line-height: 1.72;
            max-width: 820px;
            position: relative;
            z-index: 2;
        }}
        .hero-badge {{
            display: inline-block;
            margin-top: 14px;
            padding: 7px 13px;
            border-radius: 999px;
            font-size: 0.76rem;
            font-weight: 800;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            background: rgba(15, 98, 181, 0.08);
            border: 1px solid rgba(15, 98, 181, 0.16);
            color: var(--accent);
            position: relative;
            z-index: 2;
        }}
        .hero-meta {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 18px;
            position: relative;
            z-index: 2;
        }}
        .hero-meta span {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 9px 12px;
            border-radius: 14px;
            background: rgba(255, 255, 255, 0.72);
            border: 1px solid rgba(136, 164, 194, 0.28);
            color: var(--ink);
            font-size: 0.88rem;
            font-weight: 700;
            box-shadow: 0 10px 22px rgba(18, 35, 63, 0.06);
        }}
        .hero-orb {{
            position: absolute;
            border-radius: 50%;
            filter: blur(0.2px);
            opacity: 0.25;
            z-index: 1;
            animation: float-up 6s ease-in-out infinite;
        }}
        .hero-orb.orb-a {{
            width: 180px;
            height: 180px;
            right: -30px;
            top: -45px;
            background: radial-gradient(circle at 35% 30%, {theme['accent']}, transparent 70%);
        }}
        .hero-orb.orb-b {{
            width: 140px;
            height: 140px;
            right: 120px;
            bottom: -65px;
            background: radial-gradient(circle at 40% 40%, {theme['accent_alt']}, transparent 72%);
            animation-delay: 0.6s;
        }}
        .feature-grid {{
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 14px;
            margin: 16px 0 6px;
        }}
        .feature-card {{
            position: relative;
            overflow: hidden;
            min-height: 150px;
            padding: 18px 18px 16px;
            border-radius: 20px;
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(248, 252, 255, 0.86) 100%);
            border: 1px solid var(--soft-border);
            box-shadow: var(--soft-shadow);
            animation: fade-slide 0.55s ease-out;
        }}
        .feature-card::before {{
            content: "";
            position: absolute;
            inset: 0;
            background: linear-gradient(120deg, transparent 0%, rgba(255, 255, 255, 0.66) 45%, transparent 100%);
            transform: translateX(-140%);
            animation: shimmer 8s ease-in-out infinite;
            pointer-events: none;
        }}
        .feature-card__eyebrow {{
            position: relative;
            z-index: 1;
            font-size: 0.74rem;
            font-weight: 800;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            color: var(--accent-alt);
        }}
        .feature-card__title {{
            position: relative;
            z-index: 1;
            margin-top: 10px;
            font-size: 1.08rem;
            font-weight: 800;
            color: var(--ink);
        }}
        .feature-card__text {{
            position: relative;
            z-index: 1;
            margin-top: 8px;
            font-size: 0.92rem;
            line-height: 1.68;
            color: var(--muted);
        }}
        .workspace-card {{
            position: relative;
            overflow: hidden;
            margin-bottom: 14px;
            padding: 22px 22px 20px;
            border-radius: 22px;
            border: 1px solid rgba(255, 255, 255, 0.56);
            background: linear-gradient(160deg, rgba(255, 255, 255, 0.84) 0%, rgba(245, 250, 255, 0.72) 100%);
            box-shadow: var(--soft-shadow);
            backdrop-filter: blur(10px);
        }}
        .workspace-card::before {{
            content: "";
            position: absolute;
            width: 220px;
            height: 220px;
            right: -80px;
            top: -80px;
            background: radial-gradient(circle, rgba(15, 98, 181, 0.14) 0%, transparent 72%);
            pointer-events: none;
        }}
        .workspace-card__kicker {{
            position: relative;
            z-index: 1;
            font-size: 0.74rem;
            font-weight: 800;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            color: var(--accent);
        }}
        .workspace-card__title {{
            position: relative;
            z-index: 1;
            margin-top: 10px;
            font-family: 'DM Serif Display', serif;
            font-size: 1.6rem;
            line-height: 1.12;
            color: var(--ink);
        }}
        .workspace-card__text {{
            position: relative;
            z-index: 1;
            margin-top: 10px;
            color: var(--muted);
            font-size: 0.95rem;
            line-height: 1.68;
        }}
        .workspace-card__stats {{
            position: relative;
            z-index: 1;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
            gap: 10px;
            margin-top: 16px;
        }}
        .workspace-stat {{
            padding: 12px 12px 11px;
            border-radius: 16px;
            background: rgba(255, 255, 255, 0.76);
            border: 1px solid rgba(136, 164, 194, 0.26);
            box-shadow: 0 10px 24px rgba(18, 35, 63, 0.06);
        }}
        .workspace-stat__value {{
            font-size: 1.12rem;
            font-weight: 800;
            color: var(--ink);
        }}
        .workspace-stat__label {{
            margin-top: 4px;
            font-size: 0.8rem;
            color: var(--muted);
            line-height: 1.45;
        }}
        .mini-note {{
            color: var(--muted);
            font-size: 0.9rem;
            margin-top: 10px;
            padding: 12px 14px;
            border-radius: 14px;
            background: rgba(255, 255, 255, 0.72);
            border: 1px dashed rgba(136, 164, 194, 0.44);
            line-height: 1.65;
        }}
        .profile-ribbon {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin: 14px 0 20px;
        }}
        .topper-card {{
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(248, 252, 255, 0.9) 100%);
            border: 1px solid rgba(136, 164, 194, 0.34);
            border-radius: 18px;
            padding: 16px 16px 14px;
            min-height: 132px;
            box-shadow: 0 10px 24px rgba(22, 42, 66, 0.08);
            transition: transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease;
        }}
        .topper-card:hover {{
            transform: translateY(-4px);
            box-shadow: var(--hover-shadow);
            border-color: rgba(15, 98, 181, 0.24);
        }}
        .topper-rank {{
            color: var(--accent);
            font-size: 1.1rem;
            margin: 0;
        }}
        .topper-name {{
            margin: 4px 0 8px 0;
            font-weight: 800;
            font-size: 0.97rem;
        }}
        .chip {{
            display: inline-block;
            border-radius: 999px;
            padding: 7px 12px;
            margin: 0;
            font-size: 0.79rem;
            font-weight: 700;
            color: #113b69;
            background: linear-gradient(135deg, rgba(232, 241, 255, 0.96) 0%, rgba(240, 247, 255, 0.96) 100%);
            border: 1px solid #cfe2fb;
            transition: transform 0.18s ease, box-shadow 0.18s ease;
            box-shadow: 0 8px 18px rgba(17, 59, 105, 0.06);
        }}
        .chip:hover {{
            transform: translateY(-1px);
            box-shadow: 0 14px 22px rgba(17, 59, 105, 0.1);
        }}
        .section-kicker {{
            color: var(--accent-alt);
            font-weight: 800;
            letter-spacing: 0.16em;
            font-size: 0.76rem;
            text-transform: uppercase;
            margin-bottom: 6px;
        }}
        [data-testid="stMetric"] {{
            background: linear-gradient(145deg, rgba(255, 255, 255, 0.98) 0%, rgba(247, 251, 255, 0.94) 100%);
            border: 1px solid rgba(136, 164, 194, 0.34);
            border-radius: 18px;
            padding: 14px 16px;
            box-shadow: 0 10px 24px rgba(14, 36, 61, 0.08);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }}
        [data-testid="stMetric"]:hover {{
            transform: translateY(-2px);
            box-shadow: 0 18px 34px rgba(14, 36, 61, 0.13);
        }}
        [data-testid="stMetricLabel"] {{
            color: var(--muted) !important;
            font-weight: 700 !important;
        }}
        [data-testid="stMetricValue"] {{
            font-family: 'DM Serif Display', serif;
        }}
        .summary-tile {{
            --summary-accent: {theme['accent']};
            background: linear-gradient(160deg, rgba(255, 255, 255, 0.98) 0%, rgba(247, 251, 255, 0.94) 100%);
            border: 1px solid rgba(136, 164, 194, 0.34);
            border-top: 4px solid var(--summary-accent);
            border-radius: 18px;
            padding: 16px 18px 14px;
            min-height: 128px;
            box-shadow: 0 12px 26px rgba(14, 36, 61, 0.08);
            transition: transform 0.22s ease, box-shadow 0.22s ease, border-color 0.22s ease;
        }}
        .summary-tile:hover {{
            transform: translateY(-2px);
            box-shadow: 0 18px 34px rgba(14, 36, 61, 0.12);
            border-color: rgba(15, 98, 181, 0.18);
        }}
        .summary-tile-active {{
            border-color: var(--summary-accent);
            box-shadow: 0 18px 34px rgba(14, 36, 61, 0.14);
            transform: translateY(-2px);
        }}
        .summary-tile__label {{
            color: var(--muted);
            font-size: 0.86rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.35px;
        }}
        .summary-tile__value {{
            margin-top: 10px;
            font-size: 2.1rem;
            font-weight: 800;
            line-height: 1;
            color: var(--ink);
        }}
        .summary-tile__hint {{
            margin-top: 10px;
            color: var(--muted);
            font-size: 0.88rem;
            line-height: 1.45;
        }}
        .sidebar-brand,
        .hero-wrap,
        .workspace-card,
        .mini-note,
        .topper-card,
        [data-testid="stMetric"],
        .summary-tile,
        .stTabs [data-baseweb="tab-list"],
        details[data-testid="stExpander"],
        div[data-testid="stAlert"],
        [data-testid="stDataFrame"],
        [data-testid="stVegaLiteChart"] {{
            background: linear-gradient(180deg, var(--surface-strong) 0%, var(--surface-soft) 100%);
            border-color: var(--glass-border) !important;
            box-shadow: var(--soft-shadow);
            backdrop-filter: blur(18px);
        }}
        .hero-meta span,
        .workspace-stat,
        .chip,
        .sidebar-session-chip {{
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.8) 0%, rgba(246, 250, 255, 0.68) 100%);
            border-color: rgba(255, 255, 255, 0.46) !important;
            box-shadow: 0 12px 24px rgba(18, 35, 63, 0.08);
        }}
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        div[data-testid="stTextInput"] input,
        div[data-testid="stNumberInput"] input,
        div[data-testid="stTextArea"] textarea {{
            border-radius: 14px !important;
            border: 1px solid var(--soft-border) !important;
            background: rgba(255, 255, 255, 0.9) !important;
            color: var(--ink) !important;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.58);
        }}
        div[data-baseweb="select"] > div:hover,
        div[data-baseweb="input"] > div:hover,
        div[data-testid="stTextInput"] input:hover,
        div[data-testid="stNumberInput"] input:hover,
        div[data-testid="stTextArea"] textarea:hover {{
            border-color: var(--strong-border) !important;
        }}
        div[data-baseweb="select"] > div:focus-within,
        div[data-baseweb="input"] > div:focus-within,
        div[data-testid="stTextInput"] input:focus,
        div[data-testid="stNumberInput"] input:focus,
        div[data-testid="stTextArea"] textarea:focus {{
            border-color: var(--accent) !important;
            box-shadow: 0 0 0 4px rgba(15, 98, 181, 0.12) !important;
        }}
        div[data-testid="stMultiSelect"] [data-baseweb="tag"] {{
            border-radius: 999px;
            border: 1px solid rgba(15, 98, 181, 0.14);
            background: rgba(15, 98, 181, 0.08);
            color: var(--accent);
            font-weight: 700;
        }}
        div[data-testid="stSlider"] [role="slider"] {{
            background: var(--accent) !important;
            border: 2px solid #ffffff !important;
            box-shadow: 0 4px 14px rgba(15, 98, 181, 0.28);
        }}
        button[kind="primary"] {{
            border-radius: 14px !important;
            border: none !important;
            background: linear-gradient(135deg, {theme['accent']} 0%, {theme['accent_alt']} 100%) !important;
            color: #ffffff !important;
            font-weight: 800 !important;
            box-shadow: 0 16px 28px rgba(15, 98, 181, 0.2) !important;
            transition: transform 0.2s ease, box-shadow 0.2s ease, filter 0.2s ease;
        }}
        button[kind="primary"]:hover {{
            transform: translateY(-1px);
            box-shadow: 0 20px 34px rgba(15, 98, 181, 0.24) !important;
            filter: saturate(1.05);
        }}
        button[kind="secondary"], .stDownloadButton button {{
            border-radius: 14px !important;
            border: 1px solid rgba(136, 164, 194, 0.36) !important;
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.98) 0%, rgba(243, 249, 255, 0.96) 100%) !important;
            color: var(--ink) !important;
            font-weight: 800 !important;
            box-shadow: 0 12px 24px rgba(18, 35, 63, 0.06) !important;
            transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
        }}
        button[kind="secondary"]:hover, .stDownloadButton button:hover {{
            border-color: {theme['accent']} !important;
            box-shadow: 0 16px 28px rgba(15, 98, 181, 0.16) !important;
            transform: translateY(-1px);
        }}
        [data-testid="stFileUploader"] {{
            position: relative;
            overflow: hidden;
            padding: 0.95rem 1rem 1rem;
            border-radius: 24px;
            border: 1.5px dashed rgba(15, 98, 181, 0.28);
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.82) 0%, rgba(246, 250, 255, 0.68) 100%);
            box-shadow: 0 18px 36px rgba(15, 98, 181, 0.1);
            backdrop-filter: blur(16px);
            transition: transform 0.2s ease, box-shadow 0.25s ease, border-color 0.25s ease;
        }}
        [data-testid="stFileUploader"]::after {{
            content: "";
            position: absolute;
            width: 260px;
            height: 260px;
            right: -70px;
            top: -120px;
            background: radial-gradient(circle, rgba(15, 98, 181, 0.14) 0%, transparent 68%);
            pointer-events: none;
        }}
        [data-testid="stFileUploader"]:hover {{
            transform: translateY(-2px);
            border-color: rgba(15, 98, 181, 0.48);
            box-shadow: 0 24px 40px rgba(15, 98, 181, 0.16);
        }}
        [data-testid="stFileUploader"] section {{
            padding: 0 !important;
        }}
        [data-testid="stFileUploaderDropzone"] {{
            background: transparent !important;
            border: none !important;
            padding: 0 !important;
        }}
        [data-testid="stFileUploaderDropzone"] > div {{
            padding: 0.5rem 0 !important;
        }}
        [data-testid="stFileUploaderDropzoneInstructions"] > div:first-child {{
            font-size: 1.04rem !important;
            font-weight: 800 !important;
            color: var(--ink) !important;
        }}
        [data-testid="stFileUploaderDropzoneInstructions"] small {{
            font-size: 0.86rem !important;
            color: var(--muted) !important;
        }}
        [data-testid="stFileUploader"] button {{
            background: rgba(255, 255, 255, 0.9) !important;
            color: var(--accent) !important;
            border: 1px solid rgba(15, 98, 181, 0.18) !important;
            border-radius: 14px !important;
            font-weight: 800 !important;
        }}
        [data-testid="stFileUploader"] button:hover {{
            border-color: var(--accent) !important;
        }}
        .stTabs [data-baseweb="tab-list"] {{
            gap: 6px;
            background: linear-gradient(180deg, rgba(255, 255, 255, 0.8) 0%, rgba(246, 250, 255, 0.68) 100%);
            padding: 8px;
            border: 1px solid var(--glass-border);
            border-radius: 16px;
            box-shadow: var(--soft-shadow);
            backdrop-filter: blur(18px);
        }}
        .stTabs [data-baseweb="tab"] {{
            border-radius: 12px;
            min-height: 48px;
            padding: 12px 18px;
            font-size: 1rem;
            font-weight: 700;
            letter-spacing: 0.15px;
            transition: all 0.2s ease;
        }}
        .stTabs [data-baseweb="tab"] > div,
        .stTabs [data-baseweb="tab"] p {{
            font-size: 1rem !important;
            font-weight: 700 !important;
        }}
        .stTabs [aria-selected="true"] {{
            background: linear-gradient(135deg, {theme['accent']} 0%, {theme['accent_alt']} 100%);
            color: #ffffff !important;
            font-weight: 800;
            animation: glow-pulse 1.5s ease-out 1;
        }}
        .stTabs [data-baseweb="tab-panel"] {{
            padding-top: 1.1rem;
            animation: fade-slide 0.35s ease-out;
        }}
        div[data-testid="stAlert"] {{
            border-radius: 18px;
            border: 1px solid var(--glass-border);
            overflow: hidden;
            box-shadow: var(--soft-shadow);
            backdrop-filter: blur(18px);
        }}
        div[data-testid="stAlert"] > div {{
            background: linear-gradient(180deg, var(--surface-strong) 0%, var(--surface-soft) 100%);
        }}
        div[data-testid="stAlert"] p {{
            font-weight: 600;
        }}
        details[data-testid="stExpander"] {{
            border: 1px solid var(--glass-border);
            border-radius: 18px;
            background: linear-gradient(180deg, var(--surface-strong) 0%, var(--surface-soft) 100%);
            box-shadow: var(--soft-shadow);
            backdrop-filter: blur(18px);
        }}
        details[data-testid="stExpander"] summary {{
            padding: 0.8rem 1rem;
            font-weight: 700;
            color: var(--ink);
        }}
        [data-testid="stDataFrame"] {{
            border: 1px solid var(--glass-border);
            border-radius: 18px;
            background: linear-gradient(180deg, var(--surface-strong) 0%, var(--surface-soft) 100%);
            box-shadow: var(--soft-shadow);
            backdrop-filter: blur(18px);
            overflow: hidden;
        }}
        [data-testid="stVegaLiteChart"] {{
            border: 1px solid var(--glass-border);
            border-radius: 18px;
            padding: 10px;
            background: linear-gradient(180deg, var(--surface-strong) 0%, var(--surface-soft) 100%);
            box-shadow: var(--soft-shadow);
            backdrop-filter: blur(18px);
            overflow: hidden;
        }}
        @media (max-width: 1100px) {{
            .feature-grid {{
                grid-template-columns: 1fr;
            }}
        }}
        @media (max-width: 900px) {{
            [data-testid="stMainBlockContainer"] {{
                padding-top: 1.25rem;
                padding-right: 1rem;
                padding-bottom: 2rem;
                padding-left: 1rem;
            }}
            .hero-wrap,
            .workspace-card {{
                padding: 20px 18px 18px;
                border-radius: 22px;
            }}
            .hero-title {{
                font-size: 1.9rem;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def load_login_background():
    candidates = [
        os.path.join(BASE_DIR, "assets", "login_bg.jpg"),
        os.path.join(BASE_DIR, "assets", "login_bg.jpeg"),
        os.path.join(BASE_DIR, "assets", "login_bg.png"),
        os.path.join(BASE_DIR, "assets", "college.jpg"),
        os.path.join(BASE_DIR, "assets", "college.jpeg"),
        os.path.join(BASE_DIR, "assets", "college.png"),
        os.path.join(BASE_DIR, "assets", "login image.jpg"),
        os.path.join(BASE_DIR, "assets", "login image.jpeg"),
        os.path.join(BASE_DIR, "assets", "login image.png"),
    ]
    for path in candidates:
        if os.path.exists(path):
            with open(path, "rb") as handle:
                data = handle.read()
            ext = os.path.splitext(path)[1].lower()
            mime = "image/png" if ext == ".png" else "image/jpeg"
            return f"data:{mime};base64,{b64encode(data).decode('ascii')}"

    assets_dir = os.path.join(BASE_DIR, "assets")
    if os.path.isdir(assets_dir):
        allowed = {".jpg", ".jpeg", ".png"}
        for fname in sorted(os.listdir(assets_dir)):
            ext = os.path.splitext(fname)[1].lower()
            if ext in allowed:
                path = os.path.join(assets_dir, fname)
                with open(path, "rb") as handle:
                    data = handle.read()
                mime = "image/png" if ext == ".png" else "image/jpeg"
                return f"data:{mime};base64,{b64encode(data).decode('ascii')}"
    return ""


def apply_login_theme(bg_data_uri):
    if bg_data_uri:
        background_rule = (
            f'background: linear-gradient(0deg, rgba(7, 12, 20, 0.62), rgba(7, 12, 20, 0.62)), '
            f'url("{bg_data_uri}") center/cover no-repeat fixed;'
        )
    else:
        background_rule = "background: linear-gradient(135deg, #0b1625 0%, #122235 100%);"

    st.markdown(
        f"""
        <style>
        [data-testid="stSidebar"],
        [data-testid="stHeader"],
        [data-testid="stToolbar"] {{
            display: none !important;
        }}
        [data-testid="stAppViewContainer"] {{
            {background_rule}
        }}
        [data-testid="stAppViewContainer"]::before,
        [data-testid="stAppViewContainer"]::after {{
            display: none;
        }}
        section.main > div {{
            padding-top: 7vh;
            padding-bottom: 7vh;
        }}
        .login-left {{
            color: #f3f6fb;
            text-shadow: 0 12px 30px rgba(0, 0, 0, 0.45);
        }}
        .login-kicker {{
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.2em;
            font-size: 1rem;
            color: rgba(255, 255, 255, 0.78);
            margin-bottom: 12px;
        }}
        .login-left p.login-subtitle {{
            font-size: 1.12rem;
            font-weight: 700;
            letter-spacing: 0.02em;
            color: rgba(255, 255, 255, 0.92);
        }}
        .login-title {{
            font-family: 'DM Serif Display', serif;
            display: block;
            font-size: 2.8rem;
            line-height: 1.05;
            margin: 0 0 12px;
            color: #ffffff !important;
            -webkit-text-fill-color: #ffffff !important;
            text-shadow: 0 10px 24px rgba(0, 0, 0, 0.32);
        }}
        .login-subtitle {{
            font-size: 1.05rem;
            color: rgba(255, 255, 255, 0.78);
            max-width: 440px;
        }}
        .login-card-title {{
            font-size: 1.6rem;
            font-weight: 700;
            color: #f8fbff;
            margin-bottom: 4px;
        }}
        .login-card-subtitle {{
            color: rgba(255, 255, 255, 0.7);
            margin-bottom: 18px;
        }}
        div[data-testid="stForm"] {{
            background: rgba(14, 21, 32, 0.9);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 22px;
            padding: 26px 26px 20px;
            box-shadow: 0 22px 50px rgba(0, 0, 0, 0.4);
            backdrop-filter: blur(10px);
        }}
        div[data-testid="stForm"] label {{
            color: rgba(255, 255, 255, 0.82);
            font-weight: 600;
        }}
        div[data-testid="stTextInput"] input {{
            background: #ffffff;
            border: 1px solid #d9e2ef;
            color: #0f172a;
            padding: 14px 12px;
            border-radius: 12px;
        }}
        div[data-testid="stTextInput"] input::placeholder {{
            color: #6b7a8a;
        }}
        div[data-testid="stTextInput"] input::selection {{
            background: #0f172a;
            color: #ffffff;
        }}
        div[data-testid="stTextInput"] input::-moz-selection {{
            background: #0f172a;
            color: #ffffff;
        }}
        div[data-testid="stTextInput"] input:focus {{
            color: #0f172a;
        }}
        div[data-testid="stTextInput"] input:-webkit-autofill,
        div[data-testid="stTextInput"] input:-webkit-autofill:hover,
        div[data-testid="stTextInput"] input:-webkit-autofill:focus {{
            -webkit-text-fill-color: #0f172a !important;
            box-shadow: 0 0 0px 1000px #ffffff inset !important;
            transition: background-color 9999s ease-in-out 0s;
        }}
        div[data-testid="stTextInput"] input:focus {{
            border-color: rgba(243, 156, 61, 0.9);
            box-shadow: 0 0 0 3px rgba(243, 156, 61, 0.22);
        }}
        button[kind="primary"] {{
            background: linear-gradient(90deg, #f4a045 0%, #ef7d1b 100%) !important;
            border: none !important;
            color: #1b0b00 !important;
            font-weight: 800 !important;
            font-size: 1.05rem !important;
            padding: 0.65rem 1rem !important;
            border-radius: 12px !important;
            width: 100% !important;
            box-shadow: 0 12px 24px rgba(243, 156, 61, 0.25);
        }}
        .login-links {{
            display: flex;
            justify-content: space-between;
            font-size: 0.92rem;
            color: rgba(255, 255, 255, 0.7);
            margin: 6px 0 14px;
        }}
        .login-links a {{
            color: rgba(255, 255, 255, 0.85);
            text-decoration: none;
        }}
        .login-support {{
            color: rgba(255, 255, 255, 0.7);
            text-align: center;
            margin-top: 12px;
        }}
        .login-support span {{
            color: #6ec2ff;
            font-weight: 600;
        }}
        .stTabs [data-baseweb="tab-list"] {{
            background: rgba(4, 10, 18, 0.55);
            border: 1px solid rgba(255, 255, 255, 0.2);
            border-radius: 14px;
            padding: 6px;
        }}
        .stTabs [data-baseweb="tab"] {{
            border-radius: 10px !important;
            min-height: 44px !important;
            padding: 10px 16px !important;
            font-size: 1.02rem !important;
            font-weight: 700 !important;
            color: rgba(255, 255, 255, 0.85) !important;
        }}
        .stTabs [aria-selected="true"] {{
            background: rgba(255, 255, 255, 0.2) !important;
            color: #ffffff !important;
            box-shadow: 0 8px 18px rgba(0, 0, 0, 0.35);
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def normalize_semester(value):
    txt = str(value).strip()
    if not txt or txt.lower() in {"nan", "none", "na", "null", "-"}:
        return ""
    m = re.search(r"\b(\d+)\b", txt)
    if m:
        return f"Sem {int(m.group(1))}"
    roman_map = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8}
    m = re.search(r"\b([ivx]+)\b", txt.lower())
    if m and m.group(1) in roman_map:
        return f"Sem {roman_map[m.group(1)]}"
    return txt


def normalize_academic_year(value):
    txt = str(value).strip()
    if not txt or txt.lower() in {"nan", "none", "na", "null", "-"}:
        return ""
    years = re.findall(r"\d{4}", txt)
    if len(years) >= 2:
        return f"{years[0]}-{years[1]}"
    short = re.search(r"(\d{4})\D+(\d{2})", txt)
    if short:
        return f"{short.group(1)}-20{short.group(2)}"
    return txt


def extract_academic_details(file_bytes, sheet_name):
    details = {
        "institution": "",
        "department": "",
        "class_name": "",
        "semester": "",
        "academic_year": "",
    }

    try:
        raw = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, header=None, nrows=40)
        texts = []
        for val in raw.fillna("").values.flatten().tolist():
            txt = str(val).strip()
            if txt:
                texts.append(txt)

        def find_value(keywords):
            for txt in texts:
                low = txt.lower()
                if any(k in low for k in keywords):
                    if ":" in txt:
                        return txt.split(":", 1)[1].strip()
                    return txt.strip()
            return ""

        details["institution"] = find_value(["university", "institute", "college"])
        details["department"] = find_value(["department", "course name", "school"])
        details["class_name"] = find_value(["class", "program", "branch"])
        details["semester"] = find_value(["semester", "term"])
        details["academic_year"] = find_value(["academic year", "academic batch", "batch"])

        if not details["class_name"] and details["department"]:
            m = re.search(r"\(([^()]+)\)\s*$", details["department"])
            if m:
                details["class_name"] = m.group(1).strip()
    except Exception:
        pass

    if not details["class_name"]:
        details["class_name"] = sheet_name

    return details


def login_screen():
    bg = load_login_background()
    apply_login_theme(bg)

    left, right = st.columns([1.2, 1])
    with left:
        st.markdown('<div class="login-kicker">Faculty Workspace</div>', unsafe_allow_html=True)
        st.markdown('<div class="login-title">Academic Result Intelligence</div>', unsafe_allow_html=True)
        st.markdown(
            '<p class="login-subtitle">Sign in to analyze term-wise performance, track subjects, and export reports.</p>',
            unsafe_allow_html=True,
        )

    with right:
        login_tab, register_tab = st.tabs(["Login", "Create Account"])

        with login_tab:
            with st.form("login_form"):
                st.markdown('<div class="login-card-title">Result Analysis Portal</div>', unsafe_allow_html=True)
                st.markdown('<div class="login-card-subtitle">Please login to continue</div>', unsafe_allow_html=True)
                username = st.text_input("Faculty ID / Email", key="login_user")
                password = st.text_input("Password", type="password", key="login_pass")
                submit = st.form_submit_button("Login")
            if submit:
                user = authenticate_user(username, password)
                if user:
                    token = create_session(user["id"])
                    st.session_state["user"] = user
                    st.session_state["session_token"] = token
                    st.session_state["uploaded_file_bytes"] = None
                    st.session_state["uploaded_filename"] = ""
                    st.session_state["engine_cache"] = None
                    st.session_state["engine_signature"] = ""
                    clear_summary_filter_state()
                    set_query_param("session", token)
                    st.success("Login successful. Redirecting to upload...")
                    st.rerun()
                else:
                    st.error("Invalid credentials.")

        with register_tab:
            with st.form("register_form"):
                st.markdown('<div class="login-card-title">Create account</div>', unsafe_allow_html=True)
                st.markdown('<div class="login-card-subtitle">Register to access analytics</div>', unsafe_allow_html=True)
                full_name = st.text_input("Full Name", key="reg_name")
                department = st.text_input("Department", key="reg_dept")
                username = st.text_input("Faculty ID / Email", key="reg_user")
                password = st.text_input("Password", type="password", key="reg_pass")
                submit = st.form_submit_button("Create Account")
            if submit:
                ok, message = create_user(username, full_name, department, password)
                if ok:
                    st.success("Account created. You can log in now.")
                else:
                    st.error(message)


def upload_screen():
    left, right = st.columns([1.35, 0.95], gap="large")

    with left:
        st.markdown(
            """
            <div class="hero-wrap">
                <div class="hero-orb orb-a"></div>
                <div class="hero-orb orb-b"></div>
                <h1 class="hero-title">Result File Upload</h1>
                <p class="hero-subtitle">Upload your semester result file to open the dashboard in a cleaner, more modern workspace.</p>
                <span class="hero-badge">Secure Faculty Workspace</span>
                <div class="hero-meta">
                    <span>Fast upload</span>
                    <span>Clean interface</span>
                    <span>Same logic</span>
                </div>
            </div>
            <div class="mini-note">A bolder background and simpler layout keep the page professional without making the upload screen feel crowded.</div>
            """,
            unsafe_allow_html=True,
        )

    with right:
        st.markdown(
            """
            <div class="workspace-card">
                <div class="workspace-card__kicker">Secure Intake</div>
                <div class="workspace-card__title">Upload semester workbook</div>
                <div class="workspace-card__text">Drop the latest Excel result sheet here and move straight into the dashboard.</div>
                <div class="workspace-card__stats">
                    <div class="workspace-stat">
                        <div class="workspace-stat__value">.xlsx</div>
                        <div class="workspace-stat__label">Accepted format</div>
                    </div>
                    <div class="workspace-stat">
                        <div class="workspace-stat__value">200MB</div>
                        <div class="workspace-stat__label">Max file size</div>
                    </div>
                    <div class="workspace-stat">
                        <div class="workspace-stat__value">1 step</div>
                        <div class="workspace-stat__label">Quick start</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        uploaded_file = st.file_uploader(
            "Upload semester result Excel file",
            type=["xlsx"],
            label_visibility="collapsed",
        )
        st.markdown(
            """
            <div class="mini-note">Best results come from a clean semester workbook with at least one ready-to-analyze sheet. You can replace the file later without logging out.</div>
            """,
            unsafe_allow_html=True,
        )

    if uploaded_file is None:
        return
    st.session_state["uploaded_file_bytes"] = uploaded_file.getvalue()
    st.session_state["uploaded_filename"] = uploaded_file.name
    st.session_state["engine_cache"] = None
    st.session_state["engine_signature"] = ""
    st.session_state["profile_source_signature"] = None
    clear_summary_filter_state()
    save_session_upload(
        st.session_state.get("session_token", ""),
        uploaded_file.name,
        st.session_state["uploaded_file_bytes"],
    )
    st.success("File uploaded. Redirecting to the analysis dashboard...")
    st.rerun()


def donut_chart(data, label_col, value_col, title, colors):
    spec = {
        "mark": {"type": "arc", "innerRadius": 52, "cornerRadius": 3},
        "encoding": {
            "theta": {"field": value_col, "type": "quantitative"},
            "color": {
                "field": label_col,
                "type": "nominal",
                "scale": {"range": colors},
                "legend": {"title": None},
            },
            "tooltip": [
                {"field": label_col, "type": "nominal", "title": "Category"},
                {"field": value_col, "type": "quantitative", "title": "Count"},
            ],
        },
        "title": title,
    }
    st.vega_lite_chart(data, spec, use_container_width=True)


def failed_bar(data, theme):
    chart_data = data.copy()
    chart_data["failed"] = pd.to_numeric(chart_data["failed"], errors="coerce").fillna(0)
    chart_data["failed_label"] = chart_data["failed"].map(lambda value: str(int(value)))
    chart_data["bar_state"] = chart_data["failed"].map(lambda value: "zero" if float(value) == 0 else "nonzero")

    max_failed = float(chart_data["failed"].max()) if not chart_data.empty else 0.0
    zero_stub = 0.6 if max_failed == 0 else max(0.35, round(max_failed * 0.06, 2))
    chart_data["failed_visual"] = chart_data["failed"].where(chart_data["failed"] > 0, zero_stub)
    chart_data["label_y"] = chart_data["failed_visual"]
    domain_max = max(1.0, float(chart_data["failed_visual"].max()) + max(0.4, max_failed * 0.15))
    if max_failed == 0:
        st.caption("All selected subjects currently have 0 failed students.")

    tooltip = [
        {"field": "subject_name", "type": "nominal", "title": "Subject"},
        {"field": "course_code", "type": "nominal", "title": "Course Code"},
        {"field": "appeared", "type": "quantitative", "title": "Appeared"},
        {"field": "failed", "type": "quantitative", "title": "Failed"},
        {"field": "pass_percent", "type": "quantitative", "title": "Pass %"},
    ]
    spec = {
        "layer": [
            {
                "mark": {"type": "bar", "cornerRadiusTopLeft": 5, "cornerRadiusTopRight": 5},
                "encoding": {
                    "x": {"field": "subject", "type": "nominal", "sort": "-y", "axis": {"labelAngle": -35, "title": None}},
                    "y": {
                        "field": "failed_visual",
                        "type": "quantitative",
                        "title": "Failed Students",
                        "scale": {"domain": [0, domain_max], "nice": False},
                        "axis": {"tickMinStep": 1},
                    },
                    "color": {
                        "field": "bar_state",
                        "type": "nominal",
                        "scale": {"domain": ["zero", "nonzero"], "range": ["#efb0a5", theme["danger"]]},
                        "legend": None,
                    },
                    "opacity": {"value": 0.9},
                    "tooltip": tooltip,
                },
            },
            {
                "mark": {"type": "point", "filled": True, "size": 90, "color": theme["danger"]},
                "encoding": {
                    "x": {"field": "subject", "type": "nominal", "sort": "-y", "axis": None},
                    "y": {
                        "field": "label_y",
                        "type": "quantitative",
                        "scale": {"domain": [0, domain_max], "nice": False},
                        "axis": None,
                    },
                    "tooltip": tooltip,
                },
            },
            {
                "mark": {"type": "text", "dy": -10, "fontSize": 12, "fontWeight": 700, "color": theme["danger"]},
                "encoding": {
                    "x": {"field": "subject", "type": "nominal", "sort": "-y", "axis": None},
                    "y": {
                        "field": "label_y",
                        "type": "quantitative",
                        "scale": {"domain": [0, domain_max], "nice": False},
                        "axis": None,
                    },
                    "text": {"field": "failed_label", "type": "nominal"},
                },
            },
        ],
        "height": 340,
    }
    st.vega_lite_chart(chart_data, spec, use_container_width=True)


def pass_percent_bar(data, theme):
    spec = {
        "mark": {"type": "bar", "cornerRadiusTopLeft": 5, "cornerRadiusTopRight": 5},
        "encoding": {
            "x": {"field": "subject", "type": "nominal", "axis": {"labelAngle": -35, "title": None}, "sort": "-y"},
            "y": {"field": "pass_percent", "type": "quantitative", "title": "Pass Percent", "scale": {"domain": [0, 100]}},
            "color": {
                "field": "pass_percent",
                "type": "quantitative",
                "scale": {"range": ["#e4f3ff", theme["accent"]]},
                "legend": None,
            },
            "tooltip": [
                {"field": "subject_name", "type": "nominal", "title": "Subject"},
                {"field": "course_code", "type": "nominal", "title": "Course Code"},
                {"field": "pass_percent", "type": "quantitative", "title": "Pass %"},
            ],
        },
        "height": 340,
    }
    st.vega_lite_chart(data, spec, use_container_width=True)


def build_zip(insights_df, insight_report, subject_df, matrix_df, toppers_df):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("insights_report.txt", insight_report or "")
        zf.writestr("insights_table.csv", insights_df.to_csv(index=False))
        zf.writestr("subject_analysis.csv", subject_df.to_csv(index=False))
        zf.writestr("student_matrix.csv", matrix_df.to_csv(index=False))
        if toppers_df is not None and not toppers_df.empty:
            zf.writestr("toppers.csv", toppers_df.to_csv(index=False))
    buffer.seek(0)
    return buffer.getvalue()


def data_quality(df, roll_col, sgpa_col, subject_df):
    rows, cols = df.shape
    total_cells = rows * cols
    missing_cells = int(df.isna().sum().sum()) if total_cells else 0
    completeness = 100.0 if total_cells == 0 else round(((total_cells - missing_cells) / total_cells) * 100, 2)
    dup_prn = 0
    if roll_col and roll_col in df.columns and not df.empty:
        dup_prn = int(df[roll_col].duplicated().sum())
    miss_sgpa = 0
    if sgpa_col and sgpa_col in df.columns and not df.empty:
        miss_sgpa = int(pd.to_numeric(df[sgpa_col], errors="coerce").isna().sum())
    return {
        "rows": int(rows),
        "columns": int(cols),
        "missing_cells": int(missing_cells),
        "completeness": float(completeness),
        "duplicate_prn": int(dup_prn),
        "missing_sgpa": int(miss_sgpa),
        "subjects_detected": int(len(subject_df)),
    }


def build_insights(overview, subject_df, matrix_df, dq, risk_threshold):
    items = []

    def add(priority, area, insight, metric, rec):
        items.append({"Priority": priority, "Area": area, "Insight": insight, "Metric": metric, "Recommendation": rec})

    pass_pct = float(overview.get("pass_percent", 0.0))
    if pass_pct < 70:
        add("High", "Overall Outcome", "Class pass percentage is in risk zone.", f"Pass % = {pass_pct:.2f}", "Start immediate remedial support.")
    elif pass_pct < 85:
        add("Medium", "Overall Outcome", "Class pass percentage is moderate.", f"Pass % = {pass_pct:.2f}", "Target weak subjects and monitor weekly.")
    else:
        add("Low", "Overall Outcome", "Class pass percentage is strong.", f"Pass % = {pass_pct:.2f}", "Push mid-band students to higher grade bands.")

    if not subject_df.empty:
        weak = subject_df.loc[subject_df["pass_percent"].idxmin()]
        best = subject_df.loc[subject_df["pass_percent"].idxmax()]
        weak_priority = "High" if float(weak["pass_percent"]) < 85 else "Medium"
        add(
            weak_priority,
            "Subject Risk",
            f"Weakest subject is {weak['subject_name']} ({weak['course_code']}).",
            f"Pass % = {float(weak['pass_percent']):.2f} | Failed = {int(weak['failed'])}",
            "Run topic-level intervention for this subject.",
        )
        add(
            "Info",
            "Subject Strength",
            f"Strongest subject is {best['subject_name']} ({best['course_code']}).",
            f"Pass % = {float(best['pass_percent']):.2f}",
            "Replicate successful methods from this subject.",
        )
    else:
        add(
            "Info",
            "Subject Coverage",
            "Subject-level result columns were not detected.",
            "Subjects detected = 0",
            "Upload a sheet with subject result indicators (P/F or equivalent).",
        )

    if not matrix_df.empty and matrix_df["SGPA"].notna().any():
        risk_count = int((matrix_df["SGPA"] < risk_threshold).sum())
        high_perf = int((matrix_df["SGPA"] >= 8.0).sum())
        risk_priority = "High" if risk_count > 0 else "Low"
        add(
            risk_priority,
            "At-Risk Students",
            "Students below configured SGPA threshold identified.",
            f"Threshold = {risk_threshold:.1f} | Count = {risk_count}",
            "Create mentoring batches and assign weak-subject tutors.",
        )
        add("Info", "High Performers", "Distinction-level students identified.", f"SGPA >= 8.0 | Count = {high_perf}", "Use toppers as peer mentors.")
        grade_dist = matrix_df["Grade"].fillna("-").value_counts().head(5)
        add(
            "Info",
            "Grade Pattern",
            "Grade distribution trend extracted.",
            ", ".join([f"{g}:{int(c)}" for g, c in grade_dist.items()]),
            "Track whether B+/A students can move to A+/O.",
        )

    dq_priority = "Low" if dq["completeness"] >= 95 else "Medium"
    add(
        dq_priority,
        "Data Quality",
        "Workbook quality assessment completed.",
        f"Completeness = {dq['completeness']:.2f}% | Missing = {dq['missing_cells']} | Duplicate PRN = {dq['duplicate_prn']}",
        "Clean missing and duplicate records for higher confidence.",
    )

    df = pd.DataFrame(items)
    if df.empty:
        return df
    df["_order"] = df["Priority"].map(PRIORITY_ORDER)
    return df.sort_values(["_order", "Area"]).drop(columns=["_order"]).reset_index(drop=True)


def insight_text(insights_df, overview, dq, sheet_name):
    lines = [
        "Academic Result Insight Report",
        f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Workbook Sheet: {sheet_name}",
        "",
        "Overview",
        f"- Total Students: {overview.get('total_students', 0)}",
        f"- Passed: {overview.get('passed', 0)}",
        f"- Failed: {overview.get('failed', 0)}",
        f"- Average SGPA: {overview.get('average_sgpa', 0)}",
        f"- Pass Percent: {overview.get('pass_percent', 0)}",
        "",
        "Data Quality",
        f"- Rows: {dq['rows']}",
        f"- Columns: {dq['columns']}",
        f"- Completeness: {dq['completeness']}%",
        f"- Missing Cells: {dq['missing_cells']}",
        f"- Duplicate PRN: {dq['duplicate_prn']}",
        f"- Subjects Detected: {dq['subjects_detected']}",
        "",
        "Insights",
    ]
    if insights_df.empty:
        lines.append("- No insights generated.")
    else:
        for idx, row in insights_df.iterrows():
            lines.append(f"{idx + 1}. [{row['Priority']}] {row['Area']}: {row['Insight']}")
            lines.append(f"   Metric: {row['Metric']}")
            lines.append(f"   Recommendation: {row['Recommendation']}")
    return "\n".join(lines)


def build_term_context(
    engine,
    term_key,
    risk_threshold,
    top_n,
    matrix_statuses,
    show_only_failed,
    student_search,
    sheet_name,
    selected_summary_filter="",
):
    term_label = engine.get_term_label(term_key) if term_key else "All Terms"
    selected_summary_filter = normalize_summary_filter(selected_summary_filter)
    active_mask = engine.get_term_active_mask(term_key) if term_key else pd.Series(True, index=engine.df.index)
    df_active = engine.df.loc[active_mask].copy()

    sgpa_col = engine.get_term_sgpa_col(term_key) if term_key else engine.sgpa_col
    grade_col = engine.get_term_grade_col(term_key) if term_key else engine.grade_col

    overview = engine.get_class_overview(term_key)
    subject_df = engine.get_subject_analysis(term_key)
    matrix = engine.get_student_matrix(term_key)
    toppers = engine.get_class_toppers(top_n, term_key)
    grade_summary = engine.get_class_grade_summary(term_key)
    grade_df = engine.get_subject_grade_distribution(term_key)

    sgpa_series = pd.Series(dtype=float)
    if sgpa_col and sgpa_col in df_active.columns:
        sgpa_series = pd.to_numeric(df_active[sgpa_col], errors="coerce")

    roll_series = df_active[engine.roll_col].astype(str) if not df_active.empty else pd.Series(dtype=str)
    sgpa_map = dict(zip(roll_series, sgpa_series))

    if grade_col and grade_col in df_active.columns:
        grade_map = dict(zip(roll_series, df_active[grade_col].astype(str).str.strip()))
    else:
        grade_map = {roll: grade_from_sgpa(sgpa) for roll, sgpa in sgpa_map.items()}

    matrix_rows = []
    for roll, data in matrix.items():
        sgpa = sgpa_map.get(str(roll))
        matrix_rows.append(
            {
                "Student Name": data["name"],
                "PRN No": str(roll),
                "Status": "Passed" if data["passed_all"] else "Failed",
                "Failed Subjects": ", ".join(data["failed_subjects"]) if data["failed_subjects"] else "-",
                "SGPA": None if pd.isna(sgpa) else float(round(sgpa, 2)),
                "Grade": grade_map.get(str(roll), "-"),
            }
        )

    matrix_df = pd.DataFrame(matrix_rows)
    if matrix_df.empty:
        matrix_df = pd.DataFrame(
            columns=["Student Name", "PRN No", "Status", "Failed Subjects", "SGPA", "Grade"]
        )
    else:
        matrix_df = matrix_df[["Student Name", "PRN No", "Status", "Failed Subjects", "SGPA", "Grade"]]

    filtered_matrix_df = apply_student_filters(
        matrix_df,
        student_search=student_search,
        matrix_statuses=matrix_statuses,
        show_only_failed=show_only_failed,
    )
    summary_matrix_df = apply_student_filters(
        matrix_df,
        student_search=student_search,
        summary_filter=selected_summary_filter,
        ignore_status_filters=True,
    )
    student_view_df = summary_matrix_df if selected_summary_filter else filtered_matrix_df

    excluded_df = pd.DataFrame(columns=["PRN No", "Student Name"])
    if term_key:
        excluded_mask = ~active_mask
        if excluded_mask.any():
            excluded_df = engine.df.loc[excluded_mask, [engine.roll_col, engine.name_col]].copy()
            excluded_df.rename(
                columns={engine.roll_col: "PRN No", engine.name_col: "Student Name"}, inplace=True
            )

    term_cols = engine.get_term_columns(term_key) if term_key else list(engine.df.columns)
    quality_cols = [c for c in term_cols if c in engine.df.columns]
    for col in [engine.roll_col, engine.name_col, sgpa_col, grade_col]:
        if col and col in engine.df.columns and col not in quality_cols:
            quality_cols.insert(0, col)
    df_quality = engine.df.loc[active_mask, quality_cols] if not engine.df.empty else engine.df

    dq = data_quality(df_quality, engine.roll_col, sgpa_col, subject_df)
    insight_descriptor = f"{sheet_name} | {term_label}" if term_key else sheet_name
    insights_df = build_insights(overview, subject_df, matrix_df, dq, risk_threshold)
    insight_report = insight_text(insights_df, overview, dq, insight_descriptor)

    return {
        "engine": engine,
        "term_key": term_key,
        "term_label": term_label,
        "sheet_name": sheet_name,
        "overview": overview,
        "subject_df": subject_df,
        "matrix_df": matrix_df,
        "filtered_matrix_df": filtered_matrix_df,
        "summary_matrix_df": summary_matrix_df,
        "student_view_df": student_view_df,
        "selected_summary_filter": selected_summary_filter,
        "summary_filter_state_key": get_summary_filter_state_key(term_key),
        "toppers": toppers,
        "grade_summary": grade_summary,
        "grade_df": grade_df,
        "dq": dq,
        "insights_df": insights_df,
        "insight_report": insight_report,
        "sgpa_series": sgpa_series,
        "sgpa_col": sgpa_col,
        "grade_col": grade_col,
        "excluded_df": excluded_df,
        "result_cols_count": len(engine.get_result_columns(term_key)),
        "active_count": int(len(df_active)),
    }


def render_history_panel(key_suffix="history"):
    st.markdown("<div class='section-kicker'>Analysis History</div>", unsafe_allow_html=True)
    history_df = fetch_history(st.session_state["user"]["id"])
    if history_df.empty:
        st.info("No history yet. Upload a file to create your first record.")
        return

    history_df = history_df.copy()
    if "uploaded_at" in history_df.columns:
        history_df["uploaded_at"] = pd.to_datetime(history_df["uploaded_at"], errors="coerce")
        history_df = history_df.sort_values("uploaded_at", ascending=False)
        history_df["uploaded_at"] = history_df["uploaded_at"].dt.strftime("%Y-%m-%d %H:%M")
    history_df.rename(
        columns={
            "uploaded_at": "Uploaded At",
            "filename": "File",
            "sheet_name": "Sheet",
            "total_students": "Total Students",
            "passed": "Passed",
            "failed": "Failed",
            "pass_percent": "Pass %",
            "average_sgpa": "Average SGPA",
            "institution": "Institution",
            "department": "Department",
            "class_name": "Class",
            "semester": "Semester",
            "academic_year": "Academic Year",
        },
        inplace=True,
    )
    st.dataframe(history_df, use_container_width=True)
    st.download_button(
        "Download History CSV",
        data=history_df.to_csv(index=False).encode("utf-8"),
        file_name="analysis_history.csv",
        mime="text/csv",
        key=f"history_csv_{key_suffix}",
    )


def render_term_tabs(ctx, theme, risk_threshold):
    engine = ctx["engine"]
    term_key = ctx["term_key"]
    term_label = ctx["term_label"]
    overview = ctx["overview"]
    subject_df = ctx["subject_df"]
    grade_df = ctx["grade_df"]
    grade_summary = ctx["grade_summary"]
    matrix_df = ctx["matrix_df"]
    filtered_matrix_df = ctx["filtered_matrix_df"]
    summary_matrix_df = ctx["summary_matrix_df"]
    student_view_df = ctx["student_view_df"]
    selected_summary_filter = ctx["selected_summary_filter"]
    summary_filter_state_key = ctx["summary_filter_state_key"]
    toppers = ctx["toppers"]
    dq = ctx["dq"]
    insights_df = ctx["insights_df"]
    insight_report = ctx["insight_report"]
    sgpa_series = ctx["sgpa_series"]
    sgpa_col = ctx["sgpa_col"]
    excluded_df = ctx["excluded_df"]

    key_suffix = term_key if term_key else "all"

    if not excluded_df.empty:
        st.warning(f"{len(excluded_df)} students have no {term_label} data and were excluded from this term.")
        with st.expander("View excluded students", expanded=False):
            st.dataframe(excluded_df, use_container_width=True)

    sheet_name = ctx["sheet_name"]
    avg_sgpa = overview.get("average_sgpa", 0.0)
    if not matrix_df.empty and matrix_df["SGPA"].notna().any():
        distinction = int((matrix_df["SGPA"] >= 8).sum())
        at_risk = int((matrix_df["SGPA"] < risk_threshold).sum())
    else:
        distinction = 0
        at_risk = 0
    summary_cards = [
        ("total", "Total Students", overview.get("total_students", 0), "Open the full cohort list.", theme["accent"]),
        ("passed", "Passed", overview.get("passed", 0), "Students who cleared all subjects.", theme["success"]),
        ("failed", "Failed", overview.get("failed", 0), "Students who need quick attention.", theme["danger"]),
    ]

    st.markdown("<div class='section-kicker'>Quick Cohort Drill Down</div>", unsafe_allow_html=True)
    card_cols = st.columns(3)
    for col, (filter_key, title, value, hint, accent_color) in zip(card_cols, summary_cards):
        active = selected_summary_filter == filter_key
        with col:
            st.markdown(
                f"""
                <div class="summary-tile {'summary-tile-active' if active else ''}" style="--summary-accent: {accent_color};">
                    <div class="summary-tile__label">{title}</div>
                    <div class="summary-tile__value">{value}</div>
                    <div class="summary-tile__hint">{hint}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(
                "Viewing Students" if active else f"Show {title}",
                key=f"summary_drill_{filter_key}_{key_suffix}",
                use_container_width=True,
                type="primary" if active else "secondary",
            ):
                st.session_state[summary_filter_state_key] = filter_key
                st.rerun()

    k4, k5, k6 = st.columns(3)
    k4.metric("Average SGPA", "-" if not sgpa_col else avg_sgpa)
    k5.metric("Pass %", f"{overview.get('pass_percent', 0.0)}%")
    k6.metric("Distinction", distinction)
    st.markdown(
        f"<div class='mini-note'>Sheet: <strong>{sheet_name}</strong> | Term: <strong>{term_label}</strong> | "
        f"At-risk threshold: <strong>{risk_threshold:.1f}</strong> | At-risk students: <strong>{at_risk}</strong></div>",
        unsafe_allow_html=True,
    )

    filter_note_col, filter_action_col = st.columns([5, 1])
    with filter_note_col:
        if selected_summary_filter:
            st.markdown(
                f"<div class='mini-note'>Active cohort: <strong>{SUMMARY_FILTER_LABELS[selected_summary_filter]}</strong>. "
                "This drill-down keeps the clicked summary consistent and still respects the student search box.</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div class='mini-note'>Click any summary card above to instantly open that student group in a cleaner drill-down view.</div>",
                unsafe_allow_html=True,
            )
    with filter_action_col:
        if selected_summary_filter and st.button(
            "Clear View",
            key=f"clear_summary_view_{key_suffix}",
            use_container_width=True,
        ):
            st.session_state[summary_filter_state_key] = ""
            st.rerun()

    if selected_summary_filter:
        cohort_label = SUMMARY_FILTER_LABELS[selected_summary_filter]
        st.markdown("<div class='section-kicker'>Selected Cohort</div>", unsafe_allow_html=True)
        st.caption(f"Showing {len(summary_matrix_df)} {cohort_label.lower()} for {term_label}.")
        if summary_matrix_df.empty:
            st.info(f"No {cohort_label.lower()} match the current search.")
        else:
            st.dataframe(summary_matrix_df, use_container_width=True)

    overview_tab, subject_tab, grade_tab, student_tab, history_tab, report_tab = st.tabs(
        ["Overview", "Subject Intelligence", "Grade Sheet", "Student Explorer", "History", "Reporting"]
    )

    with overview_tab:
        st.markdown("<div class='section-kicker'>Visual Snapshot</div>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            pass_fail_df = pd.DataFrame({"Category": ["Passed", "Failed"], "Count": [overview.get("passed", 0), overview.get("failed", 0)]})
            donut_chart(pass_fail_df, "Category", "Count", "Pass vs Fail", [theme["success"], theme["danger"]])
        with c2:
            valid_sgpa = sgpa_series.dropna()
            if valid_sgpa.empty:
                st.info("SGPA data unavailable for distribution chart.")
            else:
                bins = [0, 4, 5, 6, 7, 8, 9, 10.000001]
                labels = ["0-4", "4-5", "5-6", "6-7", "7-8", "8-9", "9-10"]
                bucket = pd.cut(valid_sgpa, bins=bins, labels=labels, include_lowest=True, right=False)
                d = bucket.value_counts().reindex(labels, fill_value=0).reset_index()
                d.columns = ["Range", "Students"]
                d = d[d["Students"] > 0]
                if d.empty:
                    st.info("No valid SGPA buckets found.")
                else:
                    donut_chart(d, "Range", "Students", "SGPA Distribution", theme["palette"])

        st.markdown("### Top Students")
        if toppers.empty:
            st.info("No topper data available.")
        else:
            for start in range(0, len(toppers), 3):
                chunk = toppers.iloc[start:start + 3]
                cols = st.columns(len(chunk))
                for idx, (_, row) in enumerate(chunk.iterrows()):
                    rank = start + idx + 1
                    sgpa_val = "-"
                    if sgpa_col and sgpa_col in toppers.columns:
                        raw_val = row[sgpa_col]
                        sgpa_val = "-" if pd.isna(raw_val) else raw_val
                    with cols[idx]:
                        st.markdown(
                            f"""
                            <div class="topper-card" style="border-top: 4px solid {theme['palette'][rank % len(theme['palette'])]};">
                                <p class="topper-rank">Rank {rank}</p>
                                <p class="topper-name">{row[engine.name_col]}</p>
                                <div>PRN: {row[engine.roll_col]}</div>
                                <div>SGPA: {sgpa_val}</div>
                                <div>Grade: {row['grade']}</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
        with st.expander("Detected Schema", expanded=False):
            st.write(
                {
                    "Roll Column": engine.roll_col,
                    "Name Column": engine.name_col,
                    "SGPA Column": sgpa_col or "-",
                    "Grade Column": ctx.get("grade_col") or "-",
                    "Detected Subject Results": ctx["result_cols_count"],
                }
            )

    with subject_tab:
        st.markdown("<div class='section-kicker'>Subject Health</div>", unsafe_allow_html=True)
        if subject_df.empty:
            st.warning("No subject-level pass/fail columns detected in this file.")
        else:
            subject_work = subject_df.copy()
            h1, h2 = st.columns([2, 1])
            with h1:
                st.caption("Showing all detected subjects.")
            with h2:
                sort_mode = st.selectbox(
                    "Sort Subjects By",
                    ["Pass Percent (High to Low)", "Pass Percent (Low to High)", "Failed (High to Low)"],
                    index=0,
                    key=f"sort_subjects_{key_suffix}",
                )
            if sort_mode == "Pass Percent (High to Low)":
                subject_work = subject_work.sort_values("pass_percent", ascending=False)
            elif sort_mode == "Pass Percent (Low to High)":
                subject_work = subject_work.sort_values("pass_percent", ascending=True)
            else:
                subject_work = subject_work.sort_values("failed", ascending=False)

            hard = subject_work.loc[subject_work["pass_percent"].idxmin()]
            best = subject_work.loc[subject_work["pass_percent"].idxmax()]
            s1, s2, s3 = st.columns(3)
            s1.metric("Subjects in View", len(subject_work))
            s2.metric("Average Subject Pass %", f"{float(subject_work['pass_percent'].mean()):.2f}%")
            s3.metric("Needs Improvement", f"{hard['subject_name']} ({hard['course_code']})")

            c1, c2 = st.columns(2)
            with c1:
                failed_bar(subject_work, theme)
            with c2:
                pass_percent_bar(subject_work, theme)

            st.markdown(
                f"<span class='chip'>Best Pass %: {best['subject_name']} ({best['course_code']}) - {best['pass_percent']}%</span>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<span class='chip'>Needs Attention: {hard['subject_name']} ({hard['course_code']}) - {hard['pass_percent']}%</span>",
                unsafe_allow_html=True,
            )

            table = subject_work[
                ["subject_name", "course_code", "appeared", "failed", "pass_percent", "topper_name", "topper_prn", "topper_marks"]
            ].copy()
            table.columns = [
                "Subject Name",
                "Course Code",
                "Appeared Students",
                "Failed",
                "Pass Percent",
                "Topper Name",
                "Topper PRN No",
                "Topper Marks",
            ]
            table["Pass Percent"] = table["Pass Percent"].map(lambda v: f"{float(v):.2f}%")
            table["Topper Marks"] = table["Topper Marks"].map(lambda v: "-" if pd.isna(v) else f"{float(v):.2f}")
            st.dataframe(table, use_container_width=True)

    with grade_tab:
        st.markdown("<div class='section-kicker'>Grade Sheet</div>", unsafe_allow_html=True)
        if grade_df.empty:
            st.warning("No grade distribution could be derived from this file.")
        else:
            g1, g2, g3, g4, g5, g6 = st.columns(6)
            g1.metric("Total Students", grade_summary.get("total_students", 0))
            g2.metric("Distinction", grade_summary.get("distinction", 0))
            g3.metric("First Class", grade_summary.get("first_class", 0))
            g4.metric("Second Class", grade_summary.get("second_class", 0))
            g5.metric("Passed", grade_summary.get("passed", 0))
            g6.metric("ATKT", grade_summary.get("failed", 0))

            g7, g8, g9, g10 = st.columns(4)
            g7.metric("Failed (Overall)", grade_summary.get("overall_failed", 0))
            g8.metric("Pass %", f"{float(grade_summary.get('pass_percent', 0.0)):.2f}%")
            g9.metric("Pass % With ATKT", f"{float(grade_summary.get('pass_with_atkt', 0.0)):.2f}%")
            g10.metric("Total Appeared", grade_summary.get("total_students", 0))

            display_df = grade_df.copy()
            if "before_remedial_result" in display_df.columns:
                display_df["before_remedial_result"] = display_df["before_remedial_result"].apply(
                    lambda v: "NA" if pd.isna(v) else f"{float(v):.2f}%"
                )
            display_df.rename(
                columns={
                    "subject": "Subject",
                    "faculty": "Name of Faculty",
                    "total": "Total",
                    "appeared": "Appeared",
                    "passed": "Pass",
                    "failed": "Fail",
                    "not_appeared": "Not Appeared",
                    "before_remedial_result": "Before Remedial Result",
                    "O": "O",
                    "A++": "A++",
                    "A+": "A+",
                    "A": "A",
                    "AB": "AB",
                    "B+": "B+",
                    "B": "B",
                    "C+": "C+",
                    "C": "C",
                    "D": "D",
                    "F": "F/Fail",
                },
                inplace=True,
            )
            st.dataframe(display_df, use_container_width=True)

    with student_tab:
        st.markdown("<div class='section-kicker'>Student Drill Down</div>", unsafe_allow_html=True)
        if selected_summary_filter:
            st.caption(
                f"Explorer synced to {SUMMARY_FILTER_LABELS[selected_summary_filter].lower()}. "
                "Sidebar status filters are bypassed while this cohort view is active."
            )
        st.dataframe(student_view_df, use_container_width=True)
        if student_view_df.empty:
            if selected_summary_filter:
                st.info(f"No {SUMMARY_FILTER_LABELS[selected_summary_filter].lower()} match the current search.")
            else:
                st.info("No students match current filters.")
        else:
            st.markdown("### Individual Student Profile")
            option_map = {
                f"{row['Student Name']} ({row['PRN No']})": row["PRN No"]
                for _, row in student_view_df.drop_duplicates(subset=["PRN No"]).iterrows()
            }
            label = st.selectbox("Select Student", list(option_map.keys()), key=f"student_{key_suffix}")
            prn = option_map[label]
            row = student_view_df[student_view_df["PRN No"] == prn].iloc[0]
            p1, p2, p3 = st.columns(3)
            p1.metric("Student", row["Student Name"])
            p2.metric("Status", row["Status"])
            p3.metric("SGPA", "-" if pd.isna(row["SGPA"]) else row["SGPA"])

            detail_df = engine.get_student_subject_report(prn, term_key)
            if detail_df.empty:
                st.info("No subject-level details found for this student.")
            else:
                details = detail_df[["subject_name", "course_code", "result", "marks"]].copy()
                details.columns = ["Subject Name", "Course Code", "Result", "Marks"]
                details["Marks"] = details["Marks"].map(lambda v: "-" if pd.isna(v) else f"{float(v):.2f}")
                st.dataframe(details, use_container_width=True)

    with history_tab:
        render_history_panel(key_suffix)

    with report_tab:
        st.markdown("<div class='section-kicker'>Exports and Reporting</div>", unsafe_allow_html=True)
        st.write("Download structured outputs or full report package.")

        c1, c2, c3 = st.columns(3)
        with c1:
            st.download_button(
                "Download Insights CSV",
                data=insights_df.to_csv(index=False).encode("utf-8"),
                file_name=f"insights_table_{key_suffix}.csv",
                mime="text/csv",
                key=f"insights_csv_{key_suffix}",
            )
        with c2:
            st.download_button(
                "Download Insights TXT",
                data=insight_report.encode("utf-8"),
                file_name=f"insights_report_{key_suffix}.txt",
                mime="text/plain",
                key=f"insights_txt_{key_suffix}",
            )
        with c3:
            st.download_button(
                "Download Subject Analysis CSV",
                data=subject_df.to_csv(index=False).encode("utf-8"),
                file_name=f"subject_analysis_{key_suffix}.csv",
                mime="text/csv",
                key=f"subject_csv_{key_suffix}",
            )

        st.download_button(
            "Download Full Analysis Bundle (ZIP)",
            data=build_zip(insights_df, insight_report, subject_df, student_view_df, toppers),
            file_name=f"analysis_bundle_{key_suffix}.zip",
            mime="application/zip",
            key=f"bundle_zip_{key_suffix}",
        )

        st.divider()

        if st.button("Generate Excel Report", key=f"excel_report_{key_suffix}"):
            report_semester = term_label if term_key else st.session_state.get("semester_name", "")
            report_slug = re.sub(r"[^A-Za-z0-9]+", "_", report_semester).strip("_") or key_suffix
            report = ReportGenerator(
                engine,
                university=st.session_state.get("institution_name", ""),
                department=st.session_state.get("department_name", ""),
                semester=report_semester,
                academic_year=st.session_state.get("academic_year_name", ""),
                class_name=st.session_state.get("class_name", ""),
                term_key=term_key,
                top_n=top_n,
            )
            output_file = f"Final_Result_Report_{report_slug}.xlsx"
            report.generate_report(output_file)
            st.success("Excel report generated successfully.")
            with open(output_file, "rb") as file:
                st.download_button(
                    label="Download Full Excel Report",
                    data=file,
                    file_name=output_file,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"excel_download_{key_suffix}",
                )

ensure_db()
if "user" not in st.session_state:
    st.session_state["user"] = None
if "session_token" not in st.session_state:
    st.session_state["session_token"] = ""
if "uploaded_file_bytes" not in st.session_state:
    st.session_state["uploaded_file_bytes"] = None
if "uploaded_filename" not in st.session_state:
    st.session_state["uploaded_filename"] = ""
if "engine_cache" not in st.session_state:
    st.session_state["engine_cache"] = None
if "engine_signature" not in st.session_state:
    st.session_state["engine_signature"] = ""

if st.session_state["user"] is None:
    token = get_query_param("session")
    if token:
        restored_user = get_user_by_session(token)
        if restored_user:
            st.session_state["user"] = restored_user
            st.session_state["session_token"] = token
            filename, file_bytes = load_session_upload(token)
            if file_bytes:
                st.session_state["uploaded_file_bytes"] = file_bytes
                st.session_state["uploaded_filename"] = filename or "uploaded.xlsx"

if st.session_state["user"] is None:
    login_screen()
    st.stop()

if not st.session_state.get("uploaded_file_bytes"):
    apply_theme(THEMES[DEFAULT_THEME_NAME])
    upload_screen()
    st.stop()

PROFILE_FALLBACK_DEFAULTS = {
    "institution": "SOET MGM UNIVERSITY",
    "department": "CSE (Integrated)",
    "class_name": "Data Science",
    "semester": "Sem 5",
    "academic_year": "2025-2026",
}

file_bytes = st.session_state.get("uploaded_file_bytes")
uploaded_filename = st.session_state.get("uploaded_filename", "uploaded.xlsx")
if not file_bytes:
    st.session_state["view"] = "upload"
    st.rerun()

hero_col, utility_col = st.columns([1.35, 0.95], gap="large")

with hero_col:
    st.markdown(
        f"""
        <div class="hero-wrap">
            <div class="hero-orb orb-a"></div>
            <div class="hero-orb orb-b"></div>
            <h1 class="hero-title">Academic Result Intelligence Dashboard</h1>
            <p class="hero-subtitle">Auto-detects uploaded workbook schema, builds a cohort digital twin, and turns the workbook into a cleaner, export-ready analytics experience.</p>
            <span class="hero-badge">Interactive Visual Workspace</span>
            <div class="hero-meta">
                <span>Active workbook: {uploaded_filename}</span>
                <span>Live multi-tab analysis</span>
                <span>Export-ready outputs</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with utility_col:
    quick_upload = st.file_uploader(
        "Browse another Excel file",
        type=["xlsx"],
        key="dashboard_uploader_main",
        label_visibility="collapsed",
    )
if quick_upload is not None:
    st.session_state["uploaded_file_bytes"] = quick_upload.getvalue()
    st.session_state["uploaded_filename"] = quick_upload.name
    st.session_state["engine_cache"] = None
    st.session_state["engine_signature"] = ""
    st.session_state["profile_source_signature"] = None
    clear_summary_filter_state()
    save_session_upload(
        st.session_state.get("session_token", ""),
        quick_upload.name,
        st.session_state["uploaded_file_bytes"],
    )
    file_bytes = st.session_state["uploaded_file_bytes"]
    uploaded_filename = st.session_state["uploaded_filename"]
    st.success("New file loaded. Analyzing...")

try:
    workbook = pd.ExcelFile(io.BytesIO(file_bytes))
except Exception:
    st.error("Unable to open this Excel file. Please upload a valid workbook.")
    st.stop()

with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-brand">
            <div class="sidebar-brand__kicker">Faculty Command Center</div>
            <div class="sidebar-brand__title">Result Analysis Dashboard</div>
            <div class="sidebar-brand__text">Tune the visual theme, filters, workbook choices, and reporting session from one place.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<div class='sidebar-section-title'>Workspace Settings</div>", unsafe_allow_html=True)
    theme_name = st.selectbox(
        "Visual Theme",
        list(THEMES.keys()),
        index=list(THEMES.keys()).index(DEFAULT_THEME_NAME),
    )
    top_n = st.slider("Top Students to Highlight", min_value=3, max_value=10, value=3)
    risk_threshold = st.slider("At-Risk SGPA Threshold", min_value=4.0, max_value=8.0, value=6.0, step=0.1)
    show_only_failed = st.toggle("Show Only Failed in Matrix", value=False)
    matrix_statuses = st.multiselect("Matrix Status Filter", ["Passed", "Failed"], default=["Passed", "Failed"])
    student_search = st.text_input("Search Student (Name or PRN)", "").strip()

    st.markdown("<div class='sidebar-section-title'>Workbook</div>", unsafe_allow_html=True)
    sheet_name = st.selectbox("Workbook Sheet", workbook.sheet_names, index=0)
    detected_details = extract_academic_details(file_bytes, sheet_name)
    auto_detect_profile = st.toggle("Auto-detect Academic Profile", value=True)

    detected_profile = {
        "institution": detected_details.get("institution", "").strip(),
        "department": detected_details.get("department", "").strip(),
        "class_name": detected_details.get("class_name", "").strip(),
        "semester": normalize_semester(detected_details.get("semester", "")),
        "academic_year": normalize_academic_year(detected_details.get("academic_year", "")),
    }

    profile_defaults = {
        "institution": detected_profile["institution"] or PROFILE_FALLBACK_DEFAULTS["institution"],
        "department": detected_profile["department"] or PROFILE_FALLBACK_DEFAULTS["department"],
        "class_name": detected_profile["class_name"] or PROFILE_FALLBACK_DEFAULTS["class_name"],
        "semester": detected_profile["semester"] or PROFILE_FALLBACK_DEFAULTS["semester"],
        "academic_year": detected_profile["academic_year"] or PROFILE_FALLBACK_DEFAULTS["academic_year"],
    }

    apply_detected = st.button(
        "Apply Detected Profile",
        disabled=not auto_detect_profile,
        use_container_width=True,
    )

    source_signature = f"{uploaded_filename}:{sheet_name}:{profile_defaults}"
    first_load_for_source = st.session_state.get("profile_source_signature") != source_signature
    if first_load_for_source or (auto_detect_profile and apply_detected):
        st.session_state["institution_name"] = profile_defaults["institution"]
        st.session_state["department_name"] = profile_defaults["department"]
        st.session_state["class_name"] = profile_defaults["class_name"]
        st.session_state["semester_name"] = profile_defaults["semester"]
        st.session_state["academic_year_name"] = profile_defaults["academic_year"]
        st.session_state["profile_source_signature"] = source_signature

    st.markdown("<div class='sidebar-section-title'>Academic Profile</div>", unsafe_allow_html=True)
    st.caption("Auto mode reads metadata from sheet. You can still edit fields manually anytime.")
    institution_name = st.text_input("Institution", key="institution_name")
    department_name = st.text_input("Department", key="department_name")
    class_name = st.text_input("Class / Program", key="class_name")
    semester_name = st.text_input("Semester", key="semester_name")
    academic_year_name = st.text_input("Academic Year", key="academic_year_name")

    st.markdown("<div class='sidebar-section-title'>Session</div>", unsafe_allow_html=True)
    st.markdown(
        f"<div class='sidebar-session-chip'>Signed in as <strong>{st.session_state['user']['name']}</strong></div>",
        unsafe_allow_html=True,
    )
    if st.session_state["user"].get("department"):
        st.caption(st.session_state["user"]["department"])
    if st.button("Logout", use_container_width=True):
        delete_session_upload(st.session_state.get("session_token"))
        delete_session(st.session_state.get("session_token"))
        st.session_state["user"] = None
        st.session_state["session_token"] = ""
        st.session_state["uploaded_file_bytes"] = None
        st.session_state["uploaded_filename"] = ""
        st.session_state["engine_cache"] = None
        st.session_state["engine_signature"] = ""
        clear_summary_filter_state()
        clear_query_params()
        st.rerun()

theme = THEMES[theme_name]
apply_theme(theme)

engine = None
engine_signature = f"{ENGINE_CACHE_VERSION}:{sha1(file_bytes).hexdigest()}:{sheet_name}" if file_bytes else ""
cached_engine = st.session_state.get("engine_cache")
cached_signature = st.session_state.get("engine_signature")

if cached_engine is not None and cached_signature == engine_signature:
    engine = cached_engine
else:
    try:
        with st.spinner("Analyzing workbook..."):
            engine = ResultEngine(io.BytesIO(file_bytes), sheet_name=sheet_name)
            engine.load_data()
        st.session_state["engine_cache"] = engine
        st.session_state["engine_signature"] = engine_signature
    except Exception as exc:
        st.error("Could not parse this workbook with current schema detection.")
        st.exception(exc)
        st.stop()

overview_global = engine.get_class_overview()
invalid_students = engine.get_invalid_students()

profile_payload = {
    "institution": institution_name,
    "department": department_name,
    "class_name": class_name,
    "semester": semester_name,
    "academic_year": academic_year_name,
}
record_history(
    st.session_state["user"]["id"],
    file_bytes,
    uploaded_filename,
    sheet_name,
    overview_global,
    profile_payload,
)

st.success("File uploaded and analyzed successfully.")
if not invalid_students.empty:
    st.warning(f"{len(invalid_students)} students have blank or missing subject data and were excluded from analysis.")
    with st.expander("View excluded students"):
        st.dataframe(invalid_students, use_container_width=True)
st.markdown(
    f"<div class='profile-ribbon'>"
    f"<span class='chip'>Workbook: {uploaded_filename}</span>"
    f"<span class='chip'>Institution: {institution_name}</span>"
    f"<span class='chip'>Department: {department_name}</span>"
    f"<span class='chip'>Class: {class_name}</span>"
    f"<span class='chip'>Semester: {semester_name}</span>"
    f"<span class='chip'>Academic Year: {academic_year_name}</span>"
    f"</div>",
    unsafe_allow_html=True,
)

terms = engine.get_terms()
if terms:
    term_labels = [engine.get_term_label(t) for t in terms]
    st.caption(f"Detected terms: {', '.join(term_labels)}")
    term_tabs = st.tabs(term_labels)
    for term_key, tab in zip(terms, term_tabs):
        with tab:
            ctx = build_term_context(
                engine,
                term_key,
                risk_threshold,
                top_n,
                matrix_statuses,
                show_only_failed,
                student_search,
                sheet_name,
                st.session_state.get(get_summary_filter_state_key(term_key), ""),
            )
            render_term_tabs(ctx, theme, risk_threshold)
else:
    ctx = build_term_context(
        engine,
        None,
        risk_threshold,
        top_n,
        matrix_statuses,
        show_only_failed,
        student_search,
        sheet_name,
        st.session_state.get(get_summary_filter_state_key(None), ""),
    )
    render_term_tabs(ctx, theme, risk_threshold)
