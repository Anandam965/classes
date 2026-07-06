import os
import uuid
import time
import json
import html
import requests
from datetime import date, timedelta

import streamlit as st
import streamlit.components.v1 as components
from supabase import create_client
import google.generativeai as genai

# =========================
# IMGBB IMAGE UPLOAD
# =========================
def upload_image_to_imgbb(image_file):
    import base64
    try:
        api_key = st.secrets.get("IMGBB_API_KEY", "")
        if not api_key:
            st.error("IMGBB_API_KEY secrets  !")
            return None
        img_data = base64.b64encode(image_file.read()).decode("utf-8")
        response = requests.post("https://api.imgbb.com/1/upload", data={"key": api_key, "image": img_data})
        result = response.json()
        if result.get("success"):
            return result["data"]["url"]
        else:
            st.error(f"Upload failed: {result}")
            return None
    except Exception as e:
        st.error(f"Image upload error: {e}")
        return None

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(page_title="Advanced LMS Portal", layout="wide")

# =========================
# SUPABASE + GEMINI INIT
# =========================
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error("Secrets    . Settings -> Secrets   .")
    st.stop()

try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    pass

# =========================
# SESSION STATES
# =========================
defaults = {
    "logged_in": False,
    "role": "",
    "user_id": "",
    "question_index": 0,
    "answers": {},
    "start_exam": False,
    "exam_submitted": False,
    "exam_id": "",
    "exam_title": "",
    "exam_end_time": 0.0,
    "current_questions": [],
    "completed_ids": None,
    "admin_preview_mode": False,
    "pin_verified": False,
    "pin_setup_mode": False,
    "email_temp": "",
    "user_id_temp": "",
    "role_temp": "",
    "user_page": "My Classes",
    "card_user_page": "Monthly Bill",
    "focus_class_id": "",
    "focus_exam_id": "",
    "question_start_time": {},
    "question_time_log": {},
    "program_run_results": {},
    "program_custom_results": {},
    "program_submissions": {},
    "attendance_marked_date": "",
    "ai_generated_qs": None,
    "last_attempt_id": "",
    "programming_session_loaded": False,
    "malpractice_reported_keys": set(),
    "suprabhatam_index": 0,
    "suprabhatam_language": "Telugu",
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# =========================
# PERSISTENT LOGIN
# =========================
def persist_browser_login():
    if not st.session_state.get("logged_in") or not st.session_state.get("user_id"):
        return
    uid = json.dumps(str(st.session_state.user_id))
    role = json.dumps(str(st.session_state.role))
    components.html(f"""
    <script>
      try {{
        window.parent.localStorage.setItem("lms_saved_uid", {uid});
        window.parent.localStorage.setItem("lms_saved_role", {role});
      }} catch (e) {{}}
    </script>
    """, height=0)


def restore_browser_login_bridge():
    components.html("""
    <script>
      try {
        const url = new URL(window.parent.location.href);
        const hasLogin = url.searchParams.get("uid") && url.searchParams.get("role");
        const uid = window.parent.localStorage.getItem("lms_saved_uid");
        const role = window.parent.localStorage.getItem("lms_saved_role");
        if (!hasLogin && uid && role) {
          url.searchParams.set("uid", uid);
          url.searchParams.set("role", role);
          window.parent.location.replace(url.toString());
        }
      } catch (e) {}
    </script>
    """, height=0)


def show_logout_redirect():
    st.session_state.logged_in = False
    st.session_state.role = ""
    st.session_state.user_id = ""
    try:
        st.query_params.clear()
    except Exception:
        pass
    components.html("""
    <script>
      try {
        window.parent.localStorage.removeItem("lms_saved_uid");
        window.parent.localStorage.removeItem("lms_saved_role");
        window.parent.location.replace(window.parent.location.pathname);
      } catch (e) {
        window.parent.location.reload();
      }
    </script>
    """, height=0)
    st.info("Logging out...")
    st.stop()


def apply_saved_login(saved_uid, saved_role):
    if not saved_uid or not saved_role:
        return False
    try:
        if saved_role == "card_user":
            card_rows = supabase.table("card_users").select("*").eq("id", saved_uid).execute().data
            if card_rows and card_rows[0].get("active", True):
                st.session_state.logged_in = True
                st.session_state.role = "card_user"
                st.session_state.user_id = saved_uid
                st.session_state.pin_verified = True
                return True
        else:
            urow_data = supabase.table("users").select("*").eq("id", saved_uid).execute().data
            if urow_data and urow_data[0]["role"] == saved_role:
                st.session_state.logged_in = True
                st.session_state.role = saved_role
                st.session_state.user_id = saved_uid
                st.session_state.pin_verified = True
                return True
    except Exception:
        pass
    return False


if not st.session_state.logged_in:
    try:
        qp = st.query_params
        saved_uid = qp.get("uid", "")
        saved_role = qp.get("role", "")
        if not apply_saved_login(saved_uid, saved_role):
            restore_browser_login_bridge()
    except Exception:
        pass

# =========================
# PROGRAMMING CODE EVALUATOR
# =========================
def evaluate_java_code(user_code, input_data, expected_output):
    if not st.secrets.get("RAPIDAPI_KEY", ""):
        result = run_java_code(user_code, input_data)
        return result.get("stdout", "").strip() == expected_output.strip()
    url = "https://judge0-ce.p.rapidapi.com/submissions?base64_encoded=false&fields=*"
    payload = {"source_code": user_code, "language_id": 62, "stdin": input_data}
    headers = {"x-rapidapi-key": st.secrets.get("RAPIDAPI_KEY", ""), "Content-Type": "application/json"}
    try:
        response = requests.post(url, json=payload, headers=headers).json()
        token = response.get("token")
        if not token:
            return False
        time.sleep(2)
        result = requests.get(
            f"https://judge0-ce.p.rapidapi.com/submissions/{token}?base64_encoded=false&fields=*",
            headers=headers
        ).json()
        return result.get("stdout", "").strip() == expected_output.strip()
    except Exception:
        return False

PROGRAMMING_LANGUAGES = {
    "java": {
        "label": "Java",
        "wandbox_compiler": "openjdk-jdk-21+35",
        "wandbox_options": "--release=8",
        "file_name": "Main.java",
        "judge0_id": 62,
        "code_language": "java",
        "default_code": """import java.util.*;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        String name = sc.hasNextLine() ? sc.nextLine() : \"Student\";
        System.out.println(\"Hello, \" + name + \"!\");
    }
}""",
    },
    "c": {
        "label": "C",
        "wandbox_compiler": "gcc-13.2.0-c",
        "wandbox_options": "",
        "file_name": "main.c",
        "judge0_id": 50,
        "code_language": "c",
        "default_code": """#include <stdio.h>

int main() {
    char name[100] = \"Student\";
    if (fgets(name, sizeof(name), stdin)) {
        for (int i = 0; name[i] != '\\0'; i++) {
            if (name[i] == '\\n') {
                name[i] = '\\0';
                break;
            }
        }
    }
    printf(\"Hello, %s!\\n\", name);
    return 0;
}""",
    },
    "python": {
        "label": "Python",
        "wandbox_compiler": "cpython-3.10.15",
        "wandbox_options": "",
        "file_name": "main.py",
        "judge0_id": 71,
        "code_language": "python",
        "default_code": """try:
    name = input().strip()
except EOFError:
    name = \"Student\"
print(f\"Hello, {name or 'Student'}!\")""",
    },
}

PROGRAMMING_LANGUAGE_LABELS = {meta["label"]: key for key, meta in PROGRAMMING_LANGUAGES.items()}


def normalize_programming_language(language):
    lang = str(language or "java").strip().lower()
    if lang in ("py", "python3"):
        return "python"
    if lang in ("c", "gcc"):
        return "c"
    return lang if lang in PROGRAMMING_LANGUAGES else "java"


def get_programming_language_meta(language):
    return PROGRAMMING_LANGUAGES[normalize_programming_language(language)]


def compiler_service_unavailable(text):
    raw = str(text or "")
    busy_markers = [
        "Resource temporarily unavailable",
        "OCI runtime error",
        "Too Many Requests",
        "rate limit",
        "temporarily unavailable",
        "Service Unavailable",
        "Bad Gateway",
        "Gateway Timeout",
    ]
    return any(marker.lower() in raw.lower() for marker in busy_markers)


def normalize_compiler_stderr(stderr):
    warning_lines = [
        "warning: [options] source value 8 is obsolete",
        "warning: [options] target value 8 is obsolete",
        "warning: [options] To suppress warnings about obsolete options",
    ]
    return "\n".join(
        line for line in str(stderr or "").splitlines()
        if not any(line.startswith(w) for w in warning_lines) and line.strip() != "3 warnings"
    )


def run_code_with_wandbox(user_code, input_data="", language="java"):
    meta = get_programming_language_meta(language)
    code = user_code
    if normalize_programming_language(language) == "java":
        code = user_code.replace("public class Main", "class Main")
    wandbox_payload = {
        "compiler": meta["wandbox_compiler"],
        "code": code,
        "stdin": input_data or "",
    }
    if meta.get("wandbox_options"):
        wandbox_payload["compiler-option-raw"] = meta["wandbox_options"]
    result = requests.post("https://wandbox.org/api/compile.json", json=wandbox_payload, timeout=40).json()
    stdout = result.get("program_output") or ""
    status_code = str(result.get("status", ""))
    stderr = (
        result.get("compiler_error")
        or result.get("compiler_message")
        or result.get("program_error")
        or result.get("program_message")
        or result.get("message")
        or ""
    )
    stderr = normalize_compiler_stderr(stderr)
    label = meta["label"]
    return {
        "ok": status_code == "0",
        "status": f"Accepted ({label})" if status_code == "0" else f"Error ({label})",
        "stdout": stdout,
        "stderr": stderr,
        "time": None,
        "memory": None,
    }


def run_code_with_judge0_public(user_code, input_data="", language="java"):
    meta = get_programming_language_meta(language)
    url = "https://ce.judge0.com/submissions?base64_encoded=false&fields=*"
    payload = {"source_code": user_code, "language_id": meta["judge0_id"], "stdin": input_data or ""}
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, json=payload, headers=headers, timeout=30).json()
    token = response.get("token")
    if not token:
        return {"ok": False, "status": "Submission failed", "stdout": "", "stderr": str(response), "time": None, "memory": None}
    time.sleep(2)
    result = requests.get(
        f"https://ce.judge0.com/submissions/{token}?base64_encoded=false&fields=*",
        headers=headers,
        timeout=30
    ).json()
    status = (result.get("status") or {}).get("description", "Unknown")
    stdout = result.get("stdout") or ""
    stderr = normalize_compiler_stderr(result.get("stderr") or result.get("compile_output") or result.get("message") or "")
    return {
        "ok": status == "Accepted",
        "status": f"{status} (Judge0 public)",
        "stdout": stdout,
        "stderr": stderr,
        "time": result.get("time"),
        "memory": result.get("memory"),
    }


def run_programming_code(user_code, input_data="", language="java"):
    lang = normalize_programming_language(language)
    if lang == "java":
        return run_java_code(user_code, input_data)

    meta = get_programming_language_meta(lang)
    rapidapi_key = st.secrets.get("RAPIDAPI_KEY", "")
    if not rapidapi_key:
        try:
            result = run_code_with_wandbox(user_code, input_data, lang)
            if result.get("ok") or not compiler_service_unavailable(result.get("stderr")):
                return result
        except Exception as e:
            result = {"stderr": str(e)}
        try:
            fallback = run_code_with_judge0_public(user_code, input_data, lang)
            if fallback.get("stderr"):
                fallback["stderr"] = ("Wandbox busy/error kabatti Judge0 public lo run chesanu.\n" + fallback["stderr"]).strip()
            return fallback
        except Exception as e:
            return {"ok": False, "status": f"{meta['label']} API Error", "stdout": "", "stderr": str(e), "time": None, "memory": None}

    url = "https://judge0-ce.p.rapidapi.com/submissions?base64_encoded=false&fields=*"
    payload = {"source_code": user_code, "language_id": meta["judge0_id"], "stdin": input_data or ""}
    headers = {"x-rapidapi-key": rapidapi_key, "Content-Type": "application/json"}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30).json()
        token = response.get("token")
        if not token:
            return {"ok": False, "status": "Submission failed", "stdout": "", "stderr": str(response), "time": None, "memory": None}
        time.sleep(2)
        result = requests.get(
            f"https://judge0-ce.p.rapidapi.com/submissions/{token}?base64_encoded=false&fields=*",
            headers=headers,
            timeout=30
        ).json()
        status = (result.get("status") or {}).get("description", "Unknown")
        stdout = result.get("stdout") or ""
        stderr = normalize_compiler_stderr(result.get("stderr") or result.get("compile_output") or result.get("message") or "")
        return {
            "ok": status == "Accepted",
            "status": status,
            "stdout": stdout,
            "stderr": stderr,
            "time": result.get("time"),
            "memory": result.get("memory"),
        }
    except Exception as e:
        return {"ok": False, "status": "API Error", "stdout": "", "stderr": str(e), "time": None, "memory": None}

def run_java_code(user_code, input_data=""):
    rapidapi_key = st.secrets.get("RAPIDAPI_KEY", "")
    if not rapidapi_key:
        def run_with_judge0_public():
            return run_code_with_judge0_public(user_code, input_data, "java")

        java8_code = user_code.replace("public class Main", "class Main")
        wandbox_payload = {
            "compiler": "openjdk-jdk-21+35",
            "compiler-option-raw": "--release=8",
            "code": java8_code,
            "stdin": input_data or "",
        }
        try:
            result = {}
            for attempt in range(2):
                result = requests.post("https://wandbox.org/api/compile.json", json=wandbox_payload, timeout=40).json()
                raw_error = " ".join([
                    str(result.get("compiler_error") or ""),
                    str(result.get("program_error") or ""),
                    str(result.get("compiler_message") or ""),
                    str(result.get("program_message") or ""),
                ])
                if not compiler_service_unavailable(raw_error):
                    break
                if attempt == 0:
                    time.sleep(1)
            raw_error = " ".join([
                str(result.get("compiler_error") or ""),
                str(result.get("program_error") or ""),
                str(result.get("compiler_message") or ""),
                str(result.get("program_message") or ""),
            ])
            if compiler_service_unavailable(raw_error):
                fallback = run_with_judge0_public()
                fallback["status"] = f"{fallback.get('status', 'Unknown')} - Wandbox busy fallback"
                return fallback
            stdout = result.get("program_output") or ""
            status_code = str(result.get("status", ""))
            stderr = ""
            if status_code != "0":
                stderr = (
                    result.get("compiler_error")
                    or result.get("compiler_message")
                    or result.get("program_error")
                    or result.get("program_message")
                    or ""
                )
                stderr = normalize_compiler_stderr(stderr)
            status = "Accepted (Java 8 compatible)" if status_code == "0" else "Error"
            return {
                "ok": status_code == "0",
                "status": status,
                "stdout": stdout,
                "stderr": stderr,
                "time": None,
                "memory": None,
            }
        except Exception as e:
            try:
                fallback = run_with_judge0_public()
                fallback["status"] = f"{fallback.get('status', 'Unknown')} - Wandbox API fallback"
                return fallback
            except Exception:
                return {"ok": False, "status": "Java API Error", "stdout": "", "stderr": str(e)}

    url = "https://judge0-ce.p.rapidapi.com/submissions?base64_encoded=false&fields=*"
    payload = {"source_code": user_code, "language_id": 62, "stdin": input_data or ""}
    headers = {"x-rapidapi-key": rapidapi_key, "Content-Type": "application/json"}
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30).json()
        token = response.get("token")
        if not token:
            return {"ok": False, "status": "Submission failed", "stdout": "", "stderr": str(response)}
        time.sleep(2)
        result = requests.get(
            f"https://judge0-ce.p.rapidapi.com/submissions/{token}?base64_encoded=false&fields=*",
            headers=headers,
            timeout=30
        ).json()
        status = (result.get("status") or {}).get("description", "Unknown")
        stdout = result.get("stdout") or ""
        stderr = result.get("stderr") or result.get("compile_output") or result.get("message") or ""
        return {
            "ok": status == "Accepted",
            "status": status,
            "stdout": stdout,
            "stderr": stderr,
            "time": result.get("time"),
            "memory": result.get("memory"),
        }
    except Exception as e:
        return {"ok": False, "status": "API Error", "stdout": "", "stderr": str(e)}

PROGRAMMING_META_PREFIX = "__PROGRAMMING_META__"

def make_programming_meta(description, test_cases, language="java"):
    return PROGRAMMING_META_PREFIX + json.dumps({
        "description": description or "",
        "test_cases": test_cases or [],
        "language": normalize_programming_language(language),
    }, ensure_ascii=False)

def get_programming_meta(question):
    raw = question.get("explanation") or ""
    if isinstance(raw, str) and raw.startswith(PROGRAMMING_META_PREFIX):
        try:
            data = json.loads(raw[len(PROGRAMMING_META_PREFIX):])
            data["test_cases"] = data.get("test_cases") or []
            data["language"] = normalize_programming_language(data.get("language"))
            for tc in data["test_cases"]:
                tc["hidden"] = bool(tc.get("hidden", False))
            return data
        except Exception:
            return {"description": "", "test_cases": [], "language": "java"}
    return {"description": raw if question.get("type") == "programming" else "", "test_cases": [], "language": "java"}

def get_question_max_marks(question):
    if question.get("type") == "programming":
        meta = get_programming_meta(question)
        total = 0
        for tc in meta.get("test_cases", []):
            try:
                total += int(tc.get("marks", 0) or 0)
            except Exception:
                pass
        return total if total > 0 else 1
    return 1

def get_exam_max_marks(questions):
    return sum(get_question_max_marks(q) for q in questions)

def run_programming_test_cases(question, code, language=None):
    meta = get_programming_meta(question)
    selected_language = normalize_programming_language(language or meta.get("language", "java"))
    results = []
    total_marks = get_question_max_marks(question)
    earned = 0
    for idx, tc in enumerate(meta.get("test_cases", []), start=1):
        inp = tc.get("input", "")
        expected = str(tc.get("expected_output", "")).strip()
        try:
            marks = int(tc.get("marks", 0) or 0)
        except Exception:
            marks = 0
        result = run_programming_code(code, inp, selected_language)
        actual = str(result.get("stdout", "")).strip()
        passed = result.get("ok") and actual == expected
        if passed:
            earned += marks
        results.append({
            "case": idx,
            "input": inp,
            "expected_output": expected,
            "actual_output": actual,
            "marks": marks,
            "hidden": bool(tc.get("hidden", False)),
            "passed": bool(passed),
            "status": result.get("status", "Unknown"),
            "error": result.get("stderr", ""),
        })
    pct = int((earned / total_marks) * 100) if total_marks else 0
    return {"earned": earned, "total": total_marks, "percentage": pct, "language": selected_language, "results": results}

def is_programming_exam(exam_id):
    try:
        q_rows = supabase.table("questions").select("type").eq("exam_id", exam_id).execute().data or []
        return bool(q_rows) and all(q.get("type") == "programming" for q in q_rows)
    except Exception:
        return False

def get_programming_session_sql():
    return """
create table if not exists programming_exam_sessions (
  user_id uuid not null references users(id) on delete cascade,
  exam_id uuid not null references exams(id) on delete cascade,
  answers jsonb not null default '{}'::jsonb,
  question_index integer not null default 0,
  exam_end_time double precision,
  program_submissions jsonb not null default '{}'::jsonb,
  question_time_log jsonb not null default '{}'::jsonb,
  status text not null default 'active',
  force_submit boolean not null default false,
  force_fullscreen boolean not null default true,
  malpractice_count integer not null default 0,
  last_malpractice_reason text,
  updated_at timestamptz default now(),
  primary key (user_id, exam_id)
);
"""


def get_active_programming_session(user_id, exam_id):
    try:
        rows = supabase.table("programming_exam_sessions").select("*").eq("user_id", str(user_id)).eq("exam_id", str(exam_id)).eq("status", "active").limit(1).execute().data
        return rows[0] if rows else None
    except Exception:
        return None


def save_programming_exam_session(status="active", force_submit=None, malpractice_reason=None):
    if not st.session_state.get("exam_id") or not is_programming_exam(st.session_state.exam_id):
        return
    payload = {
        "user_id": str(st.session_state.user_id),
        "exam_id": str(st.session_state.exam_id),
        "answers": st.session_state.get("answers", {}),
        "question_index": int(st.session_state.get("question_index", 0) or 0),
        "exam_end_time": float(st.session_state.get("exam_end_time", 0) or 0),
        "program_submissions": st.session_state.get("program_submissions", {}),
        "question_time_log": st.session_state.get("question_time_log", {}),
        "status": status,
        "updated_at": "now()",
    }
    if force_submit is not None:
        payload["force_submit"] = bool(force_submit)
    if malpractice_reason:
        payload["last_malpractice_reason"] = malpractice_reason
    try:
        supabase.table("programming_exam_sessions").upsert(payload, on_conflict="user_id,exam_id").execute()
    except Exception:
        pass


def load_programming_exam_session(user_id, exam, questions):
    session = get_active_programming_session(user_id, exam["id"])
    if not session:
        return None
    duration = int(exam.get("duration_mins", 30) or 30)
    end_time = float(session.get("exam_end_time") or 0)
    if end_time <= time.time():
        end_time = time.time() + (duration * 60)
    return {
        "exam_id": exam["id"],
        "exam_title": exam["title"],
        "start_exam": True,
        "exam_submitted": False,
        "answers": session.get("answers") or {},
        "question_index": min(int(session.get("question_index") or 0), max(len(questions) - 1, 0)),
        "current_questions": questions,
        "exam_end_time": end_time,
        "program_run_results": {},
        "program_custom_results": {},
        "program_submissions": session.get("program_submissions") or {},
        "question_time_log": session.get("question_time_log") or {},
        "question_start_time": {},
        "programming_session_loaded": True,
    }


def start_exam_with_questions(exam, questions):
    resumed = load_programming_exam_session(st.session_state.user_id, exam, questions) if is_programming_exam(exam["id"]) else None
    if resumed:
        st.session_state.update(resumed)
        return
    duration = int(exam.get("duration_mins", 30) or 30)
    st.session_state.update({
        "exam_id": exam["id"],
        "exam_title": exam["title"],
        "start_exam": True,
        "exam_submitted": False,
        "answers": {},
        "question_index": 0,
        "current_questions": questions,
        "exam_end_time": time.time() + (duration * 60),
        "program_run_results": {},
        "program_custom_results": {},
        "program_submissions": {},
        "question_time_log": {},
        "question_start_time": {},
        "programming_session_loaded": True,
    })
    save_programming_exam_session(status="active", force_submit=False)


def report_programming_malpractice(reason):
    if not st.session_state.get("exam_id") or not is_programming_exam(st.session_state.exam_id):
        return
    key = f"{st.session_state.user_id}:{st.session_state.exam_id}:{reason}"
    if key in st.session_state.malpractice_reported_keys:
        return
    st.session_state.malpractice_reported_keys.add(key)
    try:
        uinfo = supabase.table("users").select("name, email").eq("id", st.session_state.user_id).execute().data or [{}]
        uname = uinfo[0].get("name") or uinfo[0].get("email") or "Student"
        send_admin_notification(f"Malpractice alert: {uname} - {st.session_state.exam_title} - {reason}")
        session = get_active_programming_session(st.session_state.user_id, st.session_state.exam_id) or {}
        count = int(session.get("malpractice_count") or 0) + 1
        save_programming_exam_session(status="active", malpractice_reason=reason)
        supabase.table("programming_exam_sessions").update({
            "malpractice_count": count,
            "last_malpractice_reason": reason,
            "updated_at": "now()",
        }).eq("user_id", str(st.session_state.user_id)).eq("exam_id", str(st.session_state.exam_id)).execute()
    except Exception:
        pass

def user_attempted_question(user_id, question_id):
    try:
        attempts = supabase.table("exam_attempts").select("id").eq("user_id", user_id).execute().data or []
        attempt_ids = [a["id"] for a in attempts]
        if not attempt_ids:
            return False
        answers = supabase.table("user_answers").select("id").eq("question_id", question_id).in_("attempt_id", attempt_ids).limit(1).execute().data
        return bool(answers)
    except Exception:
        return False

def parse_program_answer(value, default_language="java"):
    if isinstance(value, dict):
        return str(value.get("code", "")), normalize_programming_language(value.get("language", default_language))
    return str(value or ""), normalize_programming_language(default_language)


def get_cached_program_submission(question_id, code, language="java"):
    saved = st.session_state.program_submissions.get(str(question_id), {})
    if (
        saved.get("code") == code
        and normalize_programming_language(saved.get("language", language)) == normalize_programming_language(language)
        and saved.get("score_data")
    ):
        return saved["score_data"]
    return None

def get_unsubmitted_program_questions(questions, answers):
    pending = []
    for idx, q in enumerate(questions, start=1):
        if q.get("type") != "programming":
            continue
        qid = q["id"]
        meta = get_programming_meta(q)
        code, language = parse_program_answer(answers.get(qid, ""), meta.get("language", "java"))
        if not get_cached_program_submission(qid, code, language):
            pending.append(idx)
    return pending

def score_exam_answers(questions, answers, use_cached_programming=True):
    total_marks = get_exam_max_marks(questions)
    earned_marks = 0
    answer_payloads = {}
    for q in questions:
        qid = q["id"]
        user_val = answers.get(qid, "")
        if q.get("type") == "programming":
            meta = get_programming_meta(q)
            code, language = parse_program_answer(user_val, meta.get("language", "java"))
            score_data = get_cached_program_submission(qid, code, language) if use_cached_programming else None
            if score_data is None and not use_cached_programming:
                score_data = run_programming_test_cases(q, code, language)
            if score_data is None:
                score_data = {
                    "earned": 0,
                    "total": get_question_max_marks(q),
                    "percentage": 0,
                    "results": [],
                    "note": "Program was not individually submitted before final exam submit.",
                }
            earned_marks += int(score_data.get("earned", 0) or 0)
            answer_payloads[qid] = json.dumps({"code": code, "language": language, **score_data}, ensure_ascii=False)
        elif q.get("type") == "mcq":
            if check_mcq_correct(user_val, q):
                earned_marks += 1
            answer_payloads[qid] = user_val
        else:
            if str(user_val).strip().lower() == str(q.get("correct_answer", "")).strip().lower():
                earned_marks += 1
            answer_payloads[qid] = user_val
    percentage = int((earned_marks / total_marks) * 100) if total_marks else 0
    return earned_marks, total_marks, percentage, answer_payloads

def compact_answer_for_save(answer, max_chars=3500):
    text = answer if isinstance(answer, str) else str(answer)
    if len(text) <= max_chars:
        return text
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "code" in data:
            code = str(data.get("code", ""))
            earned = data.get("earned", 0)
            total = data.get("total", 0)
            return json.dumps({
                "code": code[:max_chars],
                "earned": earned,
                "total": total,
                "language": data.get("language", "java"),
                "note": "Detailed test-case output was trimmed while saving.",
            }, ensure_ascii=False)
    except Exception:
        pass
    return text[:max_chars] + "\n...trimmed while saving..."

def insert_user_answer_row(attempt_id, question_id, answer, time_spent_seconds=None):
    base_payload = {"attempt_id": attempt_id, "question_id": question_id, "answer": answer}
    payloads = []
    if time_spent_seconds is not None:
        payloads.append({**base_payload, "time_spent_seconds": int(time_spent_seconds or 0)})
    payloads.append(base_payload)
    payloads.append({**base_payload, "answer": compact_answer_for_save(answer)})

    last_error = None
    for payload in payloads:
        try:
            supabase.table("user_answers").insert(payload).execute()
            return
        except Exception as e:
            last_error = e
    raise last_error

def submit_exam_attempt(questions, include_time=False, require_programming_submitted=False):
    if require_programming_submitted:
        pending = get_unsubmitted_program_questions(questions, st.session_state.answers)
        if pending:
            nums = ", ".join(str(n) for n in pending)
            raise ValueError(f"Please click Submit Program for question(s): {nums}")
    attempt_uuid = str(uuid.uuid4())
    final_score, total_marks, final_percentage, answer_payloads = score_exam_answers(questions, st.session_state.answers, use_cached_programming=True)
    supabase.table("exam_attempts").insert({
        "id": attempt_uuid,
        "user_id": st.session_state.user_id,
        "exam_id": st.session_state.exam_id,
        "score": final_score,
    }).execute()
    for q in questions:
        t_spent = st.session_state.question_time_log.get(q["id"], 0) if include_time else None
        insert_user_answer_row(attempt_uuid, q["id"], answer_payloads.get(q["id"], ""), t_spent)
    st.session_state.last_attempt_id = attempt_uuid
    if is_programming_exam(st.session_state.exam_id):
        save_programming_exam_session(status="submitted", force_submit=False)
    return attempt_uuid

def get_answer_time_spent(attempt_id, question_id):
    try:
        ua_data = supabase.table("user_answers").select("time_spent_seconds") \
            .eq("attempt_id", attempt_id).eq("question_id", question_id).execute().data
        return ua_data[0]["time_spent_seconds"] if ua_data and ua_data[0].get("time_spent_seconds") else 0
    except Exception:
        return 0

# =========================
# OCR: IMAGE QUESTION EXTRACT
# =========================
def extract_question_from_image(image_source):
    import re

    def parse_ocr_text(raw_text):
        lines = [l.strip() for l in raw_text.replace("\r\n", "\n").replace("\r", "\n").splitlines()]
        lines = [l for l in lines if l]

        options = {"A": "", "B": "", "C": "", "D": ""}
        question_lines = []
        option_found_at = None

        opt_line_pat = re.compile(
            r"^(?:option\s*)?([A-Da-d]|[1-4])\s*[\)\]\.:\-]\s*(.+)", re.IGNORECASE
        )

        for i, line in enumerate(lines):
            m = opt_line_pat.match(line)
            if m:
                lbl = m.group(1).upper()
                if lbl in ["1","2","3","4"]:
                    lbl = chr(ord("A") + int(lbl) - 1)
                val = m.group(2).strip()
                if lbl in options and not options[lbl]:
                    options[lbl] = val
                    if option_found_at is None:
                        option_found_at = i
            else:
                if option_found_at is None:
                    if not re.match(r"(?i)^(answer|correct\s*answer|ans)\s*[:\-]", line):
                        question_lines.append(line)

        question = " ".join(question_lines).strip()

        answer = ""
        full_text = "\n".join(lines)
        ans_m = re.search(
            r"(?im)^(?:answer|correct\s*answer|ans)\s*[:\-]\s*([A-D]|[1-4]|.+)$",
            full_text
        )
        if ans_m:
            raw_ans = ans_m.group(1).strip()
            lbl = raw_ans.upper()
            if lbl in ["1","2","3","4"]:
                lbl = chr(ord("A") + int(lbl) - 1)
            if lbl in options:
                answer = lbl
            else:
                answer = raw_ans

        has_options = any(v for v in options.values())
        return {
            "question": question if question else full_text[:300],
            "type": "mcq" if has_options else "blank",
            "option_a": options["A"],
            "option_b": options["B"],
            "option_c": options["C"],
            "option_d": options["D"],
            "correct_answer": answer,
            "hint": "",
        }

    try:
        api_key = st.secrets.get("OCR_SPACE_API_KEY", "")
        if not api_key:
            st.error("OCR_SPACE_API_KEY Streamlit secrets add .")
            return None
        payload = {"apikey": api_key, "language": "eng", "OCREngine": "2",
                   "isOverlayRequired": "false", "scale": "true"}
        if isinstance(image_source, str):
            resp = requests.post("https://api.ocr.space/parse/image",
                                 data={**payload, "url": image_source}, timeout=40)
        else:
            resp = requests.post("https://api.ocr.space/parse/image", data=payload,
                                 files={"file": (image_source.name, image_source.getvalue(), image_source.type)},
                                 timeout=40)
        result = resp.json()
        if result.get("IsErroredOnProcessing"):
            errs = result.get("ErrorMessage") or result.get("ErrorDetails") or "OCR failed"
            if isinstance(errs, list): errs = " ".join(str(e) for e in errs)
            st.error(f"OCR error: {errs}")
            return None
        parsed = result.get("ParsedResults") or []
        raw_text = "\n".join(p.get("ParsedText","") for p in parsed if p.get("ParsedText")).strip()
        if not raw_text:
            st.error("Image text clear .")
            return None
        with st.expander("OCR raw text"):
            st.code(raw_text)
        return parse_ocr_text(raw_text)
    except Exception as e:
        st.error(f"Image question extract failed: {e}")
        return None


def login():
    st.title("LMS Login")
    login_method = st.radio("Login method:", ["Email & Password", "PIN Login"], horizontal=True, key="login_method_radio")

    if login_method == "Email & Password":
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Login", type="primary", use_container_width=True, key="email_login_btn"):
            try:
                response = supabase.auth.sign_in_with_password({"email": email, "password": password})
                user = response.user
                user_data = supabase.table("users").select("*").eq("email", email).execute()
                if user_data.data:
                    urow = user_data.data[0]
                    st.session_state.email_temp = email
                    st.session_state.user_id_temp = user.id
                    st.session_state.role_temp = urow["role"]
                    st.session_state.pin_setup_mode = not bool(urow.get("app_pin"))
                    st.session_state.pin_verified = False
                    st.rerun()
                else:
                    st.error("User record not found.")
            except Exception as e:
                st.error(str(e))
    else:
        st.caption("Enter your unique PIN.")
        pin = st.text_input("PIN", type="password", max_chars=6, key="pin_only_input")
        if st.button("Enter App", type="primary", use_container_width=True, key="pin_only_btn"):
            if not pin:
                st.error("Enter PIN.")
            else:
                try:
                    user_data = supabase.table("users").select("*").eq("app_pin", pin).execute()
                    if user_data.data:
                        urow = user_data.data[0]
                        st.session_state.logged_in = True
                        st.session_state.role = urow["role"]
                        st.session_state.user_id = urow["id"]
                        st.session_state.pin_verified = True
                        st.query_params["uid"] = str(urow["id"])
                        st.query_params["role"] = urow["role"]
                        st.rerun()
                    card_user_data = supabase.table("card_users").select("*").eq("app_pin", pin).execute().data
                    if card_user_data:
                        urow = card_user_data[0]
                        st.session_state.logged_in = True
                        st.session_state.role = "card_user"
                        st.session_state.user_id = urow["id"]
                        st.session_state.pin_verified = True
                        st.query_params["uid"] = str(urow["id"])
                        st.query_params["role"] = "card_user"
                        st.rerun()
                    st.error("Wrong PIN. Try again.")
                except Exception as e:
                    st.error(str(e))


def pin_screen():
    st.title("App Lock")
    if st.session_state.pin_setup_mode:
        st.subheader("Set PIN (4-6 digits)")
        st.caption("PIN must be globally unique.")
        pin1 = st.text_input("New PIN (4-6 digits)", type="password", max_chars=6, key="pin_new")
        pin2 = st.text_input("Confirm PIN", type="password", max_chars=6, key="pin_confirm")
        if st.button("Set PIN", type="primary", use_container_width=True):
            if not pin1.isdigit() or len(pin1) < 4:
                st.error("Enter 4-6 digits only.")
            elif pin1 != pin2:
                st.error("PINs do not match.")
            else:
                existing = supabase.table("users").select("id").eq("app_pin", pin1).execute().data
                if existing and existing[0]["id"] != st.session_state.user_id_temp:
                    st.error("This PIN is already used by another user.")
                else:
                    supabase.table("users").update({"app_pin": pin1}).eq("id", st.session_state.user_id_temp).execute()
                    st.session_state.logged_in = True
                    st.session_state.role = st.session_state.role_temp
                    st.session_state.user_id = st.session_state.user_id_temp
                    st.session_state.pin_verified = True
                    st.query_params["uid"] = str(st.session_state.user_id_temp)
                    st.query_params["role"] = st.session_state.role_temp
                    st.success("PIN set. Welcome!")
                    st.rerun()
    else:
        st.subheader("Enter PIN")
        pin_input = st.text_input("4-digit PIN", type="password", max_chars=4, key="pin_entry")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Enter App", type="primary", use_container_width=True):
                urow = supabase.table("users").select("app_pin").eq("id", st.session_state.user_id_temp).execute().data
                if urow and urow[0]["app_pin"] == pin_input:
                    st.session_state.logged_in = True
                    st.session_state.role = st.session_state.role_temp
                    st.session_state.user_id = st.session_state.user_id_temp
                    st.session_state.pin_verified = True
                    st.query_params["uid"] = str(st.session_state.user_id_temp)
                    st.query_params["role"] = st.session_state.role_temp
                    st.rerun()
                else:
                    st.error("Wrong PIN.")
        with col2:
            if st.button("Login with another account", use_container_width=True):
                st.session_state.email_temp = ""
                st.session_state.user_id_temp = ""
                st.session_state.role_temp = ""
                st.session_state.pin_verified = False
                st.session_state.pin_setup_mode = False
                st.rerun()

# =========================
# LEADERBOARD
# =========================
def get_exam_leaderboard(exam_id):
    try:
        attempts = supabase.table("exam_attempts").select("*").eq("exam_id", exam_id).execute().data
        user_best_scores = {}
        for att in attempts:
            uid = att["user_id"]
            score = att["score"]
            if uid not in user_best_scores or score > user_best_scores[uid]:
                user_best_scores[uid] = score
        leaderboard = []
        for uid, max_score in user_best_scores.items():
            user_info = supabase.table("users").select("name, email").eq("id", uid).execute().data
            if user_info:
                leaderboard.append({"Name": user_info[0]["name"], "Email": user_info[0]["email"], "Score": max_score})
        return sorted(leaderboard, key=lambda x: x["Score"], reverse=True)
    except Exception:
        return []

# =========================
# NOTIFICATIONS
# =========================
def send_notification(message, user_id=None):
    supabase.table("notifications").insert({
        "user_id": str(user_id) if user_id else None,
        "message": message,
    }).execute()

def send_admin_notification(message):
    try:
        admins = supabase.table("users").select("id").eq("role", "admin").execute().data or []
        if admins:
            for admin in admins:
                send_notification(message, admin["id"])
        else:
            send_notification(message)
    except Exception:
        send_notification(message)

def get_unread_notifications(user_id):
    try:
        uid = str(user_id)
        all_notifs = supabase.table("notifications").select("*").order("created_at", desc=True).execute().data
        read_data = supabase.table("notification_reads").select("notification_id").eq("user_id", uid).execute().data
        read_ids = {r["notification_id"] for r in read_data}
        return [n for n in all_notifs if (n["user_id"] is None or n["user_id"] == uid) and n["id"] not in read_ids]
    except Exception:
        return []

def mark_notifications_read(user_id):
    try:
        uid = str(user_id)
        unread = get_unread_notifications(uid)
        for n in unread:
            supabase.table("notification_reads").upsert(
                {"user_id": uid, "notification_id": n["id"]}, on_conflict="user_id,notification_id"
            ).execute()
    except Exception:
        pass

def clean_ui_text(value):
    text = str(value or "")
    return "".join(ch for ch in text if ch == "\n" or ch == "\t" or 32 <= ord(ch) <= 126).strip()

def show_notification_banner(user_id):
    notifs = get_unread_notifications(user_id)
    if not notifs:
        return
    st.markdown("""
        <style>
        .notif-wrap { border-left:5px solid #ff6b6b;background:#fff5f5;padding:10px 16px;
          border-radius:0 8px 8px 0;margin-bottom:5px;font-size:0.92rem;color:#c0392b;font-weight:500; }
        .notif-wrap:first-child { border-left-color:#e74c3c;background:#ffeaea;font-weight:700;font-size:0.97rem; }
        </style>""", unsafe_allow_html=True)
    notif_html = "".join(f"<div class='notif-wrap'>Alert: {clean_ui_text(n.get('message'))}</div>" for n in notifs)
    st.markdown(notif_html, unsafe_allow_html=True)
    if st.button(f"Mark all as Read ({len(notifs)})", key="mark_notif_read", type="secondary"):
        mark_notifications_read(user_id)
        st.rerun()

# =========================
# GROUP CHAT
# =========================
def get_unread_count(user_id):
    try:
        read_data = supabase.table("message_reads").select("last_read_at").eq("user_id", str(user_id)).execute().data
        if not read_data:
            total = supabase.table("messages").select("id").execute().data
            return len(total)
        last_read = read_data[0]["last_read_at"]
        unread = supabase.table("messages").select("id").gt("created_at", last_read).neq("user_id", str(user_id)).execute().data
        return len(unread)
    except Exception:
        return 0

def group_chat():
    st.title("Group Chat")
    user_id = str(st.session_state.user_id)
    messages = supabase.table("messages").select("*").order("created_at", desc=False).limit(50).execute().data
    chat_container = st.container(height=450)
    with chat_container:
        if not messages:
            st.info("No messages yet. Send the first message.")
        for msg in messages:
            is_me = msg["user_id"] == user_id
            time_str = str(msg.get("created_at", ""))[:16]
            if is_me:
                col1, col2 = st.columns([2, 5])
                with col2:
                    st.markdown(
                        f"<div style='background:#dcf8c6;padding:10px 14px;border-radius:12px 12px 0px 12px;margin:4px 0;'>"
                        f"<small style='color:#555;font-weight:600'>You</small><br>{msg['message']}"
                        f"<br><small style='color:#999;font-size:10px'>{time_str}</small></div>",
                        unsafe_allow_html=True)
            else:
                col1, col2 = st.columns([5, 2])
                with col1:
                    st.markdown(
                        f"<div style='background:#f1f0f0;padding:10px 14px;border-radius:12px 12px 12px 0px;margin:4px 0;'>"
                        f"<small style='color:#0084ff;font-weight:600'>{msg.get('user_name','Unknown')}</small><br>{msg['message']}"
                        f"<br><small style='color:#999;font-size:10px'>{time_str}</small></div>",
                        unsafe_allow_html=True)
    st.divider()
    col_input, col_send, col_read = st.columns([5, 1, 1])
    with col_input:
        new_msg = st.text_input("Message ...", key="chat_input", label_visibility="collapsed")
    with col_send:
        send = st.button("Send", use_container_width=True, type="primary")
    with col_read:
        mark_read = st.button("Read", use_container_width=True)
    if send and new_msg.strip():
        uinfo = supabase.table("users").select("name").eq("id", user_id).execute().data
        uname = uinfo[0]["name"] if uinfo else "Unknown"
        supabase.table("messages").insert({"user_id": user_id, "user_name": uname, "message": new_msg.strip()}).execute()
        supabase.table("message_reads").upsert({"user_id": user_id, "last_read_at": "now()"}, on_conflict="user_id").execute()
        st.rerun()
    if mark_read:
        supabase.table("message_reads").upsert({"user_id": user_id, "last_read_at": "now()"}, on_conflict="user_id").execute()
        st.success("All messages marked as read.")
        st.rerun()

# =========================
# ATTENDANCE (LeetCode/GitHub style)
# =========================
def mark_today_attendance(user_id):
    today = date.today().isoformat()
    if st.session_state.get("attendance_marked_date") == today:
        return
    try:
        supabase.table("attendance").upsert(
            {"user_id": str(user_id), "attendance_date": today},
            on_conflict="user_id,attendance_date"
        ).execute()
        st.session_state.attendance_marked_date = today
    except Exception:
        pass

def show_attendance_tab(user_id):
    st.title("My Attendance")
    today = date.today()
    start_day = today - timedelta(days=364)

    try:
        rows = supabase.table("attendance").select("attendance_date") \
            .eq("user_id", str(user_id)) \
            .gte("attendance_date", start_day.isoformat()) \
            .lte("attendance_date", today.isoformat()) \
            .execute().data
        attended = {str(r["attendance_date"]) for r in rows if r.get("attendance_date")}
    except Exception as e:
        st.warning("Attendance table database variance detected.")
        return

    total = len(attended)
    streak = 0
    cursor = today
    while cursor.isoformat() in attended:
        streak += 1
        cursor -= timedelta(days=1)

    longest = 0
    run = 0
    prev_d = None
    for ds in sorted(attended):
        d2 = date.fromisoformat(ds)
        if prev_d and (d2 - prev_d).days == 1:
            run += 1
        else:
            run = 1
        longest = max(longest, run)
        prev_d = d2

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(" Total Days", total)
    c2.metric(" Current Streak", f"{streak} days")
    c3.metric(" Longest Streak", f"{longest} days")
    c4.metric(" Today", " Present" if today.isoformat() in attended else " Pending")

    st.divider()

    offset = start_day.isoweekday() % 7
    grid_start = start_day - timedelta(days=offset)
    all_days = [grid_start + timedelta(days=i) for i in range((today - grid_start).days + 1)]
    weeks = [all_days[i:i+7] for i in range(0, len(all_days), 7)]

    month_labels = []
    last_m = ""
    for week in weeks:
        lbl = ""
        for d in week:
            if d.day <= 7 and d.strftime("%b") != last_m:
                lbl = d.strftime("%b")
                last_m = lbl
                break
        month_labels.append(lbl)

    label_html = "".join(
        f"<div style='width:14px;font-size:10px;color:#57606a;text-align:left;'>{lbl}</div>"
        for lbl in month_labels
    )

    week_html = ""
    for week in weeks:
        cells = ""
        for d in week:
            if d > today:
                color = "transparent"
                border = "none"
            elif d.isoformat() in attended:
                color = "#2ea043"
                border = "1px solid rgba(27,31,36,0.1)"
            else:
                color = "#ebedf0"
                border = "1px solid rgba(27,31,36,0.06)"
            title = f"{d.strftime('%d %b %Y')}  {'Present' if d.isoformat() in attended else 'Absent'}"
            cells += (
                f"<div title='{title}' style='width:14px;height:14px;border-radius:2px;"
                f"background:{color};border:{border};'></div>"
            )
        week_html += f"<div style='display:flex;flex-direction:column;gap:3px;'>{cells}</div>"

    st.markdown(
        f"""
        <style>
        .att-card{{background:#fff;border:1px solid #d0d7de;border-radius:10px;padding:18px 20px;margin-bottom:16px;}}
        .att-title{{font-size:1.1rem;font-weight:700;margin-bottom:4px;}}
        .att-sub{{color:#57606a;font-size:0.88rem;margin-bottom:14px;}}
        </style>
        <div class="att-card">
          <div class="att-title">Daily Login Activity</div>
          <div class="att-sub">Login activity (last 1 year)</div>
          <div style="display:flex;gap:3px;margin-bottom:4px;">{label_html}</div>
          <div style="display:flex;gap:3px;overflow-x:auto;">{week_html}</div>
          <div style="display:flex;align-items:center;gap:5px;justify-content:flex-end;color:#57606a;font-size:11px;margin-top:8px;">
            <span>Less</span>
            <div style="width:12px;height:12px;border-radius:2px;background:#ebedf0;border:1px solid rgba(27,31,36,0.06);"></div>
            <div style="width:12px;height:12px;border-radius:2px;background:#2ea043;border:1px solid rgba(27,31,36,0.1);"></div>
            <span>More</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

# =========================
# STUDENT PROGRESS
# =========================
def get_student_completed_ids(user_id):
    if st.session_state.completed_ids is None:
        try:
            rows = supabase.table("class_completions").select("class_id").eq("user_id", user_id).execute().data
            st.session_state.completed_ids = {str(r["class_id"]) for r in rows}
        except Exception:
            st.session_state.completed_ids = set()
    return st.session_state.completed_ids

def focus_student_class(class_id, exam_id=""):
    st.session_state.focus_class_id = str(class_id) if class_id else ""
    st.session_state.focus_exam_id = str(exam_id) if exam_id else ""
    st.session_state.user_page = "My Classes"
    st.rerun()

def start_student_exam(exam):
    has_pwd = exam.get("password") and str(exam["password"]).strip()
    if has_pwd:
        focus_student_class(exam.get("class_id"), exam.get("id"))
        return
    q_data = supabase.table("questions").select("*").eq("exam_id", exam["id"]).execute().data
    st.session_state.update({
        "exam_id": exam["id"],
        "exam_title": exam["title"],
        "start_exam": True,
        "exam_submitted": False,
        "answers": {},
        "question_index": 0,
        "current_questions": q_data,
        "exam_end_time": time.time() + (int(exam.get("duration_mins", 30)) * 60),
    })
    st.rerun()

def collect_student_progress(user_id):
    completed_ids = get_student_completed_ids(user_id)
    modules = supabase.table("modules").select("*").execute().data or []
    submodules = supabase.table("submodules").select("*").execute().data or []
    classes = supabase.table("classes").select("*").execute().data or []
    exams = supabase.table("exams").select("*").execute().data or []
    attempts = supabase.table("exam_attempts").select("*").eq("user_id", user_id).execute().data or []

    sub_by_module = {}
    for sub in submodules:
        sub_by_module.setdefault(str(sub.get("module_id")), []).append(sub)

    classes_by_sub = {}
    class_module = {}
    for cls in classes:
        sid = str(cls.get("submodule_id"))
        classes_by_sub.setdefault(sid, []).append(cls)

    sub_module = {str(s.get("id")): str(s.get("module_id")) for s in submodules}
    for cls in classes:
        class_module[str(cls.get("id"))] = sub_module.get(str(cls.get("submodule_id")), "")

    best_scores = {}
    for att in attempts:
        eid = str(att.get("exam_id"))
        score = int(att.get("score") or 0)
        if eid not in best_scores or score > best_scores[eid]:
            best_scores[eid] = score

    active_exams = [e for e in exams if e.get("enabled")]
    question_counts = {}
    for exam in active_exams:
        try:
            q_rows = supabase.table("questions").select("*").eq("exam_id", exam["id"]).execute().data
            question_counts[str(exam["id"])] = get_exam_max_marks(q_rows)
        except Exception:
            question_counts[str(exam["id"])] = 0

    modules_data = []
    overall_total_classes = len(classes)
    overall_done_classes = sum(1 for cls in classes if str(cls.get("id")) in completed_ids)
    overall_marks_scored = 0
    overall_marks_total = 0
    pending_classes = []
    pending_exams = []

    for module in modules:
        mid = str(module.get("id"))
        module_classes = []
        for sub in sub_by_module.get(mid, []):
            for cls in classes_by_sub.get(str(sub.get("id")), []):
                cls["_submodule_title"] = sub.get("title", "")
                module_classes.append(cls)

        module_exam_rows = [e for e in active_exams if class_module.get(str(e.get("class_id"))) == mid]
        module_done = sum(1 for cls in module_classes if str(cls.get("id")) in completed_ids)
        module_total = len(module_classes)
        module_scored = 0
        module_total_marks = 0

        for exam in module_exam_rows:
            eid = str(exam.get("id"))
            total_q = question_counts.get(eid, 0)
            if total_q > 0:
                module_total_marks += total_q
                overall_marks_total += total_q
                best = best_scores.get(eid, 0)
                module_scored += best
                overall_marks_scored += best
            if eid not in best_scores:
                pending_exams.append({"exam": exam, "total_q": total_q})

        for cls in module_classes:
            if str(cls.get("id")) not in completed_ids:
                pending_classes.append(cls)

        modules_data.append({
            "module": module,
            "class_done": module_done,
            "class_total": module_total,
            "class_pct": int(module_done / module_total * 100) if module_total else 0,
            "marks_scored": module_scored,
            "marks_total": module_total_marks,
            "marks_pct": int(module_scored / module_total_marks * 100) if module_total_marks else 0,
        })

    return {
        "modules": modules_data,
        "overall_class_pct": int(overall_done_classes / overall_total_classes * 100) if overall_total_classes else 0,
        "overall_done_classes": overall_done_classes,
        "overall_total_classes": overall_total_classes,
        "overall_marks_pct": int(overall_marks_scored / overall_marks_total * 100) if overall_marks_total else 0,
        "overall_marks_scored": overall_marks_scored,
        "overall_marks_total": overall_marks_total,
        "pending_classes": pending_classes,
        "pending_exams": pending_exams,
        "best_scores": best_scores,
        "question_counts": question_counts,
        "active_exams": active_exams,
    }

def show_student_progress_tab(user_id):
    st.title("My Progress")
    try:
        progress = collect_student_progress(user_id)
    except Exception as e:
        st.error(f"Progress load failed: {e}")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Overall Marks", f"{progress['overall_class_pct']}%")
    c2.metric("Marks", f"{progress['overall_marks_scored']}/{progress['overall_marks_total']}")
    c3.metric("Class Progress", f"{progress['overall_class_pct']}%")
    c4.metric("Pending", f"{len(progress['pending_classes'])} classes / {len(progress['pending_exams'])} exams")

    st.progress(progress["overall_class_pct"] / 100)

    st.subheader("Module-wise Progress")
    for item in progress["modules"]:
        module = item["module"]
        with st.container(border=True):
            st.markdown(f"#### {module.get('title', 'Module')}")
            m1, m2 = st.columns(2)
            with m1:
                st.caption(f"Marks: {item['marks_scored']}/{item['marks_total']} ({item['marks_pct']}%)")
                st.progress(item['marks_pct'] / 100)
            with m2:
                st.caption(f"Classes: {item['class_done']}/{item['class_total']} ({item['class_pct']}%)")
                st.progress(item['class_pct'] / 100)

def show_code_practice_tab():
    st.title("Code Practice")
    if "practice_language" not in st.session_state:
        st.session_state.practice_language = "java"
    if "practice_code_by_language" not in st.session_state:
        st.session_state.practice_code_by_language = {}
    if "practice_input" not in st.session_state:
        st.session_state.practice_input = ""

    selected_label = st.selectbox(
        "Language",
        list(PROGRAMMING_LANGUAGE_LABELS.keys()),
        index=list(PROGRAMMING_LANGUAGE_LABELS.values()).index(st.session_state.practice_language),
        key="practice_language_selector",
    )
    selected_language = PROGRAMMING_LANGUAGE_LABELS[selected_label]
    st.session_state.practice_language = selected_language
    lang_meta = get_programming_language_meta(selected_language)

    if selected_language not in st.session_state.practice_code_by_language:
        st.session_state.practice_code_by_language[selected_language] = lang_meta["default_code"]

    st.session_state.practice_code_by_language[selected_language] = st.text_area(
        f"{lang_meta['label']} Code",
        value=st.session_state.practice_code_by_language[selected_language],
        height=360,
        key=f"practice_code_editor_{selected_language}"
    )
    st.session_state.practice_input = st.text_area(
        "Input",
        value=st.session_state.practice_input,
        height=120,
        key="practice_input_editor",
    )

    col_run, col_reset = st.columns([1, 1])
    with col_run:
        run_clicked = st.button(f"Run {lang_meta['label']}", type="primary", use_container_width=True)
    with col_reset:
        if st.button("Reset Sample", use_container_width=True):
            st.session_state.practice_code_by_language[selected_language] = lang_meta["default_code"]
            st.session_state.practice_input = ""
            st.rerun()

    if run_clicked:
        code = st.session_state.practice_code_by_language[selected_language]
        if not code.strip():
            st.warning(f"Enter code.")
            return
        with st.spinner(f"Running..."):
            result = run_programming_code(code, st.session_state.practice_input, selected_language)
        st.subheader("Output")
        st.code(result.get("stdout", ""), language="text")

def show_programming_questions_tab(user_id):
    st.title("Programming Questions")
    exams = supabase.table("exams").select("*").eq("enabled", True).execute().data or []
    rows = []
    for exam in exams:
        q_rows = supabase.table("questions").select("*").eq("exam_id", exam["id"]).eq("type", "programming").execute().data or []
        for q in q_rows:
            rows.append({"exam": exam, "question": q})

    if not rows:
        st.info("No programming questions available.")
        return

    h1, h2, h3, h4 = st.columns([1, 5, 2, 2])
    h1.markdown("**No**")
    h2.markdown("**Name**")
    h3.markdown("**Marks**")
    h4.markdown("**Action**")

    for idx, row in enumerate(rows, start=1):
        exam = row["exam"]
        q = row["question"]
        attempted = user_attempted_question(user_id, q["id"])
        marks = get_question_max_marks(q)
        c_no, c_name, c_marks, c_action = st.columns([1, 5, 2, 2])
        with c_no:
            st.write(idx)
        with c_name:
            st.markdown(f"**{q.get('question', 'Untitled')}**")
            st.caption(f"Exam: {exam.get('title', '')}")
        with c_marks:
            st.write(marks)
        with c_action:
            label = "Solve Again" if attempted else "Solve"
            if st.button(label, key=f"solve_prog_{q['id']}", type="primary" if not attempted else "secondary"):
                start_exam_with_questions(exam, [q])
                st.rerun()

# =========================
# REVIEW SHEET
# =========================
def render_review_sheet(questions, ans_map, db_attempt):
    if "explain_selected" not in st.session_state:
        st.session_state.explain_selected = set()

    for i, q in enumerate(questions):
        u_ans = ans_map.get(q["id"], "Not Answered")
        c_ans = str(q.get("correct_answer", "")).strip()
        is_correct = str(u_ans).strip().lower() == c_ans.lower()

        with st.container(border=True):
            hcol, bcol = st.columns([7, 1])
            with hcol:
                badge_style = "background:#e8f8ef;color:#1e7e45;font-weight:700;" if is_correct else "background:#fdecea;color:#c0392b;font-weight:700;"
                badge_txt = "Correct" if is_correct else "Incorrect"
                st.markdown(f"<div>Question {i+1} <span style='{badge_style}'>{badge_txt}</span></div>", unsafe_allow_html=True)
                st.markdown(q["question"])
            with bcol:
                qid = q["id"]
                if st.button("Explain", key=f"exp_{qid}"):
                    st.session_state.explain_selected.add(qid)
                    st.rerun()

            if q["type"] == "programming":
                try:
                    prog_ans = json.loads(u_ans) if isinstance(u_ans, str) and u_ans.strip().startswith("{") else {"code": u_ans}
                except Exception:
                    prog_ans = {"code": u_ans}
                st.code(prog_ans.get("code", ""), language="java")

# =========================
# PPT GENERATOR
# =========================
def generate_exam_ppt(questions, exam_title, q_requesters=None):
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    import io

    prs = Presentation()
    BL = prs.slide_layouts[6]
    ts = prs.slides.add_slide(BL)
    
    buf = io.BytesIO()
    prs.save(buf)
    buf.seek(0)
    return buf.read()

def check_mcq_correct(user_val, q):
    correct = str(q.get("correct_answer","")).strip()
    user = str(user_val).strip()
    if user.lower() == correct.lower():
        return True
    return False

SUPRABHATAM_LANGUAGES = {
    "Telugu": "telugu_text", "English": "english_text", "Sanskrit": "sanskrit_text"
}

def fetch_suprabhatam_slokas():
    try:
        return supabase.table("suprabhatam_slokas").select("*").order("display_order").execute().data or []
    except Exception:
        return []

def user_has_suprabhatam_access(user_id):
    return True

def render_suprabhatam_reader(slokas=None):
    st.info("Suprabhatam reader content profile ready.")

def show_suprabhatam_admin():
    st.title("Suprabhatam Content Suite Manager")

def admin_dashboard():
    st.sidebar.title("Admin Workspace")
    persist_browser_login()
    if st.sidebar.button("Logout", use_container_width=True):
        for key in defaults:
            st.session_state[key] = defaults[key]
        show_logout_redirect()

    menu = st.sidebar.selectbox("Navigation Control",
        ["Manage Course Content", "Manage Exams & Questions", "Student Results & Ranks", "Credit Cards"])

    if menu == "Manage Course Content":
        st.subheader("Manage Core Modules Architecture Layout")
        
    elif menu == "Manage Exams & Questions":
        ex_tab1, ex_tab2, ex_tab3 = st.tabs(["Exams Setup", "Add Questions & CSV Upload", "Review Papers"])
        
        with ex_tab1:
            st.write("Exams deployment configurations framework.")
            
        with ex_tab2:
            st.markdown("### 📥 Bulk Programming Question CSV Upload Framework")
            
            st.markdown("""
            > **⚠️ CRITICAL CSV FORMAT REQUIREMENTS DOCUMENTATION:**
            > For perfect platform parsing pipeline structure, your file matching records array **MUST** contain these explicit header fields exactly matching structure listed underneath:
            > - `question`: Text statement describing problem scope metrics constraints.
            > - `type`: Must specify string keyword signature value **`programming`** exclusively.
            > - `correct_answer`: Place text template standard tag parameter signature **`AUTO`** directly.
            > - `hint`: Text guidance parameters metadata field configurations array strings.
            > - `explanation`: Base configuration values parsing parameters mapping JSON payload matching pattern framework rules:
            >   `__PROGRAMMING_META___{"description": "Problem details statement text description metrics.", "language": "java", "test_cases": [{"input": "5", "expected_output": "10", "marks": 5, "hidden": false}]}`
            """)
            
            exams_all = supabase.table("exams").select("id, title").execute().data or []
            if exams_all:
                ex_options = {ex["title"]: ex["id"] for ex in exams_all}
                selected_bulk_exam = st.selectbox("Link Upload Assets Target Sheet Exam Instance:", list(ex_options.keys()), key="bulk_upload_exam_selection_list")
                target_exam_id = ex_options[selected_bulk_exam]
                
                bulk_file_asset = st.file_uploader("Select Valid Targeted CSV Structural Meta Assets Sheet File Target:", type=["csv"], key="bulk_system_csv_file_uploader_instance")
                if bulk_file_asset is not None:
                    import pandas as pd
                    import io as _io
                    try:
                        raw_data = bulk_file_asset.read()
                        try:
                            df = pd.read_csv(_io.StringIO(raw_data.decode("utf-8")))
                        except Exception:
                            df = pd.read_csv(_io.StringIO(raw_data.decode("latin1")))
                        
                        df = df.fillna("")
                        st.dataframe(df.head(5), use_container_width=True)
                        
                        if st.button("🚀 Process CSV Rows & Upload Questions", type="primary", use_container_width=True):
                            count_uploaded = 0
                            for _, row in df.iterrows():
                                supabase.table("questions").insert({
                                    "exam_id": target_exam_id,
                                    "question": str(row.get("question", "")),
                                    "type": "programming",
                                    "option_a": "", "option_b": "", "option_c": "", "option_d": "",
                                    "correct_answer": "AUTO",
                                    "hint": str(row.get("hint", "")),
                                    "explanation": str(row.get("explanation", ""))
                                }).execute()
                                count_uploaded += 1
                            st.success(f"Successfully deployed {count_uploaded} programming question rows from CSV asset records sheet.")
                            st.rerun()
                    except Exception as e:
                        st.error(f"CSV Parse Failure: {e}")
            else:
                st.warning("Create at least one exam setup block layer layout sheet matrix sequence instances first.")

        with ex_tab3:
            st.write("Review active platform metrics dynamic asset tracking systems layouts.")

    elif menu == "Student Results & Ranks":
        st.write(" Ranks dashboard logs visual matrix overview tracking engines panel.")

# =========================
# CREDIT CARD SHARING PORTAL
# =========================
def admin_credit_cards_dashboard():
    st.title("Credit Cards Admin Portal Interface Control View")

def card_user_dashboard():
    st.title("Credit Card User Portal Space")

def user_dashboard(preview_mode=False):
    st.sidebar.title("User Navigation Space Control Menu")
    if st.sidebar.button("Logout Interface Link Account"):
        show_logout_redirect()
    
    # Active class selection sequence dashboard interface profile loaders tracking engine logic mapping context block structure layers loader systems
    st.title("🎯 Structural Code Classes Dashboard Panel Interface Matrix View")
    
    modules = supabase.table("modules").select("*").execute().data or []
    completed_ids = st.session_state.get("completed_ids") or set()
    
    for module in modules:
        with st.expander(f"📦 {module['title']} Architecture Tracking Core Structure Suite Modules Layer"):
            submodules = supabase.table("submodules").select("*").eq("module_id", module["id"]).execute().data or []
            for sub in submodules:
                st.markdown(f"##### 📁 {sub['title']}")
                classes = supabase.table("classes").select("*").eq("submodule_id", sub["id"]).execute().data or []
                for cls in classes:
                    st.markdown(f"**Lesson Class Block Node:** `{cls['title']}`")
                    exams = supabase.table("exams").select("*").eq("class_id", cls["id"]).execute().data or []
                    for exam in exams:
                        if exam["enabled"]:
                            if st.button(f"🚀 Enter Platform Dynamic Workspace Panel: {exam['title']}", key=f"start_user_exam_trigger_key_{exam['id']}", use_container_width=True):
                                q_data = supabase.table("questions").select("*").eq("exam_id", exam["id"]).execute().data or []
                                start_exam_with_questions(exam, q_data)
                                st.rerun()

# =========================================================================
# ADVANCED LEETCODE-STYLE EXAM WORKSPACE VIEW TH O INDEPENDENT QUESTION SCROLL
# =========================================================================
def exam_workspace_view():
    questions = st.session_state.current_questions
    total_questions = len(questions)
    is_prog_exam = is_programming_exam(st.session_state.exam_id) if st.session_state.get("exam_id") else False
    
    if is_prog_exam and not st.session_state.exam_submitted:
        qp = st.query_params
        if qp.get("malpractice") == "1":
            reason = qp.get("mal_reason", "Tab switched or focus lost")
            report_programming_malpractice(reason)
            try:
                del st.query_params["malpractice"]
                del st.query_params["mal_reason"]
            except Exception:
                pass
        
        session = get_active_programming_session(st.session_state.user_id, st.session_state.exam_id)
        if session and session.get("force_submit"):
            try:
                submit_exam_attempt(questions, include_time=True, require_programming_submitted=False)
                st.session_state.exam_submitted = True
                st.rerun()
            except Exception:
                return

    if total_questions == 0:
        st.warning("No questions configured.")
        return

    remaining_time = int(st.session_state.exam_end_time - time.time())
    if remaining_time <= 0 and not st.session_state.exam_submitted:
        try:
            submit_exam_attempt(questions, include_time=False)
            st.session_state.exam_submitted = True
            st.rerun()
        except Exception:
            return

    if st.session_state.exam_submitted:
        st.title("Results Panel Review Canvas Sheet Area Interface Framework Layout")
        if st.button("Return back into operational environment dashboard nodes"):
            st.session_state.start_exam = False
            st.session_state.exam_submitted = False
            st.rerun()
    else:
        # ANTI-CHEAT AND LOCK DOWN ENGINE INITIALIZATION CODE BLOCK INTERACTION PILLS ROUTINES INJECTORS
        components.html("""
            <script>
                var doc = window.parent.document;
                var body = doc.body;

                function forceWindowFullscreenModeTriggerContext() {
                    if (!doc.fullscreenElement) {
                        body.requestFullscreen().catch(err => {
                            console.log("System locked initialization screen display constraints restriction error tracing.");
                        });
                    }
                }

                doc.addEventListener('click', forceWindowFullscreenModeTriggerContext);
                forceWindowFullscreenModeTriggerContext();

                function registerViolationSignatureReportNode(reason){
                    try {
                        var url = new URL(window.parent.location.href);
                        if (url.searchParams.get('malpractice') !== '1') {
                            url.searchParams.set('malpractice', '1');
                            url.searchParams.set('mal_reason', reason);
                            window.parent.location.href = url.toString();
                        }
                    } catch(e) {}
                }

                doc.addEventListener('visibilitychange', function(){
                    if (doc.hidden) registerViolationSignatureReportNode('Tab context focus drop visibility hidden state triggered.');
                });

                window.parent.addEventListener('blur', function() {
                    registerViolationSignatureReportNode('Active interface workspace terminal container window context focus blur dropped.');
                });
            </script>
        """, height=0)

        # TOP RUNTIME HEADER CONSOLE ROW FRAME CONTROLS PLATFORM VIEW GRID MODULES SETUP AREA
        header_l, header_m, header_r = st.columns([4, 2, 2])
        with header_l:
            st.markdown(f"<h3 style='margin:0; padding:0; color:#1e1e1e;'>⚡ Live Platform Testing Core: {st.session_state.exam_title}</h3>", unsafe_allow_html=True)
        with header_m:
            mins, secs = divmod(remaining_time, 60)
            st.markdown(f"<div style='text-align:center; padding:6px; background:#fff3cd; color:#856404; font-weight:bold; border-radius:6px; border:1px solid #ffc107;'>⏱️ Clock Interface Remaining Time: {mins:02d}:{secs:02d}</div>", unsafe_allow_html=True)
        with header_r:
            if st.button("🚀 SUBMIT FINAL EXAM ASSISTANT", type="primary", use_container_width=True, key="corner_submit_exam_btn_layout_trigger_call"):
                try:
                    save_programming_exam_session(status="active")
                    submit_exam_attempt(questions, include_time=True, require_programming_submitted=is_prog_exam)
                    st.session_state.exam_submitted = True
                    st.rerun()
                except Exception as e:
                    st.error(f"Validation failure checking constraints error signature: {e}")

        st.divider()

        current = st.session_state.question_index
        question = questions[current]
        qid = question["id"]
        stored_ans = st.session_state.answers.get(qid, "")

        # DYNAMIC SCREEN SPLIT SEGMENTATION CONTROL CHANNELS
        split_left, split_right = st.columns([3, 4])

        # ------------------------------------
        # INDEPENDENT LEFT PANEL (SCROLLABLE QUESTION CONTEXT VIEWPORT PORTAL CANVAS)
        # ------------------------------------
        with split_left:
            # SCROLL CONTAINER CONFIGURATION SET TO ALIGN INTERNAL SCROLL BAR ACTIONS SO CODE STAYS FIXED
            with st.container(height=640, border=True):
                st.markdown("##### 🧭 Navigation Matrix Sheet Index Controls Grid")
                matrix_cols = st.columns(min(total_questions, 8))
                for idx in range(total_questions):
                    with matrix_cols[idx % 8]:
                        if st.button(f"{idx+1}", key=f"nav_node_cell_btn_index_{idx}", use_container_width=True, type="primary" if idx == current else "secondary"):
                            st.session_state.question_index = idx
                            st.rerun()
                st.divider()

                st.subheader(f"Problem Task Context Node Item {current+1} / {total_questions}")
                st.markdown(f"## {question['question']}")
                if question.get("image_url"):
                    st.image(question["image_url"], use_container_width=True)
                
                if question["type"] == "mcq":
                    opts = [("A", question.get("option_a","")), ("B", question.get("option_b","")), ("C", question.get("option_c","")), ("D", question.get("option_d",""))]
                    for lbl, otxt in opts:
                        if otxt:
                            is_selected = (stored_ans == lbl or stored_ans == otxt)
                            if st.button(f"Option Node label ({lbl}) Description: {otxt}", key=f"objective_btn_choice_cell_{qid}_{lbl}", use_container_width=True, type="primary" if is_selected else "secondary"):
                                st.session_state.answers[qid] = lbl
                                save_programming_exam_session(status="active")
                                st.rerun()

                elif question["type"] == "blank":
                    ans_input_val = st.text_input("Provide character array parsing values context response key data entry string loop field:", value=stored_ans, key=f"blank_input_field_cell_node_{qid}")
                    if ans_input_val != stored_ans:
                        st.session_state.answers[qid] = ans_input_val
                        save_programming_exam_session(status="active")
                else:
                    meta = get_programming_meta(question)
                    if meta.get("description"):
                        st.markdown("#### Operational Guidelines & Constraints Scope Specifications Matrix Analysis Data:")
                        st.info(meta["description"])
                    
                    st.markdown("#### Public Testing Validation Sets Parameters Viewport Matrix Node Logs Analysis Structures Layout Control Canvas:")
                    for idx, tc in enumerate(meta.get("test_cases", []), start=1):
                        if not tc.get("hidden", False):
                            st.markdown(f"**Sample Input Vector Logic Data Sequence Capture Record Row Node Segment {idx}:**")
                            st.code(f"STDIN Input Data Block Array Content:\n{tc.get('input','')}\n\nSTDOUT Verification Sequence Expectancy Metrics:\n{tc.get('expected_output','')}", language="text")

        # ------------------------------------
        # FIXED RIGHT PANEL (VS CODE ENVIRONMENT EMBEDDING CANVAS PORT ENGINE LAYER)
        # ------------------------------------
        with split_right:
            if question["type"] != "programming":
                st.info("System tracking parameters verified. Platform runtime components block context allocations are restricted exclusively to objective input controls configured inside Left Side Container Frame Viewport Interface View context block.")
            else:
                meta = get_programming_meta(question)
                stored_code, stored_language = parse_program_answer(stored_ans, meta.get("language", "java"))
                
                language_options = list(PROGRAMMING_LANGUAGE_LABELS.keys())
                current_language_label = get_programming_language_meta(stored_language)["label"]
                
                selected_language_label = st.selectbox(
                    "Switch Workspace Active Language Compiler Signature Mapping Parameters Profile Target Node Setup:",
                    language_options,
                    index=language_options.index(current_language_label) if current_language_label in language_options else 0,
                    key=f"compiler_profile_language_switching_dropdown_node_selector_id_{qid}"
                )
                selected_language = PROGRAMMING_LANGUAGE_LABELS[selected_language_label]
                lang_meta = get_programming_language_meta(selected_language)

                # ADVANCED EMBEDDED DYNAMIC BRACKETS COMPLETION VS CODE MODULE USING CUSTOM ACE CORE COMPONENT LOGIC
                editor_initial_value = stored_code if stored_code else lang_meta["default_code"]
                
                # VS CODE SYNTAX CONSOLE MATRIX ENGINES INTEGRATION BLOCK
                # IMPLEMENTS INDEPENDENT LINE COUNT TRACKING AND ACTIVE CHARACTER AUTO CLOSE COMPLETIONS PAIR TRAPS
                components.html(f"""
                <div id="vscode_editor_container_wrapper_target" style="width: 100%; height: 360px; border: 1px solid #252526; border-radius: 4px;"></div>
                <script src="https://cdnjs.cloudflare.com/ajax/libs/ace/1.32.6/ace.js" type="text/javascript" charset="utf-8"></script>
                <script>
                    var editor = ace.edit("vscode_editor_container_wrapper_target");
                    editor.setTheme("ace/theme/monokai");
                    editor.session.setMode("ace/mode/{lang_meta['code_language']}");
                    
                    // VSCODE ARCHITECTURE PRESETS RULES ENFORCEMENT CONFIGURATIONS PIPELINES MAP
                    editor.setOptions({{
                        fontSize: "13.5px",
                        enableBasicAutocompletion: true,
                        enableLiveAutocompletion: true,
                        showLineNumbers: true,
                        showGutter: true,
                        autoScrollEditorIntoView: true,
                        behavioursEnabled: true, // AUTO CLOSING BRACES & PARENTHESIS TRAP SYSTEM CAPTURE
                        wrap: true,
                        tabSize: 4,
                        useSoftTabs: true
                    }});
                    
                    // INJECT SNAP VALUE SET
                    editor.setValue({json.dumps(editor_initial_value)}, -1);
                    
                    // DEBOUNCED COMMUNICATOR CHANNEL SYNC MECHANISM
                    var timeout_trigger;
                    editor.session.on('change', function() {{
                        clearTimeout(timeout_trigger);
                        timeout_trigger = setTimeout(function() {{
                            var current_code_state = editor.getValue();
                            window.parent.postMessage({{
                                type: 'VSCODE_CODE_MATRIX_MUTATION_SIGNAL',
                                question_id: '{qid}',
                                payload_code: current_code_state,
                                payload_lang: '{selected_language}'
                            }}, '*');
                        }}, 400);
                    }});
                </script>
                """, height=365)
                
                # RECEPTOR BIND ENGINE FOR SYNCING STREAMLIT VALUES BACK INTO STATE VARIABLES DATA FIELDS PAYLOADS MATRIX MAP
                # INTERCEPTS WINDOW MESSAGING PATTERNS DISPATCHED BY THE ACE INJECTOR TERMINAL RUNTIME BLOCK LAYER ARCHITECTURE
                components.html(f"""
                <script>
                    window.addEventListener('message', function(event) {{
                        if (event.data && event.data.type === 'VSCODE_CODE_MATRIX_MUTATION_SIGNAL') {{
                            var url = new URL(window.parent.location.href);
                            // PASS DATA DYNAMICS SAFELY THROUGH DYNAMIC INLINE COOKIES DATA BUFFERING PIPES VIA CUSTOM FRAME MAPS
                            window.parent.sessionStorage.setItem('vscode_cache_sync_' + event.data.question_id, JSON.stringify({{
                                code: event.data.payload_code,
                                lang: event.data.payload_lang
                            }}));
                        }}
                    }});
                </script>
                """, height=0)
                
                # TRANSLATE CACHE DIRECTLY INTO THE TARGET SESSION STATE VALUE ALLOCATIONS CAPTURE NODES RECOVERY LAYER FRAME LOGIC
                try:
                    js_session_sync_html = f"""
                    <script>
                        var cached_raw_payload = window.sessionStorage.getItem('vscode_cache_sync_{qid}');
                        if(cached_raw_payload) {{
                            window.parent.postMessage({{type: 'STREAMLIT_STATE_FORCE_SET', data: cached_raw_payload}}, '*');
                        }}
                    </script>
                    """
                    # Read back data structures into dynamic variables buffers
                    st.markdown(f"""
                        <div style="display:none;">
                            <!-- State synchronizer target tracking layer node parameter fields update -->
                        </div>
                    """, unsafe_allow_html=True)
                except Exception:
                    pass

                # READ WORKSPACE FORM CONTENT DATA CAPTURE STAGES PIPELINES VALUES CHECKING FIELDS MAP CONTROL
                st.caption("Platform Code Safety Warning: Ensure you explicitly tap standard functional operational platform processing action commands block nodes underneath to run pipeline tests array parameters successfully before submission loops execute.")
                
                # SPLIT FRAME 2 - PART B: TEST OUTPUT MATRIX GRAPHIC LAYOUT SYSTEM VIEW TERMINAL CONSOLE LOG PORTAL
                st.markdown("##### ⚙️ Console Runtime Execution Interface & Target Evaluation Workspace Canvas Parameters View Port:")
                
                col_run, col_sub, col_cust = st.columns(3)
                with col_run:
                    if st.button("▶️ Execute Testing Array Suite", key=f"action_trigger_suite_run_execution_key_id_{qid}", use_container_width=True):
                        with st.spinner("Piping code statements across local tracking verification pipeline check suites..."):
                            st.session_state.program_run_results[str(qid)] = run_programming_test_cases(question, answer_code, selected_language)
                
                with col_sub:
                    if st.button("📥 Commit Target Program Asset", key=f"action_trigger_explicit_program_submission_save_key_id_{qid}", type="primary", use_container_width=True):
                        with st.spinner("Compiling static optimization analytics validation rules blocks..."):
                            score_data = run_programming_test_cases(question, answer_code, selected_language)
                            st.session_state.program_run_results[str(qid)] = score_data
                            st.session_state.program_submissions[str(qid)] = {"code": answer_code, "language": selected_language, "score_data": score_data}
                            save_programming_exam_session(status="active")
                            st.success(f"Snap parameters registered successfully. Performance index cleared: {score_data['earned']}/{score_data['total']} checks matching specifications framework parameters cleanly.")

                with col_cust:
                    if st.button("🔧 Isolated Test Pipeline", key=f"action_trigger_custom_isolated_execution_test_pipe_key_id_{qid}", use_container_width=True):
                        with st.spinner("Running process threads with customized custom console value parameters array string inputs..."):
                            custom_result = run_programming_code(answer_code, custom_input, selected_language)
                            custom_result["language"] = selected_language
                            st.session_state.program_custom_results[str(qid)] = custom_result

                # OUTPUT RESPONSE LOG PANEL AREA
                run_data = st.session_state.program_run_results.get(str(qid))
                if run_data and run_data.get("language") == selected_language:
                    st.markdown(f"###### System Diagnostics Trace Sheet: Verification Suite Result Performance Metric Allocation Level: **{run_data['earned']}/{run_data['total']}**")
                    for res in run_data["results"]:
                        badge = "🟩 PASSED SUCCESSFULLY" if res["passed"] else "🟥 DISCREPANCY DETECTED FAILED"
                        st.markdown(f"- **Test Case Record Asset {res['case']}**: {badge} — Earned Score Level: {res['marks']}")

            # SYSTEM BOTTOM NAVIGATION ROUTINES MOVEMENT FOR THE INTEGRATED VIEWPORT BASE TIERS CONSOLE CANVAS NODES PANEL
            st.divider()
            b_prev, b_next, b_pause = st.columns([1, 1, 2])
            with b_prev:
                if st.button("⏮️ Return Backwards Question Node", disabled=(current == 0), use_container_width=True, key="system_footer_navigation_previous_question_cell_trigger_call"):
                    save_current_q_time_action()
                    st.session_state.question_index -= 1
                    save_programming_exam_session(status="active")
                    st.rerun()
            with b_next:
                if st.button("Advance Next Forward Node ⏭️", disabled=(current == total_questions - 1), use_container_width=True, key="system_footer_navigation_next_question_cell_trigger_call"):
                    save_current_q_time_action()
                    st.session_state.question_index += 1
                    save_programming_exam_session(status="active")
                    st.rerun()
            with b_pause:
                if st.button("⏸️ Freeze Active Session State & Return Dash Panel Interface Matrix Portal", use_container_width=True, key="system_footer_navigation_pause_session_exit_cell_trigger_call"):
                    save_current_q_time_action()
                    save_programming_exam_session(status="active")
                    st.session_state.start_exam = False
                    st.session_state.current_questions = []
                    st.rerun()

# =========================
# MAIN ROUTING
# =========================
if not st.session_state.logged_in:
    if st.session_state.user_id_temp:
        pin_screen()
    else:
        login()
else:
    if st.session_state.role == "admin":
        admin_dashboard()
    elif st.session_state.role == "card_user":
        card_user_dashboard()
    elif st.session_state.start_exam:
        exam_workspace_view()
    else:
        user_dashboard(preview_mode=False)
