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

def enable_textarea_tab_support():
    st.components.v1.html(
        """
        <script>
        const attachTabs = () => {
            const doc = window.parent.document;
            doc.querySelectorAll('textarea').forEach((ta) => {
                if (ta.dataset.tabInsertReady === '1') return;
                ta.dataset.tabInsertReady = '1';
                ta.addEventListener('keydown', (event) => {
                    if (event.key !== 'Tab') return;
                    event.preventDefault();
                    event.stopPropagation();
                    const start = ta.selectionStart;
                    const end = ta.selectionEnd;
                    ta.setRangeText('    ', start, end, 'end');
                    ta.dispatchEvent(new Event('input', { bubbles: true }));
                });
            });
        };
        attachTabs();
        setInterval(attachTabs, 1000);
        </script>
        """,
        height=0,
    )

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
# OCR: IMAGE  QUESTION EXTRACT
# =========================
def extract_question_from_image(image_source):
    """Image nundi OCR.space API use chesi question + options extract cheyyali"""
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
            st.error("OCR_SPACE_API_KEY Streamlit secrets  add .")
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
            st.error("Image  text clear  .")
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
                    card_user_data = supabase.table("card_users").select("*").eq("app_pin", pin).execute()
                    if card_user_data.data:
                        urow = card_user_data.data[0]
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
        st.warning("Attendance table database  . Admin SQL run .")
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
          <div class="att-sub">Login    green   (last 1 year)</div>
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
        st.error(f"Progress load avvaledu: {e}")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Overall Marks", f"{progress['overall_marks_pct']}%")
    c2.metric("Marks", f"{progress['overall_marks_scored']}/{progress['overall_marks_total']}")
    c3.metric("Class Progress", f"{progress['overall_class_pct']}%")
    c4.metric("Pending", f"{len(progress['pending_classes'])} classes / {len(progress['pending_exams'])} exams")

    st.progress(progress["overall_marks_pct"] / 100, text=f"Overall marks: {progress['overall_marks_pct']}%")
    st.progress(progress["overall_class_pct"] / 100, text=f"Classes completed: {progress['overall_done_classes']}/{progress['overall_total_classes']}")

    st.subheader("Module-wise Progress")
    for item in progress["modules"]:
        module = item["module"]
        with st.container(border=True):
            st.markdown(f"#### {module.get('title', 'Module')}")
            m1, m2 = st.columns(2)
            with m1:
                st.caption(f"Marks: {item['marks_scored']}/{item['marks_total']} ({item['marks_pct']}%)")
                st.progress(item["marks_pct"] / 100)
            with m2:
                st.caption(f"Classes: {item['class_done']}/{item['class_total']} ({item['class_pct']}%)")
                st.progress(item["class_pct"] / 100)

    st.subheader("Pending Classes")
    if not progress["pending_classes"]:
        st.success("All classes complete ayyayi!")
    else:
        for cls in progress["pending_classes"]:
            with st.container(border=True):
                col_info, col_btn = st.columns([4, 1])
                with col_info:
                    st.markdown(f"**{cls.get('title', 'Class')}**")
                    if cls.get("_submodule_title"):
                        st.caption(cls["_submodule_title"])
                with col_btn:
                    if st.button("Open", key=f"prog_open_cls_{cls['id']}", use_container_width=True):
                        focus_student_class(cls.get("id"))

    st.subheader("Pending Exams")
    if not progress["pending_exams"]:
        st.success("Pending exams levu.")
    else:
        for row in progress["pending_exams"]:
            exam = row["exam"]
            with st.container(border=True):
                col_info, col_btn = st.columns([4, 1])
                with col_info:
                    st.markdown(f"**{exam.get('title', 'Exam')}**")
                    st.caption(f"{row['total_q']} questions  {exam.get('duration_mins', 30)} mins")
                with col_btn:
                    if st.button("Open", key=f"prog_open_exam_{exam['id']}", use_container_width=True, type="primary"):
                        start_student_exam(exam)

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
        placeholder="Program ki kavalsina input ikkada type cheyyandi..."
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
            st.warning(f"{lang_meta['label']} code enter cheyyandi.")
            return
        with st.spinner(f"{lang_meta['label']} program run avuthundi..."):
            result = run_programming_code(code, st.session_state.practice_input, selected_language)
        st.subheader("Output")
        st.code(result.get("stdout", ""), language="text")
        if result.get("stderr"):
            st.subheader("Errors / Compiler Messages")
            st.code(result["stderr"], language="text")
        meta = []
        if result.get("time") is not None:
            meta.append(f"Time: {result['time']}s")
        if result.get("memory") is not None:
            meta.append(f"Memory: {result['memory']} KB")
        status_text = result.get("status", "Unknown")
        if result.get("ok"):
            st.success(f"Status: {status_text}" + (f" | {' | '.join(meta)}" if meta else ""))
        else:
            st.error(f"Status: {status_text}" + (f" | {' | '.join(meta)}" if meta else ""))


def show_java_practice_tab():
    show_code_practice_tab()


def show_programming_questions_tab(user_id):
    st.title("Programming Questions")
    exams = supabase.table("exams").select("*").eq("enabled", True).execute().data or []
    rows = []
    for exam in exams:
        q_rows = supabase.table("questions").select("*").eq("exam_id", exam["id"]).eq("type", "programming").execute().data or []
        for q in q_rows:
            rows.append({"exam": exam, "question": q})

    if not rows:
        st.info("Programming questions levu.")
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
            label = "Attempted / Solve Again" if attempted else "Solve"
            has_pwd = exam.get("password") and str(exam.get("password")).strip()
            entered_pwd = ""
            if has_pwd:
                entered_pwd = st.text_input("Access Code", type="password", key=f"prog_pwd_{q['id']}", label_visibility="collapsed")
            if st.button(label, key=f"solve_prog_{q['id']}", use_container_width=True, type="primary" if not attempted else "secondary"):
                if has_pwd and entered_pwd.strip() != str(exam.get("password")).strip():
                    st.error("Wrong Password!")
                else:
                    start_exam_with_questions(exam, [q])
                    st.rerun()

# =========================
# REVIEW SHEET (styled like screenshot)
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
                badge_style = (
                    "background:#e8f8ef;color:#1e7e45;font-weight:700;font-size:0.75rem;"
                    "padding:2px 10px;border-radius:20px;margin-left:8px;vertical-align:middle;"
                ) if is_correct else (
                    "background:#fdecea;color:#c0392b;font-weight:700;font-size:0.75rem;"
                    "padding:2px 10px;border-radius:20px;margin-left:8px;vertical-align:middle;"
                )
                badge_txt = "Correct" if is_correct else "Incorrect"
                st.markdown(
                    f"<div style='font-weight:700;font-size:1rem;margin-bottom:6px;'>"
                    f"Question {i+1} &nbsp;<span style='{badge_style}'>{badge_txt}</span></div>",
                    unsafe_allow_html=True
                )
                st.markdown(q["question"])
                if q.get("image_url"):
                    st.image(q["image_url"], width=320)
            with bcol:
                qid = q["id"]
                if qid in st.session_state.explain_selected:
                    if st.button("Marked", key=f"exp_{qid}", use_container_width=True, type="primary"):
                        st.session_state.explain_selected.discard(qid)
                        st.rerun()
                else:
                    if st.button("Explain", key=f"exp_{qid}", use_container_width=True):
                        st.session_state.explain_selected.add(qid)
                        st.rerun()

            t_spent = get_answer_time_spent(db_attempt[0]["id"], q["id"])
            if t_spent and t_spent > 0:
                mins_s, secs_s = divmod(t_spent, 60)
                tstr = f"{mins_s}m {secs_s}s" if mins_s > 0 else f"{secs_s}s"
                st.caption(f" Time spent: **{tstr}**")

            if q["type"] == "mcq":
                opts = [("A", q.get("option_a","")), ("B", q.get("option_b","")),
                        ("C", q.get("option_c","")), ("D", q.get("option_d",""))]
                correct_display = c_ans
                opts_html = ""
                for lbl, otxt in opts:
                    is_opt_correct = (
                        c_ans.upper() == lbl
                        or c_ans.lower() == str(otxt).strip().lower()
                    )
                    is_user_pick = (
                        str(u_ans).strip().upper() == lbl
                        or str(u_ans).strip().lower() == str(otxt).strip().lower()
                    )
                    if is_opt_correct:
                        correct_display = f"{lbl}. {otxt}"
                        bg, br, col, suffix, fw = "#eafaf0","#27ae60","#1b5e34","  ","700"
                    elif is_user_pick and not is_correct:
                        bg, br, col, suffix, fw = "#fdecea","#e74c3c","#c0392b","  (Your Answer) Bell System ","700"
                    else:
                        bg, br, col, suffix, fw = "#ffffff","#dfe6ee","#2c3e50","","400"
                    opts_html += (
                        f"<div style='background:{bg};border:1.5px solid {br};border-radius:10px;"
                        f"padding:12px 16px;margin-bottom:8px;color:{col};font-weight:{fw};'>"
                        f"{lbl}. {otxt}{suffix}</div>"
                    )
                st.markdown(opts_html, unsafe_allow_html=True)
                st.markdown(
                    f"<div style='background:#eaf2fb;border:1.5px solid #4a90d9;border-radius:10px;"
                    f"padding:12px 16px;margin:8px 0;color:#1a5276;font-weight:700;'>"
                    f"Correct Answer: {correct_display}</div>",
                    unsafe_allow_html=True
                )

            elif q["type"] == "programming":
                try:
                    prog_ans = json.loads(u_ans) if isinstance(u_ans, str) and u_ans.strip().startswith("{") else {"code": u_ans}
                except Exception:
                    prog_ans = {"code": u_ans}
                st.caption(f"Score: {prog_ans.get('earned', 0)}/{prog_ans.get('total', get_question_max_marks(q))} ({prog_ans.get('percentage', 0)}%)")
                answer_language = prog_ans.get("language", get_programming_meta(q).get("language", "java"))
                st.code(prog_ans.get("code", ""), language=get_programming_language_meta(answer_language)["code_language"])
                for res in prog_ans.get("results", []):
                    badge = " Passed" if res.get("passed") else " Failed"
                    st.caption(f"Test Case {res.get('case')}: {badge}  {res.get('marks', 0)} marks")

            else:
                ans_bg = "#eafaf0" if is_correct else "#fdecea"
                ans_br = "#27ae60" if is_correct else "#e74c3c"
                ans_col = "#1b5e34" if is_correct else "#c0392b"
                ans_sfx = " " if is_correct else " (Your Answer) "
                st.markdown(
                    f"<div style='background:{ans_bg};border:1.5px solid {ans_br};border-radius:10px;"
                    f"padding:12px 16px;margin-bottom:8px;color:{ans_col};font-weight:700;'>"
                    f"Your Answer: {u_ans}{ans_sfx}</div>",
                    unsafe_allow_html=True
                )
                if not is_correct:
                    st.markdown(
                        f"<div style='background:#eaf2fb;border:1.5px solid #4a90d9;border-radius:10px;"
                        f"padding:12px 16px;margin:8px 0;color:#1a5276;font-weight:700;'>"
                        f"Correct Answer: {c_ans}</div>",
                        unsafe_allow_html=True
                    )

            explanation = str(q.get("explanation", "") or "").strip()
            if explanation and not explanation.startswith(PROGRAMMING_META_PREFIX):
                st.markdown(
                    f"<div style='background:#f5f6fa;border:1px solid #d0d8e8;border-radius:10px;"
                    f"padding:14px 16px;margin-top:6px;'>"
                    f"<div style='font-weight:700;margin-bottom:5px;'>Answer Explanation</div>"
                    f"<div style='color:#444;line-height:1.6;'>{explanation}</div></div>",
                    unsafe_allow_html=True
                )

            st.markdown(
                "<div style='margin-top:8px;'>"
                "<span style='color:#e74c3c;font-size:0.82rem;cursor:pointer;'> Report Question</span>"
                "</div>",
                unsafe_allow_html=True
            )

    st.divider()
    selected_count = len(st.session_state.explain_selected)
    if selected_count > 0:
        st.info(f" {selected_count} questions marked for explanation")
        if st.button(f" Admin  Explain Request  ({selected_count} questions)", type="primary", use_container_width=True):
            try:
                supabase.table("explain_requests").insert({
                    "user_id": str(st.session_state.user_id),
                    "exam_id": str(st.session_state.exam_id),
                    "question_ids": json.dumps(list(st.session_state.explain_selected)),
                    "status": "pending"
                }).execute()
                uinfo = supabase.table("users").select("name").eq("id", st.session_state.user_id).execute().data
                uname = uinfo[0]["name"] if uinfo else "Student"
                send_notification(f" {uname} {selected_count} questions  explanation request !")
                st.session_state.explain_selected = set()
                st.success("Request sent.")
                st.rerun()
            except Exception as e:
                st.error(f"Request error: {e}")

# =========================
# PPT GENERATOR
# =========================
def generate_exam_ppt(questions, exam_title, q_requesters=None):
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    import io, requests as _req

    def rgb(h):
        h = h.lstrip("#")
        return RGBColor(int(h[0:2],16), int(h[2:4],16), int(h[4:6],16))

    def box(sl, x, y, w, h, fill, border=None, bw=Pt(1)):
        s = sl.shapes.add_shape(1, Inches(x), Inches(y), Inches(w), Inches(h))
        s.fill.solid(); s.fill.fore_color.rgb = rgb(fill)
        if border: s.line.color.rgb = rgb(border); s.line.width = bw
        else: s.line.fill.background()
        return s

    def txt(sl, text, x, y, w, h, sz=13, bold=False, color="1A1A2E", align=PP_ALIGN.LEFT, italic=False):
        tb = sl.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = tb.text_frame; tf.word_wrap = True
        p = tf.paragraphs[0]; p.alignment = align
        r = p.add_run(); r.text = str(text)
        r.font.size = Pt(sz); r.font.bold = bold
        r.font.italic = italic; r.font.color.rgb = rgb(color)
        return tb

    NAV="1E2761"; LGT="F4F6FB"; ACC="4A90D9"; GRN="27AE60"; GRD="1E8449"; WHT="FFFFFF"; DRK="1A1A2E"; MUT="7F8C8D"
    prs = Presentation(); prs.slide_width = Inches(10); prs.slide_height = Inches(5.625)
    BL = prs.slide_layouts[6]

    ts = prs.slides.add_slide(BL)
    box(ts, 0, 0, 10, 5.625, NAV); box(ts, 0, 2.5, 10, 0.06, ACC)
    txt(ts, exam_title or "Exam Review", 0.5, 1.0, 9, 1.2, sz=36, bold=True, color=WHT, align=PP_ALIGN.CENTER)
    txt(ts, f"{len(questions)} Questions", 0.5, 2.65, 9, 0.6, sz=20, color="CADCFC", align=PP_ALIGN.CENTER)
    txt(ts, "Correct  Green  |  Wrong  White", 0.5, 4.6, 9, 0.4, sz=12, italic=True, color="8899CC", align=PP_ALIGN.CENTER)

    for idx, q in enumerate(questions):
        sl = prs.slides.add_slide(BL); box(sl, 0, 0, 10, 5.625, LGT)
        cur_y = 0.18
        box(sl, 0.3, cur_y, 0.7, 0.42, ACC)
        txt(sl, f"Q{idx+1}", 0.3, cur_y, 0.7, 0.42, sz=14, bold=True, color=WHT, align=PP_ALIGN.CENTER)
        txt(sl, q.get("question",""), 1.12, cur_y, 8.55, 0.72, sz=15, bold=True, color=DRK)
        cur_y += 0.78
        if q_requesters and q.get("id") in q_requesters:
            names = q_requesters[q["id"]][:4]
            ns = " " + ",  ".join(names)
            if len(q_requesters[q["id"]]) > 4:
                ns += f"  +{len(q_requesters[q['id']])-4} more"
            box(sl, 0.3, cur_y, 9.4, 0.3, "FFF9C4", "F9A825", Pt(1))
            txt(sl, ns, 0.45, cur_y+0.02, 9.1, 0.28, sz=10, italic=True, color="7B5800")
            cur_y += 0.35
        box(sl, 0.3, cur_y, 9.4, 0.03, "D0D8E8"); cur_y += 0.1
        img_available = False
        if q.get("image_url"):
            try:
                import io as _io
                r2 = _req.get(q["image_url"], timeout=10, headers={"User-Agent":"Mozilla/5.0"})
                if r2.status_code == 200 and len(r2.content) > 500:
                    sl.shapes.add_picture(_io.BytesIO(r2.content), Inches(6.0), Inches(cur_y), Inches(3.7), Inches(2.5))
                    img_available = True
            except Exception:
                pass
        correct_ans = str(q.get("correct_answer","")).strip()
        if q.get("type","mcq") == "mcq":
            opts = [("A", q.get("option_a","")), ("B", q.get("option_b","")), ("C", q.get("option_c","")), ("D", q.get("option_d",""))]
            for i, (lbl, otxt) in enumerate(opts):
                ox = 0.3 if img_available else (0.3 if i % 2 == 0 else 5.2)
                oy = cur_y + i * 0.82 if img_available else cur_y + (i // 2) * 0.95
                ow, oh = (5.5, 0.72) if img_available else (4.5, 0.82)
                is_cor = (correct_ans.upper() == lbl or correct_ans.strip().lower() == str(otxt).strip().lower())
                bg = GRN if is_cor else WHT; tc = WHT if is_cor else DRK; br = GRN if is_cor else "C8D6E5"
                box(sl, ox, oy, ow, oh, bg, br, Pt(1.5))
                box(sl, ox+0.1, oy+0.16, 0.46, 0.46, GRD if is_cor else ACC)
                txt(sl, lbl, ox+0.1, oy+0.16, 0.46, 0.46, sz=12, bold=True, color=WHT, align=PP_ALIGN.CENTER)
                txt(sl, str(otxt), ox+0.68, oy+0.08, ow-0.8, oh-0.16, sz=13, color=tc)
            txt(sl, f"  Correct: {correct_ans}", 0.3, 5.15, 9, 0.35, sz=11, bold=True, color=GRN)
        else:
            box(sl, 0.3, cur_y, 9.4, 1.1, "EAF7EE", GRN, Pt(2))
            txt(sl, correct_ans, 0.5, cur_y+0.1, 9.0, 0.9, sz=14, bold=True, color=GRN)
        hint = str(q.get("hint","") or "").strip()
        if hint:
            txt(sl, f" {hint}", 0.3, 5.38, 9, 0.25, sz=10, italic=True, color=MUT)
        txt(sl, f"{idx+1}/{len(questions)}", 8.6, 5.38, 1.1, 0.25, sz=9, color=MUT, align=PP_ALIGN.RIGHT)

    es = prs.slides.add_slide(BL); box(es, 0, 0, 10, 5.625, NAV)
    txt(es, "End of Review", 0.5, 1.8, 9, 1.5, sz=38, bold=True, color=WHT, align=PP_ALIGN.CENTER)
    txt(es, "Keep improving!", 0.5, 3.4, 9, 0.6, sz=18, italic=True, color="CADCFC", align=PP_ALIGN.CENTER)

    buf = io.BytesIO(); prs.save(buf); buf.seek(0)
    return buf.read()

def check_mcq_correct(user_val, q):
    correct = str(q.get("correct_answer","")).strip()
    user = str(user_val).strip()
    if not user or not correct:
        return False
    if user.lower() == correct.lower():
        return True
    label_map = {
        "A": str(q.get("option_a","")), "B": str(q.get("option_b","")),
        "C": str(q.get("option_c","")), "D": str(q.get("option_d","")),
    }
    if user.upper() in label_map:
        return label_map[user.upper()].strip().lower() == correct.lower()
    if correct.upper() in label_map:
        return label_map[correct.upper()].strip().lower() == user.lower()
    return False


SUPRABHATAM_LANGUAGES = {
    "Telugu": "telugu_text",
    "English": "english_text",
    "Sanskrit": "sanskrit_text",
    "Hindi": "hindi_text",
    "Tamil": "tamil_text",
    "Kannada": "kannada_text",
}


def get_suprabhatam_sql():
    return """
create table if not exists suprabhatam_slokas (
  id uuid primary key default gen_random_uuid(),
  display_order integer not null,
  title text,
  image_url text,
  telugu_text text,
  english_text text,
  sanskrit_text text,
  hindi_text text,
  tamil_text text,
  kannada_text text,
  meaning text,
  created_at timestamptz default now()
);

create index if not exists suprabhatam_slokas_display_order_idx
on suprabhatam_slokas(display_order);

create table if not exists suprabhatam_access (
  user_id uuid primary key references users(id) on delete cascade,
  enabled boolean not null default true,
  updated_at timestamptz default now()
);
"""


def show_suprabhatam_styles():
    st.markdown("""
    <style>
    .supra-reader {
        border: 1px solid #d9dde7;
        background: #ffffff;
        border-radius: 8px;
        padding: 18px;
        margin: 12px 0 18px 0;
    }
    .supra-frame {
        display: grid;
        grid-template-columns: minmax(140px, 260px) 1fr;
        gap: 18px;
        align-items: stretch;
    }
    .supra-image {
        width: 100%;
        min-height: 180px;
        border: 5px solid #f49a73;
        border-radius: 8px;
        overflow: hidden;
        background: #f7f0e8;
    }
    .supra-image img {
        width: 100%;
        height: 100%;
        min-height: 180px;
        object-fit: cover;
        display: block;
    }
    .supra-quote {
        min-height: 180px;
        border: 1px solid #cfd3dc;
        border-right: 8px solid #f05a28;
        border-bottom: 8px solid #f05a28;
        padding: 26px 28px;
        display: flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        color: #1168c4;
        font-size: 1.55rem;
        line-height: 1.85;
        white-space: pre-wrap;
    }
    .supra-title {
        margin: 0 0 12px 0;
        color: #263047;
        font-size: 1.15rem;
        font-weight: 700;
    }
    .supra-meaning {
        margin-top: 14px;
        color: #3b4254;
        line-height: 1.7;
        white-space: pre-wrap;
    }
    @media (max-width: 760px) {
        .supra-frame { grid-template-columns: 1fr; }
        .supra-quote { font-size: 1.15rem; padding: 20px; }
    }
    </style>
    """, unsafe_allow_html=True)


def fetch_suprabhatam_slokas():
    try:
        return supabase.table("suprabhatam_slokas").select("*").order("display_order").execute().data or []
    except Exception as e:
        st.warning("Suprabhatam tables database lo create cheyyali. Admin SQL run cheyyandi.")
        return []


def user_has_suprabhatam_access(user_id):
    if st.session_state.get("role") == "admin":
        return True
    try:
        rows = supabase.table("suprabhatam_access").select("enabled").eq("user_id", user_id).eq("enabled", True).limit(1).execute().data
        return bool(rows)
    except Exception:
        return False


def render_suprabhatam_reader(slokas=None):
    slokas = slokas if slokas is not None else fetch_suprabhatam_slokas()
    if not slokas:
        st.info("Inka Suprabhatam slokas add cheyyaledu.")
        return

    st.subheader("Suprabhatam")
    sloka_payload = []
    for i, sloka in enumerate(slokas):
        sloka_payload.append({
            "title": sloka.get("title") or f"Slokam {i + 1}",
            "image_url": sloka.get("image_url") or "",
            "meaning": sloka.get("meaning") or "",
            "languages": {
                lang: sloka.get(col) or ""
                for lang, col in SUPRABHATAM_LANGUAGES.items()
            },
        })

    component_html = """
    <div class="book-wrap">
      <div class="toolbar" id="langButtons"></div>
      <div class="counter" id="counter"></div>
      <div class="book" id="book">
        <div class="page" id="page">
          <div class="imageBox" id="imageBox"></div>
          <div class="quoteBox">
            <div class="slokaTitle" id="slokaTitle"></div>
            <div class="slokaText" id="slokaText"></div>
            <div class="meaning" id="meaning"></div>
          </div>
        </div>
      </div>
      <div class="nav">
        <button id="prevBtn" type="button">Previous Slokam</button>
        <button id="nextBtn" type="button">Next Slokam</button>
      </div>
    </div>

    <style>
      * { box-sizing: border-box; }
      body {
        margin: 0;
        font-family: "Segoe UI", Arial, sans-serif;
        color: #263047;
        background: transparent;
      }
      .book-wrap {
        width: 100%;
        padding: 8px 4px 18px;
      }
      .toolbar {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin-bottom: 10px;
      }
      .toolbar button, .nav button {
        border: 1px solid #cfd6e4;
        background: #ffffff;
        color: #263047;
        border-radius: 8px;
        padding: 9px 13px;
        cursor: pointer;
        font-weight: 650;
      }
      .toolbar button.active {
        background: #1168c4;
        border-color: #1168c4;
        color: #ffffff;
      }
      .counter {
        font-size: 0.95rem;
        color: #5f6678;
        margin-bottom: 10px;
      }
      .book {
        perspective: 1800px;
      }
      .page {
        min-height: 315px;
        display: grid;
        grid-template-columns: minmax(155px, 280px) 1fr;
        gap: 18px;
        align-items: stretch;
        padding: 16px;
        border: 1px solid #d9dde7;
        border-radius: 8px;
        background:
          linear-gradient(90deg, rgba(0,0,0,0.08), rgba(255,255,255,0) 32px),
          #fffdf9;
        box-shadow: 0 10px 28px rgba(38, 48, 71, 0.12);
        transform-origin: left center;
      }
      .page.flip-next {
        animation: pageNext 520ms ease both;
      }
      .page.flip-prev {
        animation: pagePrev 520ms ease both;
      }
      @keyframes pageNext {
        0% { transform: rotateY(0deg); opacity: 1; }
        48% { transform: rotateY(-78deg); opacity: 0.45; }
        100% { transform: rotateY(0deg); opacity: 1; }
      }
      @keyframes pagePrev {
        0% { transform: rotateY(0deg); opacity: 1; }
        48% { transform: rotateY(72deg); opacity: 0.45; }
        100% { transform: rotateY(0deg); opacity: 1; }
      }
      .imageBox {
        min-height: 230px;
        border: 5px solid #f49a73;
        border-radius: 8px;
        overflow: hidden;
        background: #f7f0e8;
      }
      .imageBox img {
        width: 100%;
        height: 100%;
        min-height: 230px;
        object-fit: cover;
        display: block;
      }
      .quoteBox {
        min-height: 230px;
        border: 1px solid #cfd3dc;
        border-right: 8px solid #f05a28;
        border-bottom: 8px solid #f05a28;
        padding: 24px 28px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        text-align: center;
        background: #ffffff;
      }
      .slokaTitle {
        margin-bottom: 12px;
        color: #263047;
        font-weight: 750;
        font-size: 1.05rem;
      }
      .slokaText {
        color: #1168c4;
        font-size: 1.55rem;
        line-height: 1.8;
        white-space: pre-wrap;
      }
      .meaning {
        margin-top: 14px;
        color: #3b4254;
        line-height: 1.6;
        white-space: pre-wrap;
        text-align: left;
      }
      .nav {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
        margin-top: 14px;
      }
      .nav button:last-child {
        background: #1168c4;
        border-color: #1168c4;
        color: #ffffff;
      }
      button:disabled {
        opacity: 0.45;
        cursor: not-allowed;
      }
      @media (max-width: 760px) {
        .page { grid-template-columns: 1fr; }
        .slokaText { font-size: 1.15rem; }
        .quoteBox { padding: 20px; }
      }
    </style>

    <script>
      const slokas = __SLOKAS__;
      const languageOrder = __LANGUAGES__;
      let index = 0;
      let language = languageOrder.includes("Telugu") ? "Telugu" : languageOrder[0];

      const page = document.getElementById("page");
      const titleEl = document.getElementById("slokaTitle");
      const textEl = document.getElementById("slokaText");
      const meaningEl = document.getElementById("meaning");
      const imageBox = document.getElementById("imageBox");
      const counter = document.getElementById("counter");
      const prevBtn = document.getElementById("prevBtn");
      const nextBtn = document.getElementById("nextBtn");
      const langButtons = document.getElementById("langButtons");

      slokas.forEach((sloka) => {
        if (sloka.image_url) {
          const img = new Image();
          img.src = sloka.image_url;
        }
      });

      function availableLanguages() {
        const current = slokas[index];
        return languageOrder.filter((lang) => (current.languages[lang] || "").trim().length > 0);
      }

      function drawLanguageButtons() {
        const available = availableLanguages();
        if (!available.includes(language)) {
          language = available.includes("Telugu") ? "Telugu" : (available[0] || languageOrder[0]);
        }
        langButtons.innerHTML = "";
        available.forEach((lang) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.textContent = lang;
          btn.className = lang === language ? "active" : "";
          btn.addEventListener("click", () => {
            language = lang;
            render();
          });
          langButtons.appendChild(btn);
        });
      }

      function render() {
        const sloka = slokas[index];
        drawLanguageButtons();
        titleEl.textContent = sloka.title || `Slokam ${index + 1}`;
        const text = (sloka.languages[language] || "").trim() || "Selected language text inka add cheyyaledu.";
        textEl.textContent = `“${text}”`;
        meaningEl.textContent = sloka.meaning ? `Meaning: ${sloka.meaning}` : "";
        imageBox.innerHTML = sloka.image_url ? `<img src="${sloka.image_url}" alt="">` : "";
        counter.textContent = `Slokam ${index + 1} / ${slokas.length}`;
        prevBtn.disabled = index === 0;
        nextBtn.disabled = index === slokas.length - 1;
      }

      function turnPage(direction) {
        const nextIndex = index + direction;
        if (nextIndex < 0 || nextIndex >= slokas.length) return;
        page.classList.remove("flip-next", "flip-prev");
        void page.offsetWidth;
        page.classList.add(direction > 0 ? "flip-next" : "flip-prev");
        setTimeout(() => {
          index = nextIndex;
          render();
        }, 230);
      }

      prevBtn.addEventListener("click", () => turnPage(-1));
      nextBtn.addEventListener("click", () => turnPage(1));
      render();
    </script>
    """
    component_html = component_html.replace("__SLOKAS__", json.dumps(sloka_payload, ensure_ascii=False))
    component_html = component_html.replace("__LANGUAGES__", json.dumps(list(SUPRABHATAM_LANGUAGES.keys()), ensure_ascii=False))
    components.html(component_html, height=690, scrolling=True)


def show_suprabhatam_admin():
    st.title("Suprabhatam")
    st.caption("Manual ga slokas add cheyyandi. Display order prakaram book laga users ki kanipistundi.")

    slokas = fetch_suprabhatam_slokas()
    tab_add, tab_manage, tab_access, tab_preview = st.tabs(["Add Slokam", "Manage Slokas", "User Access", "Preview"])

    with tab_add:
        next_order = (max([int(s.get("display_order") or 0) for s in slokas]) + 1) if slokas else 1
        with st.form("add_suprabhatam_slokam"):
            order = st.number_input("Display Order", min_value=1, value=next_order, step=1)
            title = st.text_input("Slokam Title", value=f"Slokam {next_order}")
            image_file = st.file_uploader("Slokam mundu image upload", type=["png", "jpg", "jpeg", "webp"])
            image_url = st.text_input("Leda image URL paste cheyyandi")
            telugu_text = st.text_area("Telugu", height=120)
            english_text = st.text_area("English", height=120)
            sanskrit_text = st.text_area("Sanskrit", height=120)
            hindi_text = st.text_area("Hindi", height=100)
            tamil_text = st.text_area("Tamil", height=100)
            kannada_text = st.text_area("Kannada", height=100)
            meaning = st.text_area("Meaning / Notes", height=90)
            submitted = st.form_submit_button("Add Slokam", type="primary")
        if submitted:
            final_image_url = image_url.strip()
            if image_file:
                uploaded_url = upload_image_to_imgbb(image_file)
                final_image_url = uploaded_url or final_image_url
            payload = {
                "display_order": int(order),
                "title": title.strip() or f"Slokam {int(order)}",
                "image_url": final_image_url,
                "telugu_text": telugu_text.strip(),
                "english_text": english_text.strip(),
                "sanskrit_text": sanskrit_text.strip(),
                "hindi_text": hindi_text.strip(),
                "tamil_text": tamil_text.strip(),
                "kannada_text": kannada_text.strip(),
                "meaning": meaning.strip(),
            }
            try:
                supabase.table("suprabhatam_slokas").insert(payload).execute()
                st.success("Slokam add ayyindi.")
                st.rerun()
            except Exception as e:
                st.error(f"Slokam add avvaledu: {e}")

    with tab_manage:
        if not slokas:
            st.info("Inka slokas levu.")
        for sloka in slokas:
            with st.expander(f"{sloka.get('display_order')}. {sloka.get('title') or 'Slokam'}"):
                with st.form(f"edit_suprabhatam_{sloka['id']}"):
                    order = st.number_input("Display Order", min_value=1, value=int(sloka.get("display_order") or 1), step=1, key=f"order_{sloka['id']}")
                    title = st.text_input("Slokam Title", value=sloka.get("title") or "", key=f"title_{sloka['id']}")
                    image_file = st.file_uploader("Replace image", type=["png", "jpg", "jpeg", "webp"], key=f"img_{sloka['id']}")
                    image_url = st.text_input("Image URL", value=sloka.get("image_url") or "", key=f"url_{sloka['id']}")
                    telugu_text = st.text_area("Telugu", value=sloka.get("telugu_text") or "", height=100, key=f"te_{sloka['id']}")
                    english_text = st.text_area("English", value=sloka.get("english_text") or "", height=100, key=f"en_{sloka['id']}")
                    sanskrit_text = st.text_area("Sanskrit", value=sloka.get("sanskrit_text") or "", height=100, key=f"sa_{sloka['id']}")
                    hindi_text = st.text_area("Hindi", value=sloka.get("hindi_text") or "", height=80, key=f"hi_{sloka['id']}")
                    tamil_text = st.text_area("Tamil", value=sloka.get("tamil_text") or "", height=80, key=f"ta_{sloka['id']}")
                    kannada_text = st.text_area("Kannada", value=sloka.get("kannada_text") or "", height=80, key=f"ka_{sloka['id']}")
                    meaning = st.text_area("Meaning / Notes", value=sloka.get("meaning") or "", height=80, key=f"meaning_{sloka['id']}")
                    save_col, delete_col = st.columns(2)
                    save_clicked = save_col.form_submit_button("Save Changes", type="primary")
                    delete_clicked = delete_col.form_submit_button("Delete")
                if save_clicked:
                    final_image_url = image_url.strip()
                    if image_file:
                        uploaded_url = upload_image_to_imgbb(image_file)
                        final_image_url = uploaded_url or final_image_url
                    try:
                        supabase.table("suprabhatam_slokas").update({
                            "display_order": int(order),
                            "title": title.strip(),
                            "image_url": final_image_url,
                            "telugu_text": telugu_text.strip(),
                            "english_text": english_text.strip(),
                            "sanskrit_text": sanskrit_text.strip(),
                            "hindi_text": hindi_text.strip(),
                            "tamil_text": tamil_text.strip(),
                            "kannada_text": kannada_text.strip(),
                            "meaning": meaning.strip(),
                        }).eq("id", sloka["id"]).execute()
                        st.success("Slokam update ayyindi.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Update avvaledu: {e}")
                if delete_clicked:
                    try:
                        supabase.table("suprabhatam_slokas").delete().eq("id", sloka["id"]).execute()
                        st.success("Slokam delete ayyindi.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Delete avvaledu: {e}")

    with tab_access:
        try:
            users = supabase.table("users").select("id, name, email, role").eq("role", "user").order("name").execute().data or []
            access_rows = supabase.table("suprabhatam_access").select("*").execute().data or []
            access_map = {str(row["user_id"]): bool(row.get("enabled")) for row in access_rows}
        except Exception as e:
            users = []
            access_map = {}
        for user in users:
            uid = str(user["id"])
            label = f"{user.get('name') or 'No name'} - {user.get('email') or ''}"
            enabled = st.checkbox(label, value=access_map.get(uid, False), key=f"supra_access_{uid}")
            current = access_map.get(uid, False)
            if enabled != current:
                try:
                    if enabled:
                        supabase.table("suprabhatam_access").upsert({"user_id": uid, "enabled": True}, on_conflict="user_id").execute()
                    else:
                        supabase.table("suprabhatam_access").delete().eq("user_id", uid).execute()
                    st.rerun()
                except Exception as e:
                    st.error(f"Access update avvaledu: {e}")

    with tab_preview:
        render_suprabhatam_reader(slokas)


def admin_dashboard():
    st.sidebar.title("Admin Workspace")
    persist_browser_login()
    if st.sidebar.button("Logout", use_container_width=True):
        for key in defaults:
            st.session_state[key] = defaults[key]
        show_logout_redirect()

    st.sidebar.divider()
    if st.session_state.admin_preview_mode:
        if st.sidebar.button("Back to Admin View", use_container_width=True, type="primary"):
            st.session_state.admin_preview_mode = False
            st.rerun()
        user_dashboard(preview_mode=True)
        return
    else:
        show_notification_banner(st.session_state.user_id)
        if st.sidebar.button("Student View Preview", use_container_width=True):
            st.session_state.admin_preview_mode = True
            st.rerun()
    st.sidebar.divider()

    unread_admin = get_unread_count(st.session_state.user_id)
    label = f"Group Chat ({unread_admin})" if unread_admin > 0 else "Group Chat"
    
    menu = st.sidebar.selectbox("Navigation Control",
        ["Manage Course Content", "Manage Exams & Questions", "Student Results & Ranks", "Credit Cards", "Suprabhatam", label],
        key="admin_navigation")
    if "Group Chat" in menu:
        menu = "Group Chat"
    if menu == "Credit Cards":
        admin_credit_cards_dashboard()
        return
    if menu == "Suprabhatam":
        show_suprabhatam_admin()
        return

    if menu == "Manage Course Content":
        tab1, tab2, tab3 = st.tabs(["Modules Setup", "Submodules Setup", "Live/Recorded Classes"])

        with tab1:
            st.subheader("Manage Core Modules")
            with st.form("add_module_form", clear_on_submit=True):
                module_name = st.text_input("New Module Title")
                if st.form_submit_button(" Save Module"):
                    if module_name.strip():
                        supabase.table("modules").insert({"title": module_name}).execute()
                        st.success("Module Added!")
                        st.rerun()
            st.divider()
            modules = supabase.table("modules").select("*").execute().data
            for m in modules:
                col1, col2, col3 = st.columns([4, 1, 1])
                with col1:
                    new_m_title = st.text_input("Module Name", value=m["title"], key=f"mod_t_{m['id']}")
                with col2:
                    if st.button("Update", key=f"mod_u_{m['id']}", use_container_width=True):
                        supabase.table("modules").update({"title": new_m_title}).eq("id", m["id"]).execute()
                        st.success("Updated!"); st.rerun()
                with col3:
                    if st.button("Delete", key=f"mod_d_{m['id']}", type="secondary", use_container_width=True):
                        supabase.table("modules").delete().eq("id", m["id"]).execute()
                        st.warning("Deleted!"); st.rerun()

        with tab2:
            st.subheader("Manage Submodules")
            modules_list = supabase.table("modules").select("*").execute().data
            mod_options = {m["title"]: m["id"] for m in modules_list} if modules_list else {}
            with st.form("add_sub_form", clear_on_submit=True):
                sel_mod = st.selectbox("Select Parent Module", list(mod_options.keys()) or ["No modules yet"])
                sub_name = st.text_input("Submodule Title")
                if st.form_submit_button(" Save Submodule"):
                    if sub_name.strip() and sel_mod in mod_options:
                        supabase.table("submodules").insert({"module_id": mod_options[sel_mod], "title": sub_name}).execute()
                        st.success("Linked!"); st.rerun()
            st.divider()
            submodules = supabase.table("submodules").select("*").execute().data
            for s in submodules:
                p_module = supabase.table("modules").select("title").eq("id", s["module_id"]).execute().data
                p_title = p_module[0]["title"] if p_module else "Unknown"
                col1, col2, col3, col4 = st.columns([2, 3, 1, 1])
                with col1: st.caption(f"Parent: {p_title}")
                with col2:
                    new_s_title = st.text_input("Edit Title", value=s["title"], key=f"sub_t_{s['id']}", label_visibility="collapsed")
                with col3:
                    if st.button("Update", key=f"sub_u_{s['id']}", use_container_width=True):
                        supabase.table("submodules").update({"title": new_s_title}).eq("id", s["id"]).execute()
                        st.success("Updated!"); st.rerun()
                with col4:
                    if st.button("Delete", key=f"sub_d_{s['id']}", type="secondary", use_container_width=True):
                        supabase.table("submodules").delete().eq("id", s["id"]).execute()
                        st.warning("Deleted!"); st.rerun()

        with tab3:
            st.subheader("Manage Stream/Video Classes")
            sub_list = supabase.table("submodules").select("*").execute().data
            sub_options = {s["title"]: s["id"] for s in sub_list} if sub_list else {}
            with st.expander(" Add New Class Room"):
                with st.form("add_class_form", clear_on_submit=True):
                    sel_sub = st.selectbox("Link to Submodule", list(sub_options.keys()) or ["No submodules yet"])
                    c_title = st.text_input("Class Title")
                    c_link = st.text_input("Live Stream Link")
                    v_link = st.text_input("Recorded Video URL")
                    p_link = st.text_input("Notes PDF URL")
                    if st.form_submit_button(" Deploy Class"):
                        if sel_sub in sub_options:
                            supabase.table("classes").insert({
                                "submodule_id": sub_options[sel_sub], "title": c_title,
                                "class_link": c_link, "recorded_video": v_link, "notes_pdf": p_link
                            }).execute()
                            st.success("Class Broadcasted!"); st.rerun()
            st.divider()
            all_users = supabase.table("users").select("id, role").execute().data
            total_users = len([u for u in all_users if u.get("role") == "user"])
            classes = supabase.table("classes").select("*").execute().data
            for cls in classes:
                comp_data = supabase.table("class_completions").select("user_id").eq("class_id", cls["id"]).execute().data
                comp_count = len(comp_data)
                pct = int((comp_count / total_users * 100)) if total_users > 0 else 0
                with st.expander(f" {cls['title']}    {comp_count}/{total_users} students  ({pct}%)"):
                    col_prog, col_num = st.columns([5, 1])
                    with col_prog: st.progress(pct / 100)
                    with col_num: st.markdown(f"**{pct}%**")
                    if comp_count > 0:
                        with st.expander(f" {comp_count}  complete "):
                            for row in comp_data:
                                u = supabase.table("users").select("name, email").eq("id", row["user_id"]).execute().data
                                if u: st.caption(f" {u[0]['name']} ({u[0]['email']})")
                    st.divider()
                    ec_title = st.text_input("Title", value=cls["title"], key=f"ct_{cls['id']}")
                    ec_link = st.text_input("Live Link", value=cls.get("class_link",""), key=f"cl_{cls['id']}")
                    ev_link = st.text_input("Video Link", value=cls.get("recorded_video",""), key=f"cv_{cls['id']}")
                    ep_link = st.text_input("PDF Link", value=cls.get("notes_pdf",""), key=f"cp_{cls['id']}")
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("Save Changes", key=f"cu_{cls['id']}", type="primary", use_container_width=True):
                            supabase.table("classes").update({"title": ec_title, "class_link": ec_link, "recorded_video": ev_link, "notes_pdf": ep_link}).eq("id", cls["id"]).execute()
                            st.success("Saved!"); st.rerun()
                    with b2:
                        if st.button("Remove Class", key=f"cd_{cls['id']}", use_container_width=True):
                            supabase.table("classes").delete().eq("id", cls["id"]).execute()
                            st.warning("Deleted!"); st.rerun()

    elif menu == "Manage Exams & Questions":
        ex_tab1, ex_tab2, ex_tab3, ex_tab4, ex_tab5 = st.tabs([
            " Exams Setup", " Add Questions", " Review Papers", " Bulk Upload (CSV)", " AI Gen"
        ])

        with ex_tab1:
            st.subheader("Setup Dynamic Exams")
            classes_list = supabase.table("classes").select("*").execute().data
            cls_options = {c["title"]: c["id"] for c in classes_list} if classes_list else {}
            with st.form("create_exam_form", clear_on_submit=True):
                sel_cls = st.selectbox("Link with Lesson Class", list(cls_options.keys()) or ["No classes yet"])
                e_title = st.text_input("Exam Sheet Name")
                e_duration = st.number_input("Exam Duration (Minutes)", min_value=1, max_value=180, value=30)
                e_pwd = st.text_input("Exam Password (Optional)", type="password")
                c_en = st.checkbox("Turn On Exam", value=True)
                c_ans = st.checkbox("Enable Answers Visibility")
                if st.form_submit_button(" Generate Exam Layout"):
                    if sel_cls in cls_options:
                        supabase.table("exams").insert({
                            "class_id": cls_options[sel_cls], "title": e_title,
                            "duration_mins": int(e_duration),
                            "password": e_pwd.strip() if e_pwd.strip() else None,
                            "enabled": c_en, "show_answers": c_ans
                        }).execute()
                        st.success("Exam Created!"); st.rerun()
            with st.expander("Programming Exam Builder"):
                prog_questions = supabase.table("questions").select("*").eq("type", "programming").execute().data or []
                if not prog_questions:
                    st.info("Existing programming questions levu.")
                else:
                    builder_cls = st.selectbox("Class select cheyyandi", list(cls_options.keys()) or ["No classes yet"], key="prog_builder_class")
                    builder_title = st.text_input("Programming Exam Name", key="prog_builder_title")
                    builder_duration = st.number_input("Duration (Minutes)", min_value=1, max_value=180, value=60, key="prog_builder_duration")
                    builder_pwd = st.text_input("Password (Optional)", type="password", key="prog_builder_pwd")
                    builder_enabled = st.checkbox("Turn On Exam", value=True, key="prog_builder_enabled")
                    builder_show_answers = st.checkbox("Enable Answers Visibility", value=True, key="prog_builder_show_answers")

                    q_options = {}
                    for q in prog_questions:
                        marks = get_question_max_marks(q)
                        label = f"{q.get('question', 'Untitled')}  |  {marks} marks  |  QID: {q.get('id')}"
                        q_options[label] = q
                    selected_labels = st.multiselect("Programming Questions select cheyyandi", list(q_options.keys()), key="prog_builder_questions")

                    if st.button("Selected Questions tho Exam Create", type="primary", use_container_width=True, key="prog_builder_create"):
                        if builder_cls not in cls_options:
                            st.error("Class select cheyyandi.")
                        elif not builder_title.strip():
                            st.error("Exam name enter cheyyandi.")
                        elif not selected_labels:
                            st.error("At least one programming question select cheyyandi.")
                        else:
                            created = supabase.table("exams").insert({
                                "class_id": cls_options[builder_cls],
                                "title": builder_title.strip(),
                                "duration_mins": int(builder_duration),
                                "password": builder_pwd.strip() if builder_pwd.strip() else None,
                                "enabled": builder_enabled,
                                "show_answers": builder_show_answers,
                            }).execute().data
                            new_exam = created[0] if created else None
                            if not new_exam:
                                matches = supabase.table("exams").select("*").eq("title", builder_title.strip()).eq("class_id", cls_options[builder_cls]).execute().data or []
                                new_exam = matches[-1] if matches else None
                            if new_exam:
                                for label in selected_labels:
                                    src = q_options[label]
                                    supabase.table("questions").insert({
                                        "exam_id": new_exam["id"],
                                        "question": src.get("question", ""),
                                        "type": "programming",
                                        "option_a": src.get("option_a", ""),
                                        "option_b": src.get("option_b", ""),
                                        "option_c": src.get("option_c", ""),
                                        "option_d": src.get("option_d", ""),
                                        "correct_answer": src.get("correct_answer", "AUTO"),
                                        "hint": src.get("hint", ""),
                                        "image_url": src.get("image_url"),
                                        "explanation": src.get("explanation"),
                                    }).execute()
                                st.success("Programming exam create ayyindi!")
                                st.rerun()
            st.divider()
            st.write("###  Live Exam Controls")
            exams_all = supabase.table("exams").select("*").execute().data
            for ex in exams_all:
                with st.container(border=True):
                    st.markdown(f"####  **{ex['title']}**")
                    col_e1, col_e2, col_e3 = st.columns([2, 2, 2])
                    with col_e1:
                        updated_dur = st.number_input("Duration (Mins)", min_value=1, max_value=180, value=int(ex.get("duration_mins",30)), key=f"dur_{ex['id']}")
                    with col_e2:
                        updated_pwd = st.text_input("Password", value=str(ex.get("password","") or ""), key=f"pwd_ed_{ex['id']}")
                    with col_e3:
                        t_active = st.toggle("Active", value=ex["enabled"], key=f"tog_en_{ex['id']}")
                        t_ans = st.toggle("Show Answers", value=ex["show_answers"], key=f"tog_ans_{ex['id']}")
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("Save", key=f"up_ex_{ex['id']}", type="primary", use_container_width=True):
                            old_pwd = str(ex.get("password") or "")
                            new_pwd = updated_pwd.strip()
                            supabase.table("exams").update({
                                "duration_mins": int(updated_dur),
                                "password": new_pwd if new_pwd else None,
                                "enabled": t_active, "show_answers": t_ans
                            }).eq("id", ex["id"]).execute()
                            if new_pwd and new_pwd != old_pwd:
                                send_notification(f" '{ex['title']}' exam  password set : {new_pwd}")
                            st.success("Updated!"); st.rerun()
                    with col_btn2:
                        if st.button("Delete Exam", key=f"del_ex_{ex['id']}", type="secondary", use_container_width=True):
                            supabase.table("exams").delete().eq("id", ex["id"]).execute()
                            st.warning("Deleted!"); st.rerun()

        with ex_tab2:
            st.subheader("Add Questions")
            exams_q = supabase.table("exams").select("*").execute().data
            ex_options = {e["title"]: e["id"] for e in exams_q} if exams_q else {}
            st.markdown("####  Add Question")
            sel_ex = st.selectbox("Select Exam", list(ex_options.keys()) or ["No exams yet"], key="add_q_exam")

            img_col1, img_col2 = st.columns(2)
            with img_col1:
                img_url_input = st.text_input("Image URL", key="add_img_url", placeholder="https://...")
            with img_col2:
                img_file = st.file_uploader("Image upload", type=["jpg","jpeg","png","gif","webp"], key="add_img_file")

            if img_file:
                st.image(img_file, width=380)
            elif img_url_input.strip():
                try: st.image(img_url_input.strip(), width=380)
                except Exception: pass

            extract_source = img_file if img_file else (img_url_input.strip() or None)
            if extract_source:
                if st.button("Extract Question from Image", use_container_width=True, key="extract_ocr_btn"):
                    with st.spinner("OCR processing..."):
                        extracted = extract_question_from_image(extract_source)
                    if extracted:
                        st.session_state["aq_q_text"] = extracted.get("question", "")
                        st.session_state["aq_opt_A"]  = extracted.get("option_a", "")
                        st.session_state["aq_opt_B"]  = extracted.get("option_b", "")
                        st.session_state["aq_opt_C"]  = extracted.get("option_c", "")
                        st.session_state["aq_opt_D"]  = extracted.get("option_d", "")
                        st.session_state["aq_hint"]   = extracted.get("hint", "")
                        ans = extracted.get("correct_answer","").strip().upper()
                        if ans in ["A","B","C","D"]:
                            st.session_state["aq_correct_lbl"] = ans
                        q_type_ocr = extracted.get("type","mcq")
                        st.session_state["aq_q_type_idx"] = ["mcq","blank","programming"].index(q_type_ocr) if q_type_ocr in ["mcq","blank","programming"] else 0
                        st.rerun()

            st.divider()

            type_idx_default = st.session_state.get("aq_q_type_idx", 0)
            q_type = st.selectbox("Question Type", ["mcq","blank","programming"],
                                   index=type_idx_default, key="aq_q_type")

            q_text = st.text_area("Question / Title", key="aq_q_text")

            opt_vals = {"A": "", "B": "", "C": "", "D": ""}
            correct_lbl = st.session_state.get("aq_correct_lbl", "")
            h_text = st.text_input(" Hint", key="aq_hint")
            exp_text = ""
            prog_description = ""
            prog_test_cases = []

            if q_type == "programming":
                prog_language_label = st.selectbox("Programming Language", list(PROGRAMMING_LANGUAGE_LABELS.keys()), key="aq_prog_language")
                prog_language = PROGRAMMING_LANGUAGE_LABELS[prog_language_label]
                prog_description = st.text_area("Programming Description", key="aq_prog_desc")
                st.markdown("**Test Cases & Marks**")
                tc_count = st.number_input("Number of test cases", min_value=1, max_value=10, value=3, step=1, key="aq_tc_count")
                for idx in range(int(tc_count)):
                    with st.container(border=True):
                        st.markdown(f"##### Test Case {idx + 1}")
                        c_in, c_out, c_marks, c_hidden = st.columns([3, 3, 1, 1])
                        with c_in:
                            tc_input = st.text_area("Input", key=f"aq_tc_input_{idx}", height=90)
                        with c_out:
                            tc_output = st.text_area("Expected Output", key=f"aq_tc_output_{idx}", height=90)
                        with c_marks:
                            tc_marks = st.number_input("Marks", min_value=1, max_value=100, value=1, step=1, key=f"aq_tc_marks_{idx}")
                        with c_hidden:
                            tc_hidden = st.checkbox("Hidden", value=(idx > 0), key=f"aq_tc_hidden_{idx}")
                        prog_test_cases.append({
                            "input": tc_input,
                            "expected_output": tc_output,
                            "marks": int(tc_marks),
                            "hidden": bool(tc_hidden),
                        })
                correct_lbl = "AUTO"
            else:
                if q_type == "mcq":
                    for lbl in ["A","B","C","D"]:
                        c1, c2, c3 = st.columns([1, 6, 2])
                        with c1:
                            st.markdown(f"<div style='padding-top:8px;font-weight:700;font-size:1rem;'>{lbl}.</div>",
                                        unsafe_allow_html=True)
                        with c2:
                            v = st.text_input(f"Option {lbl}", key=f"aq_opt_{lbl}", label_visibility="collapsed")
                            opt_vals[lbl] = v
                        with c3:
                            cur_correct = st.session_state.get("aq_correct_lbl", "")
                            is_correct = cur_correct == lbl
                            if st.button(
                                " Correct" if is_correct else " Set Correct",
                                key=f"aq_setcor_{lbl}",
                                use_container_width=True,
                                type="primary" if is_correct else "secondary"
                            ):
                                st.session_state["aq_correct_lbl"] = lbl
                                st.rerun()

                    correct_lbl = st.session_state.get("aq_correct_lbl", "")
                    if correct_lbl:
                        opt_text = opt_vals.get(correct_lbl, "")
                        st.info(f" Correct Answer: **{correct_lbl}. {opt_text}**")
                else:
                    correct_lbl = st.text_input("Correct Answer", key="aq_blank_correct")

                exp_text = st.text_area(" Answer Explanation (optional)", key="aq_explanation")

            if st.button("Add Question", type="primary", key="add_q_btn", use_container_width=True):
                if sel_ex in ex_options and q_text.strip():
                    final_img_url = None
                    if img_file:
                        final_img_url = upload_image_to_imgbb(img_file)
                    elif img_url_input.strip():
                        final_img_url = img_url_input.strip()
                    explanation_value = make_programming_meta(prog_description, prog_test_cases, prog_language) if q_type == "programming" else (exp_text.strip() if exp_text.strip() else None)
                    supabase.table("questions").insert({
                        "exam_id": ex_options[sel_ex],
                        "question": q_text,
                        "type": q_type,
                        "option_a": opt_vals.get("A",""),
                        "option_b": opt_vals.get("B",""),
                        "option_c": opt_vals.get("C",""),
                        "option_d": opt_vals.get("D",""),
                        "correct_answer": correct_lbl,
                        "hint": h_text,
                        "image_url": final_img_url,
                        "explanation": explanation_value
                    }).execute()
                    for k in list(st.session_state.keys()):
                        if str(k).startswith("aq_tc_"):
                            st.session_state.pop(k, None)
                    for k in ["aq_q_text","aq_opt_A","aq_opt_B","aq_opt_C","aq_opt_D",
                              "aq_hint","aq_explanation","aq_prog_desc","aq_blank_correct","aq_correct_lbl","aq_q_type_idx"]:
                        st.session_state.pop(k, None)
                    st.success("Question added.")
                    st.rerun()

        with ex_tab4:
            st.subheader("Bulk Upload Questions (CSV)")
            exams = supabase.table("exams").select("id, title").execute()
            exam_options = {ex["title"]: ex["id"] for ex in exams.data} if exams.data else {}
            if exam_options:
                selected_exam = st.selectbox("Select Exam:", list(exam_options.keys()))
                exam_id_bulk = exam_options[selected_exam]
                uploaded_file = st.file_uploader("Upload CSV", type=["csv"])
                if uploaded_file is not None:
                    import pandas as pd, io as _io
                    try:
                        raw = uploaded_file.read()
                        try: df = pd.read_csv(_io.StringIO(raw.decode("utf-8")))
                        except UnicodeDecodeError: df = pd.read_csv(_io.StringIO(raw.decode("latin1")))
                        required = ["question", "type", "correct_answer"]
                        missing = [col for col in required if col not in df.columns]
                        if missing:
                            st.error(f"CSV   columns : {missing}")
                        else:
                            df = df.fillna("")
                            if st.button("Upload to DB"):
                                try:
                                    for _, row in df.iterrows():
                                        exp_val = str(row.get("explanation","")).strip()
                                        supabase.table("questions").insert({
                                            "exam_id": exam_id_bulk,
                                            "question": str(row.get("question","")),
                                            "type": str(row.get("type","mcq")),
                                            "option_a": str(row.get("option_a","")),
                                            "option_b": str(row.get("option_b","")),
                                            "option_c": str(row.get("option_c","")),
                                            "option_d": str(row.get("option_d","")),
                                            "correct_answer": str(row.get("correct_answer","")),
                                            "hint": str(row.get("hint","")),
                                            "explanation": exp_val if exp_val else None
                                        }).execute()
                                    st.success(f" {len(df)} questions uploaded!")
                                except Exception as e:
                                    st.error(f"Upload Error: {e}")
                    except Exception as e:
                        st.error(f"CSV : {e}")

        with ex_tab5:
            st.subheader("AI Question Generator (Gemini)")
            exams_ai = supabase.table("exams").select("*").execute().data
            ai_ex_options = {e["title"]: e["id"] for e in exams_ai} if exams_ai else {}
            sel_ai_ex = st.selectbox("Save to Exam", list(ai_ex_options.keys()) or ["No exams yet"], key="ai_gen_exam")
            lesson_text = st.text_area("Paste Lesson Content here:")
            if st.button("Generate Questions"):
                if not lesson_text.strip():
                    st.warning("Paste lesson text first.")
                else:
                    try:
                        prompt = (
                            "Convert this text into 5 MCQ questions in JSON format. "
                            "Return ONLY a JSON array, no markdown fences. Each item must have: "
                            "question, option_a, option_b, option_c, option_d, correct_answer, explanation. "
                            "correct_answer must exactly match the text of the correct option. "
                            "explanation should be 1-2 sentences explaining why that answer is correct. "
                            f"Text: {lesson_text}"
                        )
                        model = genai.GenerativeModel(model_name="gemini-2.0-flash-lite")
                        response = model.generate_content(prompt)
                        raw_text = response.text.strip().strip("`")
                        if raw_text.lower().startswith("json"):
                            raw_text = raw_text[4:].strip()
                        parsed_qs = json.loads(raw_text)
                        st.session_state.ai_generated_qs = parsed_qs
                        st.success(f" {len(parsed_qs)} questions generated!")
                    except Exception as e:
                        st.error(f"AI Error: {e}")

            if st.session_state.get("ai_generated_qs"):
                if sel_ai_ex in ai_ex_options:
                    if st.button("Save to DB", type="primary", use_container_width=True):
                        try:
                            for gq in st.session_state.ai_generated_qs:
                                supabase.table("questions").insert({
                                    "exam_id": ai_ex_options[sel_ai_ex],
                                    "question": gq.get("question",""), "type": "mcq",
                                    "option_a": gq.get("option_a",""), "option_b": gq.get("option_b",""),
                                    "option_c": gq.get("option_c",""), "option_d": gq.get("option_d",""),
                                    "correct_answer": gq.get("correct_answer",""), "hint": "",
                                    "explanation": gq.get("explanation","") or None
                                }).execute()
                            st.success(f" saved!")
                            st.session_state.ai_generated_qs = None
                            st.rerun()
                        except Exception as e:
                            st.error(f"Save Error: {e}")

        with ex_tab3:
            st.subheader("Review Existing Exam Papers")
            exams_all_edit = supabase.table("exams").select("*").execute().data
            if not exams_all_edit:
                st.info("No exams created yet.")
            else:
                exam_edit_options = {ex["title"]: ex["id"] for ex in exams_all_edit}
                selected_exam_title = st.selectbox("Choose Exam to Review", list(exam_edit_options.keys()))
                selected_exam_id = exam_edit_options[selected_exam_title]
                current_questions = supabase.table("questions").select("*").eq("exam_id", selected_exam_id).execute().data

                exp_reqs = supabase.table("explain_requests").select("*").eq("exam_id", selected_exam_id).execute().data
                q_requesters = {}
                for req in exp_reqs:
                    qids = json.loads(req.get("question_ids") or "[]")
                    uinfo = supabase.table("users").select("name").eq("id", req["user_id"]).execute().data
                    uname = uinfo[0]["name"] if uinfo else "Unknown"
                    for qid in qids:
                        q_requesters.setdefault(qid, [])
                        if uname not in q_requesters[qid]:
                            q_requesters[qid].append(uname)

                marked_q_ids = set(q_requesters.keys())
                marked_questions = [q for q in current_questions if q["id"] in marked_q_ids]

                st.write(f"### Questions in **{selected_exam_title}** ({len(current_questions)} total)")
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Questions", len(current_questions))
                col2.metric("Explain Requested", len(marked_questions))
                col3.metric("Students Requested", len(set(req["user_id"] for req in exp_reqs)))

                dl_col1, dl_col2 = st.columns(2)
                with dl_col1:
                    if current_questions and st.button("All Questions PPT", use_container_width=True):
                        with st.spinner("PPT generate ..."):
                            ppt_bytes = generate_exam_ppt(current_questions, selected_exam_title, q_requesters=q_requesters)
                            if ppt_bytes:
                                st.download_button(" Download", data=ppt_bytes,
                                    file_name=f"{selected_exam_title[:25]}_all.pptx",
                                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                                    key="ppt_all_btn")
                with dl_col2:
                    if marked_questions and st.button(f" Marked Questions PPT ({len(marked_questions)})", use_container_width=True, type="primary"):
                        with st.spinner("PPT generate ..."):
                            ppt_bytes = generate_exam_ppt(marked_questions, f"{selected_exam_title} - Explain", q_requesters=q_requesters)
                            if ppt_bytes:
                                st.download_button(" Download", data=ppt_bytes,
                                    file_name=f"{selected_exam_title[:25]}_marked.pptx",
                                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                                    key="ppt_marked_btn")

                st.divider()
                for idx, q in enumerate(current_questions):
                    with st.container(border=True):
                        col_q1, col_q2, col_q3 = st.columns([5, 1, 1])
                        with col_q1:
                            st.markdown(f"**Q{idx+1}. {q['question']}** `({str(q['type']).upper()})`")
                            if q.get("image_url"): st.image(q["image_url"], width=200)
                            if q["type"] == "mcq":
                                st.caption(f"A: {q['option_a']} | B: {q['option_b']} | C: {q['option_c']} | D: {q['option_d']}")
                            st.caption(f" Answer: {q['correct_answer']} |  Hint: {q.get('hint','')}")
                            if q.get("explanation") and not q.get("explanation").startswith(PROGRAMMING_META_PREFIX):
                                st.caption(f" Explanation: {q['explanation']}")
                        with col_q2:
                            if st.button("Edit", key=f"edit_btn_{q['id']}", use_container_width=True):
                                st.session_state[f"editing_{q['id']}"] = True; st.rerun()
                        with col_q3:
                            if st.button("Delete", key=f"del_q_{q['id']}", type="secondary", use_container_width=True):
                                supabase.table("questions").delete().eq("id", q["id"]).execute()
                                st.success(f"Q{idx+1} Deleted!"); st.rerun()

                        if st.session_state.get(f"editing_{q['id']}", False):
                            with st.form(key=f"edit_form_{q['id']}"):
                                st.markdown("#####  Question Edit")
                                eq_type = st.selectbox("Type", ["mcq","blank","programming"],
                                    index=["mcq","blank","programming"].index(q["type"]) if q["type"] in ["mcq","blank","programming"] else 0,
                                    key=f"eq_type_{q['id']}")
                                eq_text = st.text_area("Question", value=q["question"], key=f"eq_text_{q['id']}")
                                col1, col2 = st.columns(2)
                                with col1:
                                    eq_a = st.text_input("Option A", value=q.get("option_a",""), key=f"eq_a_{q['id']}")
                                    eq_b = st.text_input("Option B", value=q.get("option_b",""), key=f"eq_b_{q['id']}")
                                with col2:
                                    eq_c = st.text_input("Option C", value=q.get("option_c",""), key=f"eq_c_{q['id']}")
                                    eq_d = st.text_input("Option D", value=q.get("option_d",""), key=f"eq_d_{q['id']}")
                                eq_ans = st.text_input("Correct Answer", value=q.get("correct_answer",""), key=f"eq_ans_{q['id']}")
                                eq_hint = st.text_input("Hint", value=q.get("hint",""), key=f"eq_hint_{q['id']}")
                                eq_explanation = st.text_area(" Explanation", value=q.get("explanation","") or "", key=f"eq_exp_{q['id']}")
                                eq_img_url = st.text_input("Image URL", value=q.get("image_url","") or "", key=f"eq_img_{q['id']}")
                                if q.get("image_url"): st.image(q["image_url"], width=150)
                                save_col, cancel_col = st.columns(2)
                                with save_col:
                                    saved = st.form_submit_button(" Save", use_container_width=True, type="primary")
                                with cancel_col:
                                    cancelled = st.form_submit_button(" Cancel", use_container_width=True)
                                if saved:
                                    supabase.table("questions").update({
                                        "type": eq_type, "question": eq_text,
                                        "option_a": eq_a, "option_b": eq_b, "option_c": eq_c, "option_d": eq_d,
                                        "correct_answer": eq_ans, "hint": eq_hint,
                                        "explanation": eq_explanation.strip() if eq_explanation.strip() else None,
                                        "image_url": eq_img_url.strip() if eq_img_url.strip() else None
                                    }).eq("id", q["id"]).execute()
                                    st.session_state[f"editing_{q['id']}"] = False
                                    st.success("Updated!"); st.rerun()
                                if cancelled:
                                    st.session_state[f"editing_{q['id']}"] = False; st.rerun()

                st.divider()
                st.markdown("####  Quick Add Question")
                with st.form("quick_add_question_form", clear_on_submit=True):
                    q_type_new = st.selectbox("Type", ["mcq","blank","programming"], key="new_q_type")
                    q_text_new = st.text_area("Question Text", key="new_q_text")
                    col_opts1, col_opts2 = st.columns(2)
                    with col_opts1:
                        a_new = st.text_input("Option A", key="new_a"); b_new = st.text_input("Option B", key="new_b")
                    with col_opts2:
                        c_new = st.text_input("Option C", key="new_c"); d_new = st.text_input("Option D", key="new_d")
                    h_text_new = st.text_input("Hint", key="new_hint")
                    c_ans_new = st.text_input("Correct Answer", key="new_ans")
                    exp_new = st.text_area(" Explanation (optional)", key="new_explanation")
                    if st.form_submit_button(" Add Question"):
                        if q_text_new.strip():
                            supabase.table("questions").insert({
                                "exam_id": selected_exam_id, "question": q_text_new, "type": q_type_new,
                                "option_a": a_new, "option_b": b_new, "option_c": c_new, "option_d": d_new,
                                "correct_answer": c_ans_new if q_type_new != "programming" else "Manual Review Required",
                                "hint": h_text_new,
                                "explanation": exp_new.strip() if exp_new.strip() else None
                            }).execute()
                            st.success("Added!"); st.rerun()

    elif menu == "Student Results & Ranks":
        r_tab1, r_tab2, r_tab3, r_tab4, r_tab5, r_tab6, r_tab7 = st.tabs([
            " Leaderboards", " Manual Evaluation", " Score Summary",
            " Re-Exam Requests", " Explain Requests", " Attendance", " Live Programming Exams"
        ])

        with r_tab1:
            st.title("Leaderboard")
            exams = supabase.table("exams").select("*").execute().data
            if exams:
                sel_ex_lb = st.selectbox("Select Exam", [e["title"] for e in exams])
                target_ex = next((e for e in exams if e["title"] == sel_ex_lb), None)
                if target_ex:
                    board = get_exam_leaderboard(target_ex["id"])
                    if board:
                        for rank, st_row in enumerate(board):
                            st.write(f" **{st_row['Name']}** ({st_row['Email']})  Score: **{st_row['Score']}**")

        with r_tab2:
            st.title("Manual Evaluator")
            attempts_to_eval = supabase.table("exam_attempts").select("*").execute().data
            if not attempts_to_eval:
                st.info("No submissions available.")
            else:
                for att in attempts_to_eval:
                    u_data = supabase.table("users").select("*").eq("id", att["user_id"]).execute().data
                    e_data = supabase.table("exams").select("*").eq("id", att["exam_id"]).execute().data
                    if u_data and e_data:
                        with st.container(border=True):
                            col_s1, col_s2 = st.columns([3, 1])
                            with col_s1:
                                st.markdown(f"#####  **{u_data[0]['name']}** |  **{e_data[0]['title']}**")
                            with col_s2:
                                current_score = int(att.get("score") or 0)
                                exam_questions = supabase.table("questions").select("*").eq("exam_id", att["exam_id"]).execute().data or []
                                exam_max_score = get_exam_max_marks(exam_questions)
                                score_max = max(100, int(exam_max_score or 0), current_score)
                                new_score = st.number_input("Score", min_value=0, max_value=score_max, value=current_score, step=1, key=f"score_in_{att['id']}")
                                if st.button("Save", key=f"btn_score_{att['id']}", type="primary", use_container_width=True):
                                    supabase.table("exam_attempts").update({"score": new_score}).eq("id", att["id"]).execute()
                                    st.success("Score Saved!"); st.rerun()

        with r_tab3:
            st.title("Score Logger")
            attempts = supabase.table("exam_attempts").select("*").execute().data
            if attempts:
                for att in attempts:
                    u_prof = supabase.table("users").select("*").eq("id", att["user_id"]).execute().data
                    e_prof = supabase.table("exams").select("*").eq("id", att["exam_id"]).execute().data
                    if u_prof and e_prof:
                        st.markdown(f" **{u_prof[0]['name']}**  **{e_prof[0]['title']}**  Score: **{att['score']}**")
                        st.divider()

        with r_tab4:
            st.title("Re-Exam Requests")
            requests_data = supabase.table("exam_retake_requests").select("*").eq("status","pending").order("requested_at",desc=True).execute().data
            if not requests_data:
                st.info("Pending requests .")
            else:
                for req in requests_data:
                    u_info = supabase.table("users").select("name, email").eq("id", req["user_id"]).execute().data
                    e_info = supabase.table("exams").select("title").eq("id", req["exam_id"]).execute().data
                    if u_info and e_info:
                        with st.container(border=True):
                            col1, col2, col3 = st.columns([4, 1, 1])
                            with col1:
                                st.markdown(f"** {u_info[0]['name']}** ({u_info[0]['email']})")
                                st.caption(f" {e_info[0]['title']} | {req['requested_at'][:10]}")
                            with col2:
                                if st.button("Approve", key=f"apr_{req['id']}", type="primary", use_container_width=True):
                                    supabase.table("exam_retake_requests").update({"status":"approved","reviewed_at":"now()"}).eq("id",req["id"]).execute()
                                    st.success("Approved!"); st.rerun()
                            with col3:
                                if st.button("Reject", key=f"rej_{req['id']}", use_container_width=True):
                                    supabase.table("exam_retake_requests").update({"status":"rejected","reviewed_at":"now()"}).eq("id",req["id"]).execute()
                                    st.warning("Rejected!"); st.rerun()

        with r_tab5:
            st.title("Explain Requests")
            exp_requests = supabase.table("explain_requests").select("*").order("created_at",desc=True).execute().data
            if not exp_requests:
                st.info("Explain requests .")
            else:
                for req in exp_requests:
                    u_info = supabase.table("users").select("name, email").eq("id", req["user_id"]).execute().data
                    e_info = supabase.table("exams").select("title").eq("id", req["exam_id"]).execute().data
                    uname = u_info[0]["name"] if u_info else "Unknown"
                    ename = e_info[0]["title"] if e_info else "Unknown Exam"
                    qids = json.loads(req["question_ids"]) if req.get("question_ids") else []
                    status = req.get("status","pending")
                    with st.container(border=True):
                        col1, col2, col3 = st.columns([4, 1, 1])
                        with col1:
                            st.markdown(f"** {uname}** ({u_info[0]['email'] if u_info else ''})")
                            st.caption(f" {ename} | {len(qids)} questions | {status} | {str(req.get('created_at',''))[:10]}")
                        with col2:
                            if qids:
                                marked_qs = supabase.table("questions").select("*").in_("id", qids).execute().data
                                if marked_qs:
                                    all_reqs_for_exam = supabase.table("explain_requests").select("*").eq("exam_id",req["exam_id"]).execute().data
                                    qr = {}
                                    for r2 in all_reqs_for_exam:
                                        qids2 = json.loads(r2.get("question_ids") or "[]")
                                        ui2 = supabase.table("users").select("name").eq("id",r2["user_id"]).execute().data
                                        un2 = ui2[0]["name"] if ui2 else "Unknown"
                                        for qid2 in qids2:
                                            qr.setdefault(qid2, [])
                                            if un2 not in qr[qid2]: qr[qid2].append(un2)
                                    ppt_bytes = generate_exam_ppt(marked_qs, f"{ename} - Explain", q_requesters=qr)
                                    if ppt_bytes:
                                        st.download_button(" PPT", data=ppt_bytes,
                                            file_name=f"{ename[:20]}_explain.pptx",
                                            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                                            key=f"exp_ppt_{req['id']}")
                        with col3:
                            if status == "pending":
                                if st.button("Done", key=f"exp_done_{req['id']}", use_container_width=True, type="primary"):
                                    supabase.table("explain_requests").update({"status":"done"}).eq("id",req["id"]).execute()
                                    st.rerun()

        with r_tab6:
            st.title("Student Attendance")
            all_students = supabase.table("users").select("id, name, email").eq("role","user").execute().data
            if all_students:
                sel_student = st.selectbox("Student select ", [f"{s['name']} ({s['email']})" for s in all_students])
                sel_idx = [f"{s['name']} ({s['email']})" for s in all_students].index(sel_student)
                sel_uid = all_students[sel_idx]["id"]
                show_attendance_tab(sel_uid)

        with r_tab7:
            st.title("Live Programming Exams")
            try:
                sessions = supabase.table("programming_exam_sessions").select("*").eq("status", "active").order("updated_at", desc=True).execute().data or []
            except Exception as e:
                sessions = []
            if not sessions:
                st.info("Active programming exams levu.")
            for sess in sessions:
                u_data = supabase.table("users").select("name, email").eq("id", sess["user_id"]).execute().data or [{}]
                e_data = supabase.table("exams").select("title").eq("id", sess["exam_id"]).execute().data or [{}]
                uname = u_data[0].get("name") or u_data[0].get("email") or "Student"
                ename = e_data[0].get("title") or "Programming Exam"
                with st.container(border=True):
                    c1, c2, c3 = st.columns([4, 1.5, 1.5])
                    with c1:
                        st.markdown(f"**{uname}** - {ename}")
                        st.caption(f"Question: {int(sess.get('question_index') or 0) + 1} | Malpractice: {sess.get('malpractice_count') or 0} | Last: {sess.get('last_malpractice_reason') or 'None'}")
                    with c2:
                        if not sess.get("force_submit"):
                            if st.button("Submit Exam", key=f"force_submit_{sess['user_id']}_{sess['exam_id']}", type="primary", use_container_width=True):
                                supabase.table("programming_exam_sessions").update({"force_submit": True, "updated_at": "now()"}).eq("user_id", sess["user_id"]).eq("exam_id", sess["exam_id"]).execute()
                                send_notification(f"Admin requested submit for {ename}.", sess["user_id"])
                                st.success("Student exam auto submit ki mark ayyindi.")
                                st.rerun()
                    with c3:
                        if st.button("Refresh", key=f"refresh_sess_{sess['user_id']}_{sess['exam_id']}", use_container_width=True):
                            st.rerun()

    elif menu == "Group Chat":
        with st.expander(" Broadcast Notification "):
            notif_msg = st.text_input("Message", key="broadcast_msg")
            if st.button("Send to All Users", type="primary"):
                if notif_msg.strip():
                    send_notification(notif_msg.strip())
                    st.success(" !"); st.rerun()
        st.divider()
        group_chat()

# =========================
# CREDIT CARD SHARING PORTAL
# =========================
CARD_CONFIG = {
    "card_1": {"label": "Card 1", "bill_day": 13},
    "card_2": {"label": "Card 2", "bill_day": 22},
}


def get_card_label(card_code):
    return CARD_CONFIG.get(card_code, {}).get("label", card_code)


def get_card_bill_day(card_code):
    return int(CARD_CONFIG.get(card_code, {}).get("bill_day", 1))


def add_months(source_date, months):
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    max_days = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return source_date.replace(year=year, month=month, day=min(source_date.day, max_days[month - 1]))


def get_statement_period(card_code, anchor=None):
    anchor = anchor or date.today()
    bill_day = get_card_bill_day(card_code)
    this_month_bill = date(anchor.year, anchor.month, min(bill_day, 28 if anchor.month == 2 else 30 if anchor.month in [4, 6, 9, 11] else 31))
    if anchor >= this_month_bill:
        end_date = this_month_bill
    else:
        end_date = add_months(this_month_bill, -1)
    start_date = add_months(end_date, -1) + timedelta(days=1)
    return start_date, end_date


def money_value(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def get_card_users():
    try:
        return supabase.table("card_users").select("id, name, mobile, app_pin, active").order("name").execute().data or []
    except Exception as e:
        return []


def get_assigned_cards(user_id):
    try:
        rows = supabase.table("card_user_cards").select("card_code").eq("user_id", user_id).execute().data or []
        return [r.get("card_code") for r in rows]
    except Exception:
        return []


def upload_optional_image(uploaded_file):
    if not uploaded_file:
        return ""
    return upload_image_to_imgbb(uploaded_file) or ""


def generate_recurring_transactions(user_id=None):
    try:
        query = supabase.table("card_recurring_transactions").select("*").eq("active", True)
        if user_id:
            query = query.eq("user_id", user_id)
        recurring_rows = query.execute().data or []
    except Exception as e:
        return 0

    created_count = 0
    today = date.today()
    for item in recurring_rows:
        card_code = item.get("card_code")
        if not card_code:
            continue
        start_date, end_date = get_statement_period(card_code, today)
        item_start = date.fromisoformat(str(item.get("start_date") or today))
        item_end = date.fromisoformat(str(item["end_date"])) if item.get("end_date") else None
        if item_start > end_date:
            continue
        if item_end and item_end < start_date:
            continue
        billing_month = end_date.strftime("%Y-%m")
        source_key = f"recurring:{item['id']}:{billing_month}"
        txn_date = max(item_start, start_date)
        if item_end:
            txn_date = min(txn_date, item_end)
        try:
            existing = supabase.table("card_transactions").select("id").eq("source_key", source_key).execute().data
            if existing:
                continue
            supabase.table("card_transactions").insert({
                "user_id": item["user_id"],
                "card_code": card_code,
                "purpose": item.get("purpose") or "Monthly payment",
                "amount": money_value(item.get("amount")),
                "transaction_date": str(txn_date),
                "proof_url": "",
                "source_key": source_key,
                "status": "approved",
                "admin_note": "Auto monthly payment",
                "approved_by": st.session_state.user_id if st.session_state.get("role") == "admin" else None,
                "approved_at": "now()",
            }).execute()
            created_count += 1
        except Exception as e:
            pass
    return created_count


def admin_credit_cards_dashboard():
    st.title("Credit Cards Admin")
    generate_recurring_transactions()
    tab_users, tab_txns, tab_payments, tab_recurring, tab_manual = st.tabs(["Users & Cards", "Approve Transactions", "Payment Screenshots", "Monthly Auto Payments", "Add/Edit Transactions"])

    with tab_users:
        st.subheader("Add card user PIN login")
        with st.form("add_card_user_form", clear_on_submit=True):
            name = st.text_input("User name")
            mobile = st.text_input("Mobile / note")
            pin = st.text_input("Login PIN", type="password", max_chars=6)
            assigned = st.multiselect("Cards allowed", ["card_1", "card_2"], format_func=get_card_label, default=["card_1"])
            submitted = st.form_submit_button("Create PIN Login", type="primary")
        created_user = None
        if submitted:
            if not name.strip() or not pin.strip() or not assigned:
                st.error("Name, PIN, cards required.")
            elif not pin.isdigit() or len(pin) < 4:
                st.error("PIN 4 to 6 digits undali.")
            else:
                try:
                    existing_lms = supabase.table("users").select("id").eq("app_pin", pin).execute().data
                    existing_card = supabase.table("card_users").select("id").eq("app_pin", pin).execute().data
                    if existing_lms or existing_card:
                        st.error("Ee PIN already used.")
                    else:
                        created = supabase.table("card_users").insert({
                            "name": name.strip(),
                            "mobile": mobile.strip(),
                            "app_pin": pin,
                        }).execute()
                        created_data = created.data or []
                        if not created_data:
                            created_data = supabase.table("card_users").select("*").eq("app_pin", pin).execute().data or []
                        new_user_id = created_data[0]["id"] if created_data else None
                        for card_code in assigned:
                            supabase.table("card_user_cards").insert({"user_id": new_user_id, "card_code": card_code}).execute()
                        created_user = created_data[0] if created_data else {"id": new_user_id, "name": name.strip(), "mobile": mobile.strip(), "app_pin": pin, "active": True}
                        st.success(f"Card user created: {name.strip()}")
                except Exception as e:
                    st.error(f"Create user failed: {e}")

        st.divider()
        users = get_card_users()
        if created_user and not any(u.get("id") == created_user.get("id") for u in users):
            users = [created_user] + users
        for user in users:
            with st.expander(f"{user.get('name','User')} - {user.get('mobile','')}"):
                current_cards = get_assigned_cards(user["id"])
                selected_cards = st.multiselect("Assigned cards", ["card_1", "card_2"], default=current_cards, format_func=get_card_label, key=f"cards_{user['id']}")
                if st.button("Save cards", key=f"save_cards_{user['id']}"):
                    try:
                        supabase.table("card_user_cards").delete().eq("user_id", user["id"]).execute()
                        for card_code in selected_cards:
                            supabase.table("card_user_cards").insert({"user_id": user["id"], "card_code": card_code}).execute()
                        st.success("Cards updated.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Cards update failed: {e}")

    with tab_txns:
        st.subheader("Pending user transactions")
        rows = supabase.table("card_transactions").select("*").eq("status", "pending").order("transaction_date", desc=True).execute().data or []
        if not rows:
            st.info("Pending transactions levu.")
        for row in rows:
            user = supabase.table("card_users").select("name, mobile").eq("id", row["user_id"]).execute().data or [{}]
            with st.expander(f"{get_card_label(row['card_code'])} | {user[0].get('name','User')} | Rs.{money_value(row.get('amount')):.2f}"):
                st.write(row.get("purpose", ""))
                if row.get("proof_url"):
                    st.image(row["proof_url"], width=300)
                note = st.text_input("Admin note", value=row.get("admin_note") or "", key=f"txn_note_{row['id']}")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Approve", type="primary", key=f"txn_ok_{row['id']}"):
                        supabase.table("card_transactions").update({"status": "approved", "admin_note": note, "approved_by": st.session_state.user_id, "approved_at": "now()"}).eq("id", row["id"]).execute()
                        st.success("Approved.")
                        st.rerun()
                with col2:
                    if st.button("Reject", key=f"txn_no_{row['id']}"):
                        supabase.table("card_transactions").update({"status": "rejected", "admin_note": note}).eq("id", row["id"]).execute()
                        st.warning("Rejected.")
                        st.rerun()

    with tab_payments:
        st.subheader("User bill payment screenshots")
        all_card_users = get_card_users()
        pending_bill_rows = []
        for card_user in all_card_users:
            user_cards = get_assigned_cards(card_user["id"])
            for card_code in user_cards:
                start_date, end_date = get_statement_period(card_code)
                billing_month = end_date.strftime("%Y-%m")
                approved = supabase.table("card_transactions").select("*").eq("user_id", card_user["id"]).eq("card_code", card_code).eq("status", "approved").gte("transaction_date", str(start_date)).lte("transaction_date", str(end_date)).execute().data or []
                total = sum(money_value(r.get("amount")) for r in approved)
                if total <= 0:
                    continue
                payments_for_bill = supabase.table("card_payments").select("*").eq("user_id", card_user["id"]).eq("card_code", card_code).eq("billing_month", billing_month).order("created_at", desc=True).execute().data or []
                paid = any(p.get("status") == "paid" for p in payments_for_bill)
                if paid:
                    continue
                pending_pay = any(p.get("status") == "pending" for p in payments_for_bill)
                pending_bill_rows.append({
                    "user": card_user.get("name", "User"),
                    "card": get_card_label(card_code),
                    "month": billing_month,
                    "amount": round(total, 2),
                    "status": "Pending approval" if pending_pay else "Not paid",
                })
        if pending_bill_rows:
            st.dataframe(pending_bill_rows, use_container_width=True, hide_index=True)
        st.divider()
        payments = supabase.table("card_payments").select("*").order("created_at", desc=True).execute().data or []
        for pay in payments:
            user = supabase.table("card_users").select("name, mobile").eq("id", pay["user_id"]).execute().data or [{}]
            with st.expander(f"{pay.get('status','pending').upper()} | {get_card_label(pay['card_code'])} | {user[0].get('name','User')} | Rs.{money_value(pay.get('amount')):.2f}"):
                if pay.get("proof_url"):
                    st.image(pay["proof_url"], width=320)
                note = st.text_input("Payment admin note", value=pay.get("admin_note") or "", key=f"pay_note_{pay['id']}")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Mark Paid", type="primary", key=f"pay_ok_{pay['id']}"):
                        supabase.table("card_payments").update({"status": "paid", "admin_note": note, "approved_by": st.session_state.user_id, "approved_at": "now()"}).eq("id", pay["id"]).execute()
                        st.success("Payment marked paid.")
                        st.rerun()
                with col2:
                    if st.button("Reject Payment", key=f"pay_no_{pay['id']}"):
                        supabase.table("card_payments").update({"status": "rejected", "admin_note": note}).eq("id", pay["id"]).execute()
                        st.warning("Payment rejected.")
                        st.rerun()

    with tab_recurring:
        st.subheader("One-time setup for monthly payments")
        users = get_card_users()
        if users:
            labels = {f"{u.get('name','User')} ({u.get('mobile','')})": u for u in users}
            selected_label = st.selectbox("User", list(labels.keys()), key="rec_user")
            selected_user = labels[selected_label]
            user_cards = get_assigned_cards(selected_user["id"]) or ["card_1", "card_2"]
            with st.form("recurring_payment_form", clear_on_submit=True):
                rec_card = st.selectbox("Card", user_cards, format_func=get_card_label, key="rec_card")
                rec_purpose = st.text_input("Purpose")
                rec_amount = st.number_input("Monthly amount", min_value=0.0, step=1.0, key="rec_amount")
                rec_start = st.date_input("Start from", value=date.today(), key="rec_start")
                has_end = st.checkbox("End date?")
                rec_end = st.date_input("End date", value=add_months(date.today(), 12), key="rec_end") if has_end else None
                rec_submit = st.form_submit_button("Add Monthly Auto Payment", type="primary")
            if rec_submit:
                if not rec_purpose.strip() or rec_amount <= 0:
                    st.error("Purpose and amount required.")
                else:
                    try:
                        supabase.table("card_recurring_transactions").insert({
                            "user_id": selected_user["id"],
                            "card_code": rec_card,
                            "purpose": rec_purpose.strip(),
                            "amount": rec_amount,
                            "start_date": str(rec_start),
                            "end_date": str(rec_end) if rec_end else None,
                            "active": True,
                        }).execute()
                        made = generate_recurring_transactions(selected_user["id"])
                        st.success(f"Monthly auto payment added.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Monthly auto payment add failed: {e}")

        st.divider()
        st.subheader("Manage monthly auto payments")
        recurring_rows = supabase.table("card_recurring_transactions").select("*").order("created_at", desc=True).execute().data or []
        for rec in recurring_rows:
            user = supabase.table("card_users").select("name, mobile").eq("id", rec["user_id"]).execute().data or [{}]
            status = "Active" if rec.get("active") else "Paused"
            with st.expander(f"{status} | {user[0].get('name','User')} | Rs.{money_value(rec.get('amount')):.2f}"):
                c1, c2, c3 = st.columns([2, 1, 1])
                new_purpose = c1.text_input("Purpose", value=rec.get("purpose") or "", key=f"rec_purpose_{rec['id']}")
                new_amount = c2.number_input("Amount", min_value=0.0, value=money_value(rec.get("amount")), step=1.0, key=f"rec_amount_{rec['id']}")
                new_active = c3.checkbox("Active", value=bool(rec.get("active")), key=f"rec_active_{rec['id']}")
                if st.button("Save auto payment", key=f"save_rec_{rec['id']}", type="primary"):
                    supabase.table("card_recurring_transactions").update({
                        "purpose": new_purpose.strip(),
                        "amount": new_amount,
                        "active": new_active,
                    }).eq("id", rec["id"]).execute()
                    st.success("Monthly auto payment updated.")
                    st.rerun()

    with tab_manual:
        st.subheader("Add transaction for a user")
        users = get_card_users()
        if users:
            labels = {f"{u.get('name','User')} ({u.get('mobile','')})": u for u in users}
            selected_label = st.selectbox("User", list(labels.keys()), key="manual_card_user")
            selected_user = labels[selected_label]
            user_cards = get_assigned_cards(selected_user["id"]) or ["card_1", "card_2"]
            with st.form("manual_card_txn_form", clear_on_submit=True):
                card_code = st.selectbox("Card", user_cards, format_func=get_card_label)
                purpose = st.text_input("Purpose")
                amount = st.number_input("Amount", min_value=0.0, step=1.0)
                txn_date = st.date_input("Date", value=date.today())
                proof_file = st.file_uploader("Screenshot optional", type=["png", "jpg", "jpeg", "webp", "pdf"])
                submit_txn = st.form_submit_button("Add Approved Transaction", type="primary")
            if submit_txn:
                if not purpose.strip() or amount <= 0:
                    st.error("Purpose and amount required.")
                else:
                    proof_url = upload_optional_image(proof_file)
                    supabase.table("card_transactions").insert({
                        "user_id": selected_user["id"],
                        "card_code": card_code,
                        "purpose": purpose.strip(),
                        "amount": amount,
                        "transaction_date": str(txn_date),
                        "proof_url": proof_url,
                        "status": "approved",
                        "approved_by": st.session_state.user_id,
                        "approved_at": "now()",
                    }).execute()
                    st.success("Transaction added.")
                    st.rerun()

        st.divider()
        st.subheader("Edit existing transactions")
        txns = supabase.table("card_transactions").select("*").order("transaction_date", desc=True).limit(100).execute().data or []
        for row in txns:
            user = supabase.table("card_users").select("name, mobile").eq("id", row["user_id"]).execute().data or [{}]
            with st.expander(f"{get_card_label(row['card_code'])} | {user[0].get('name','User')} | {row.get('purpose','')}"):
                col1, col2, col3 = st.columns([2, 1, 1])
                new_purpose = col1.text_input("Purpose", value=row.get("purpose") or "", key=f"edit_purpose_{row['id']}")
                new_amount = col2.number_input("Amount", min_value=0.0, value=money_value(row.get("amount")), step=1.0, key=f"edit_amount_{row['id']}")
                new_status = col3.selectbox("Status", ["pending", "approved", "rejected"], index=["pending", "approved", "rejected"].index(row.get("status", "pending")), key=f"edit_status_{row['id']}")
                if st.button("Save transaction", key=f"save_txn_{row['id']}"):
                    supabase.table("card_transactions").update({
                        "purpose": new_purpose.strip(),
                        "amount": new_amount,
                        "status": new_status,
                    }).eq("id", row["id"]).execute()
                    st.success("Transaction updated.")
                    st.rerun()


def card_user_dashboard():
    st.sidebar.title("Credit Card Portal")
    persist_browser_login()
    if st.sidebar.button("Logout", use_container_width=True):
        for key in defaults:
            st.session_state[key] = defaults[key]
        show_logout_redirect()
    st.sidebar.divider()
    pages = ["Monthly Bill", "Pending Bills", "Paid", "Add Transaction", "History"]
    for pg in pages:
        if st.sidebar.button(pg, use_container_width=True, type="primary" if st.session_state.card_user_page == pg else "secondary", key=f"card_nav_{pg}"):
            st.session_state.card_user_page = pg
            st.rerun()

    user_id = st.session_state.user_id
    assigned_cards = get_assigned_cards(user_id)
    if not assigned_cards:
        st.warning("No cards assigned yet.")
        return
    generate_recurring_transactions(user_id)

    st.title("Credit Card Portal")
    if st.session_state.card_user_page == "Add Transaction":
        with st.form("user_add_card_txn", clear_on_submit=True):
            card_code = st.selectbox("Card", assigned_cards, format_func=get_card_label)
            purpose = st.text_input("Purpose")
            amount = st.number_input("Amount", min_value=0.0, step=1.0)
            txn_date = st.date_input("Transaction date", value=date.today())
            proof_file = st.file_uploader("Payment/transaction screenshot", type=["png", "jpg", "jpeg", "webp"])
            submitted = st.form_submit_button("Submit for admin approval", type="primary")
        if submitted:
            if not purpose.strip() or amount <= 0:
                st.error("Purpose and amount required.")
            else:
                proof_url = upload_optional_image(proof_file)
                supabase.table("card_transactions").insert({
                    "user_id": user_id,
                    "card_code": card_code,
                    "purpose": purpose.strip(),
                    "amount": amount,
                    "transaction_date": str(txn_date),
                    "proof_url": proof_url,
                    "status": "pending",
                }).execute()
                st.success("Transaction sent to admin.")
                st.rerun()
        return

    if st.session_state.card_user_page == "Pending Bills":
        st.subheader("Pending Bills")
        found_pending_bill = False
        for card_code in assigned_cards:
            start_date, end_date = get_statement_period(card_code)
            billing_month = end_date.strftime("%Y-%m")
            approved = supabase.table("card_transactions").select("*").eq("user_id", user_id).eq("card_code", card_code).eq("status", "approved").gte("transaction_date", str(start_date)).lte("transaction_date", str(end_date)).order("transaction_date", desc=False).execute().data or []
            total = sum(money_value(r.get("amount")) for r in approved)
            payments = supabase.table("card_payments").select("*").eq("user_id", user_id).eq("card_code", card_code).eq("billing_month", billing_month).order("created_at", desc=True).execute().data or []
            paid = any(p.get("status") == "paid" for p in payments)
            pending_pay = any(p.get("status") == "pending" for p in payments)
            if total <= 0 or paid:
                continue
            found_pending_bill = True
            status_text = "Pending approval" if pending_pay else "PAY"
            with st.container(border=True):
                st.subheader(f"{get_card_label(card_code)} - {billing_month}")
                st.metric("Bill amount", f"Rs.{total:.2f}")
                if not pending_pay:
                    with st.form(f"pending_pay_form_{card_code}_{billing_month}"):
                        pay_file = st.file_uploader("Upload screenshot", type=["png", "jpg", "jpeg", "webp"], key=f"pending_pay_file_{card_code}_{billing_month}")
                        submit_pay = st.form_submit_button("Pay Now", type="primary")
                    if submit_pay:
                        proof_url = upload_optional_image(pay_file)
                        if proof_url:
                            supabase.table("card_payments").upsert({
                                "user_id": user_id,
                                "card_code": card_code,
                                "billing_month": billing_month,
                                "bill_start": str(start_date),
                                "bill_end": str(end_date),
                                "amount": total,
                                "proof_url": proof_url,
                                "status": "pending",
                            }, on_conflict="user_id,card_code,billing_month").execute()
                            st.success("Payment screenshot uploaded.")
                            st.rerun()
        if not found_pending_bill:
            st.info("Pending bills levu.")
        return

    if st.session_state.card_user_page == "Paid":
        st.subheader("Paid Bills")
        paid_rows = supabase.table("card_payments").select("*").eq("user_id", user_id).eq("status", "paid").order("bill_end", desc=True).execute().data or []
        if not paid_rows:
            st.info("Paid bills levu.")
        else:
            st.dataframe([{
                "card": get_card_label(r.get("card_code")),
                "month": r.get("billing_month"),
                "amount": money_value(r.get("amount")),
            } for r in paid_rows], use_container_width=True, hide_index=True)
        return

    if st.session_state.card_user_page == "History":
        rows = supabase.table("card_transactions").select("*").eq("user_id", user_id).order("transaction_date", desc=True).execute().data or []
        if not rows:
            st.info("Transactions levu.")
        else:
            st.dataframe([{
                "date": r.get("transaction_date"),
                "card": get_card_label(r.get("card_code")),
                "purpose": r.get("purpose"),
                "amount": money_value(r.get("amount")),
                "status": r.get("status"),
            } for r in rows], use_container_width=True, hide_index=True)
        return

    for card_code in assigned_cards:
        start_date, end_date = get_statement_period(card_code)
        billing_month = end_date.strftime("%Y-%m")
        approved = supabase.table("card_transactions").select("*").eq("user_id", user_id).eq("card_code", card_code).eq("status", "approved").gte("transaction_date", str(start_date)).lte("transaction_date", str(end_date)).order("transaction_date", desc=False).execute().data or []
        total = sum(money_value(r.get("amount")) for r in approved)
        payments = supabase.table("card_payments").select("*").eq("user_id", user_id).eq("card_code", card_code).eq("billing_month", billing_month).order("created_at", desc=True).execute().data or []
        paid = any(p.get("status") == "paid" for p in payments)
        pending_pay = any(p.get("status") == "pending" for p in payments)
        status_text = "PAID" if paid else "Waiting Approval" if pending_pay else "PAY"
        with st.container(border=True):
            st.subheader(f"{get_card_label(card_code)} - Bill date {get_card_bill_day(card_code)}")
            st.metric("Approved amount", f"Rs.{total:.2f}")
            if not paid and total > 0 and not pending_pay:
                with st.form(f"pay_form_{card_code}_{billing_month}"):
                    pay_file = st.file_uploader("Upload screenshot", type=["png", "jpg", "jpeg", "webp"], key=f"pay_file_{card_code}_{billing_month}")
                    submit_pay = st.form_submit_button("Submit Screenshot", type="primary")
                if submit_pay:
                    proof_url = upload_optional_image(pay_file)
                    if proof_url:
                        supabase.table("card_payments").upsert({
                            "user_id": user_id,
                            "card_code": card_code,
                            "billing_month": billing_month,
                            "bill_start": str(start_date),
                            "bill_end": str(end_date),
                            "amount": total,
                            "proof_url": proof_url,
                            "status": "pending",
                        }, on_conflict="user_id,card_code,billing_month").execute()
                        st.success("Uploaded successfully.")
                        st.rerun()

# =========================
# USER DASHBOARD
# =========================
def user_dashboard(preview_mode=False):
    if not preview_mode:
        st.sidebar.title("User Workspace")
        persist_browser_login()
        if st.sidebar.button("Logout", use_container_width=True):
            for key in defaults:
                st.session_state[key] = defaults[key]
            show_logout_redirect()
        st.sidebar.divider()
        pages = ["My Classes", "Programming", "Progress", "Code Practice", "Group Chat", "Attendance"]
        if user_has_suprabhatam_access(st.session_state.user_id):
            pages.append("Suprabhatam")
        for pg in pages:
            if pg == "Group Chat":
                unread = get_unread_count(st.session_state.user_id)
                label = f"Group Chat ({unread})" if unread > 0 else "Group Chat"
            else:
                label = pg
            if st.sidebar.button(label, use_container_width=True,
                    type="primary" if st.session_state.user_page == pg else "secondary",
                    key=f"nav_{pg}"):
                st.session_state.user_page = pg
                st.rerun()
        user_page = st.session_state.user_page
        mark_today_attendance(st.session_state.user_id)
    else:
        st.info("Student Preview Mode")
        user_page = "My Classes"

    if not preview_mode:
        show_notification_banner(st.session_state.user_id)

    if user_page == "Group Chat":
        group_chat(); return
    if user_page == "Progress":
        show_student_progress_tab(st.session_state.user_id); return
    if user_page in ["Java Practice", "Code Practice"]:
        show_code_practice_tab(); return
    if user_page == "Programming":
        show_programming_questions_tab(st.session_state.user_id); return
    if user_page == "Attendance":
        show_attendance_tab(st.session_state.user_id); return
    if user_page == "Suprabhatam":
        if user_has_suprabhatam_access(st.session_state.user_id):
            render_suprabhatam_reader(); return
        return

    modules = supabase.table("modules").select("*").execute().data
    if st.session_state.completed_ids is None:
        all_completions = supabase.table("class_completions").select("class_id").eq("user_id", st.session_state.user_id).execute().data
        st.session_state.completed_ids = {str(c["class_id"]) for c in all_completions}
    completed_ids = st.session_state.completed_ids
    focus_class_id = str(st.session_state.get("focus_class_id", ""))
    focus_exam_id = str(st.session_state.get("focus_exam_id", ""))

    for module in modules:
        module_submodules = supabase.table("submodules").select("id").eq("module_id", module["id"]).execute().data
        sub_ids = [s["id"] for s in module_submodules]
        module_has_focus = False
        module_total = 0; module_done = 0
        for sid in sub_ids:
            cls_list = supabase.table("classes").select("id").eq("submodule_id", sid).execute().data
            module_total += len(cls_list)
            module_done += sum(1 for c in cls_list if str(c["id"]) in completed_ids)
            if focus_class_id and any(str(c["id"]) == focus_class_id for c in cls_list):
                module_has_focus = True
        pct = int((module_done / module_total * 100)) if module_total > 0 else 0

        with st.expander(f"{module['title']}    {module_done}/{module_total} classes  ({pct}%)", expanded=module_has_focus):
            if module_total > 0:
                st.progress(pct / 100)
            submodules = supabase.table("submodules").select("*").eq("module_id", module["id"]).execute().data
            for sub in submodules:
                sub_classes = supabase.table("classes").select("id").eq("submodule_id", sub["id"]).execute().data
                sub_total = len(sub_classes)
                sub_done = sum(1 for c in sub_classes if str(c["id"]) in completed_ids)
                sub_pct = int((sub_done / sub_total * 100)) if sub_total > 0 else 0
                st.subheader(f"{sub['title']}   {sub_done}/{sub_total}")
                classes = supabase.table("classes").select("*").eq("submodule_id", sub["id"]).execute().data
                for cls in classes:
                    is_done = str(cls.get("id")) in completed_ids
                    st.markdown(f"### {cls['title']}")
                    col_link1, col_link2, col_link3 = st.columns(3)
                    with col_link1:
                        if cls.get("class_link"): st.link_button("Join Class", cls["class_link"], use_container_width=True)
                    with col_link2:
                        if cls.get("recorded_video"): st.link_button("Watch Video", cls["recorded_video"], use_container_width=True)
                    with col_link3:
                        if cls.get("notes_pdf"): st.link_button("Notes PDF", cls["notes_pdf"], use_container_width=True)

                    class_id = cls.get("id")
                    if class_id:
                        try: cid = int(class_id)
                        except (ValueError, TypeError): cid = str(class_id)
                        if str(class_id) not in completed_ids:
                            if st.button("Mark as Completed", key=f"btn_done_{cls['id']}"):
                                try:
                                    supabase.table("class_completions").insert({"user_id": str(st.session_state.user_id), "class_id": cid}).execute()
                                    st.session_state.completed_ids.add(str(class_id))
                                    st.success("Success!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Insert Error: {e}")

                    exams = supabase.table("exams").select("*").eq("class_id", cls["id"]).execute().data
                    for exam in exams:
                        if not exam["enabled"]: continue
                        exam_dur = exam.get("duration_mins", 30)
                        st.write(f" **Exam: {exam['title']}** ({exam_dur} Mins)")
                        btn_col, lb_col = st.columns([2, 2])
                        with lb_col:
                            board = get_exam_leaderboard(exam["id"])
                            if board:
                                st.markdown(" **Top Performers:**")
                                for idx, student in enumerate(board[:3]):
                                    st.caption(f"{student['Name']}  {student['Score']}")
                        with btn_col:
                            check_attempt = supabase.table("exam_attempts").select("*").eq("user_id", st.session_state.user_id).eq("exam_id", exam["id"]).execute().data
                            if check_attempt:
                                q_count = supabase.table("questions").select("*").eq("exam_id", exam["id"]).execute().data
                                total_q = get_exam_max_marks(q_count)
                                for idx, att in enumerate(check_attempt):
                                    pct_a = int((int(att.get("score") or 0) / total_q) * 100) if total_q else 0
                                    st.caption(f"Attempt {idx+1}: **{att['score']}/{total_q}** ({pct_a}%)")
                                if st.button("Show Answers", key=f"view_{exam['id']}", use_container_width=True):
                                    st.session_state.exam_id = exam["id"]
                                    st.session_state.exam_title = exam["title"]
                                    st.session_state.start_exam = True
                                    st.session_state.exam_submitted = True
                                    st.session_state.current_questions = supabase.table("questions").select("*").eq("exam_id", exam["id"]).execute().data
                                    st.rerun()
                            else:
                                has_pwd = exam.get("password") and str(exam["password"]).strip()
                                entered_pwd = st.text_input(f"Access Code", type="password", key=f"pwd_{exam['id']}") if has_pwd else ""
                                if st.button("Start Exam", key=f"btn_{exam['id']}", use_container_width=True):
                                    if has_pwd and entered_pwd.strip() != str(exam["password"]).strip():
                                        st.error("Wrong Password!")
                                    else:
                                        q_data = supabase.table("questions").select("*").eq("exam_id", exam["id"]).execute().data
                                        start_exam_with_questions(exam, q_data)
                                        st.rerun()
                    st.divider()

# =========================================================================
# ADVANCED LEETCODE-STYLE EXAM WORKSPACE VIEW WITH ANTI-CHEAT FULLSCREEN
# =========================================================================
def exam_workspace_view():
    questions = st.session_state.current_questions
    total_questions = len(questions)
    is_prog_exam = is_programming_exam(st.session_state.exam_id) if st.session_state.get("exam_id") else False
    
    if is_prog_exam and not st.session_state.exam_submitted:
        qp = st.query_params
        if qp.get("malpractice") == "1":
            reason = qp.get("mal_reason", "Tab switched or exam window lost focus")
            report_programming_malpractice(reason)
            try:
                del st.query_params["malpractice"]
                del st.query_params["mal_reason"]
            except Exception:
                pass
        session = get_active_programming_session(st.session_state.user_id, st.session_state.exam_id)
        if session and session.get("force_submit"):
            st.error("Admin force submit requested. Exam automatic ga submit avuthundi...")
            try:
                submit_exam_attempt(questions, include_time=True, require_programming_submitted=False)
                st.session_state.exam_submitted = True
                st.rerun()
            except Exception as e:
                st.error(f"Auto submit failed: {e}")
                return
        save_programming_exam_session(status="active")

    if total_questions == 0:
        st.warning("No questions in this exam.")
        if st.button("Go Back"): 
            st.session_state.start_exam = False
            st.rerun()
        return

    remaining_time = 0
    if not st.session_state.exam_submitted:
        remaining_time = int(st.session_state.exam_end_time - time.time())
        if remaining_time <= 0:
            st.error("Time out. Submitting exam...")
            time.sleep(1)
            try:
                submit_exam_attempt(questions, include_time=False)
                st.session_state.exam_submitted = True
                st.rerun()
            except Exception as e:
                st.error(f"Submit failed: {e}")
                return

    # RESULTS DISPLAY SHEET VIEW
    if st.session_state.exam_submitted:
        st.title(f" Results: {st.session_state.exam_title}")
        db_attempt = supabase.table("exam_attempts").select("*").eq("user_id", st.session_state.user_id).eq("exam_id", st.session_state.exam_id).execute().data
        if db_attempt and st.session_state.get("last_attempt_id"):
            last_id = st.session_state.last_attempt_id
            db_attempt = sorted(db_attempt, key=lambda att: 0 if att.get("id") == last_id else 1)
        if db_attempt:
            max_marks = get_exam_max_marks(questions)
            st.markdown("### Attempts History")
            for idx, att in enumerate(reversed(db_attempt)):
                pct = int((int(att.get("score") or 0) / max_marks) * 100) if max_marks else 0
                st.info(f"Attempt {idx+1}: **{att['score']}/{max_marks}** ({pct}%)")
            st.divider()
            latest = db_attempt[0]
            latest_pct = int((int(latest.get("score") or 0) / max_marks) * 100) if max_marks else 0
            st.success(f" Latest Score: {latest['score']}/{max_marks} ({latest_pct}%)")
            db_answers = supabase.table("user_answers").select("*").eq("attempt_id", latest["id"]).execute().data
            ans_map = {a["question_id"]: a["answer"] for a in db_answers}
            exam_data = supabase.table("exams").select("*").eq("id", st.session_state.exam_id).execute().data
            if exam_data and exam_data[0]["show_answers"]:
                st.subheader("Review Sheet")
                render_review_sheet(questions, ans_map, db_attempt)

        if st.button("Return to Dashboard", type="primary"):
            save_programming_exam_session(status="submitted", force_submit=False)
            st.session_state.start_exam = False
            st.session_state.exam_submitted = False
            st.session_state.answers = {}
            st.session_state.question_index = 0
            st.session_state.current_questions = []
            st.rerun()

    # ACTIVE INTERACTIVE FRAME MATRIX VIEW
    else:
        # FORCED INTERCEPT JS ENGINES (FOR ALL MULTI-TYPE EXAMS AS REQUESTED)
        components.html(f"""
            <div style="display:none;">Anti-Cheat Loaded</div>
            <script>
                var doc = window.parent.document;
                var body = doc.body;

                function triggerFullscreen() {{
                    if (!doc.fullscreenElement) {{
                        body.requestFullscreen().catch(err => {{
                            console.log("Fullscreen activation failed: " + err.message);
                        }});
                    }}
                }}

                doc.addEventListener('click', triggerFullscreen);
                triggerFullscreen();

                function flagMalpractice(reason){{
                    try {{
                        var url = new URL(window.parent.location.href);
                        if (url.searchParams.get('malpractice') !== '1') {{
                            url.searchParams.set('malpractice', '1');
                            url.searchParams.set('mal_reason', reason);
                            window.parent.location.href = url.toString();
                        }}
                    }} catch(e) {{}}
                }}

                doc.addEventListener('visibilitychange', function(){{
                    if (doc.hidden) flagMalpractice('Tab Switched / Screen Lost Focus');
                }});

                window.parent.addEventListener('blur', function() {{
                    flagMalpractice('Window Focus Lost (Alt+Tab or Application Switch)');
                }});
            </script>
        """, height=0)

        # CONTROL CONTAINER COMPONENT PANELS
        t_left, t_mid, t_right = st.columns([4, 2, 2])
        with t_left:
            st.markdown(f"<h2 style='margin:0; padding:0;'>💻 {st.session_state.exam_title}</h2>", unsafe_allow_html=True)
        with t_mid:
            mins, secs = divmod(remaining_time, 60)
            components.html(f"""
                <div id="timer" style="font-size:1.3rem; font-weight:600; text-align:center; padding:6px; border-radius:6px;
                    background:{'#fff3cd' if remaining_time<300 else '#e8f4fd'};
                    color:{'#856404' if remaining_time<300 else '#0c63e4'};
                    border:1px solid {'#ffc107' if remaining_time<300 else '#b6d4fe'}; font-family:sans-serif;">
                     ⏱️ Time Remaining: <span id="countdown">{mins:02d}:{secs:02d}</span>
                </div>
                <script>
                    var total={remaining_time};
                    function tick(){{
                        if(total<=0){{document.getElementById('countdown').innerText="00:00";return;}}
                        total--;var m=Math.floor(total/60).toString().padStart(2,'0');
                        var s=(total%60).toString().padStart(2,'0');
                        document.getElementById('countdown').innerText=m+':'+s;
                    }}
                    setInterval(tick,1000);
                </script>""", height=45)
        with t_right:
            def save_current_q_time_action():
                qid_cur = questions[st.session_state.question_index]["id"]
                if qid_cur in st.session_state.question_start_time:
                    elapsed = int(time.time() - st.session_state.question_start_time[qid_cur])
                    prev = st.session_state.question_time_log.get(qid_cur, 0)
                    st.session_state.question_time_log[qid_cur] = prev + elapsed
                    del st.session_state.question_start_time[qid_cur]

            if st.button("🚀 SUBMIT FINAL TEST", type="primary", use_container_width=True, key="corner_submit_exam_btn"):
                save_current_q_time_action()
                try:
                    save_programming_exam_session(status="active")
                    submit_exam_attempt(questions, include_time=True, require_programming_submitted=is_prog_exam)
                    st.session_state.question_time_log = {}
                    st.session_state.question_start_time = {}
                    st.session_state.program_run_results = {}
                    st.session_state.program_submissions = {}
                    st.session_state.exam_submitted = True
                    st.rerun()
                except Exception as e:
                    st.error(f"Submit failed: {e}")

        st.divider()

        current = st.session_state.question_index
        question = questions[current]
        qid = question["id"]
        
        if qid not in st.session_state.question_start_time:
            st.session_state.question_start_time[qid] = time.time()
        stored_ans = st.session_state.answers.get(question["id"], "")

        # LEETCODE FRAMES LOGIC DESIGN LAYOUT SETUP
        frame_left, frame_right = st.columns([3, 4])

        # ------------------------------------
        # FRAME 1 (LEFT PANEL): QUESTION PORT
        # ------------------------------------
        with frame_left:
            st.markdown("""
                <div style="background-color:#1e1e1e; padding:8px; border-radius:6px; color:#ffffff; font-weight:bold; text-align:center; margin-bottom:10px;">
                    📝 FRAME 1: QUESTION PORTAL
                </div>
            """, unsafe_allow_html=True)
            
            st.markdown("##### Navigation Dashboard Matrix")
            nav_cols = st.columns(min(total_questions, 8))
            for idx in range(total_questions):
                with nav_cols[idx % 8]:
                    if st.button(f"{idx+1}", key=f"f1_nav_{idx}", use_container_width=True, type="primary" if idx == current else "secondary"):
                        save_current_q_time_action()
                        st.session_state.question_index = idx
                        st.rerun()
            st.divider()

            st.subheader(f"Question Item {current+1} / {total_questions}")
            st.markdown(f"### {question['question']}")
            if question.get("image_url"):
                st.image(question["image_url"], use_container_width=True)
            
            if question["type"] == "mcq":
                opts = [("A", question.get("option_a","")), ("B", question.get("option_b","")), ("C", question.get("option_c","")), ("D", question.get("option_d",""))]
                for lbl, otxt in opts:
                    if otxt:
                        is_selected = (stored_ans == lbl or stored_ans == otxt)
                        if st.button(f"{lbl}. {otxt}", key=f"f1_mcq_{qid}_{lbl}", use_container_width=True, type="primary" if is_selected else "secondary"):
                            st.session_state.answers[qid] = lbl
                            save_programming_exam_session(status="active")
                            st.rerun()

            elif question["type"] == "blank":
                ans = st.text_input("Type localized response text parameters here:", value=stored_ans, key=f"f1_blank_{qid}")
                if ans != stored_ans:
                    st.session_state.answers[qid] = ans
                    save_programming_exam_session(status="active")
                    
            else:
                meta = get_programming_meta(question)
                if meta.get("description"):
                    st.markdown("#### Problem Description Constraints")
                    st.info(meta["description"])
                
                st.markdown("#### Structural Testing Platform Assets")
                for idx, tc in enumerate(meta.get("test_cases", []), start=1):
                    if not tc.get("hidden", False):
                        st.markdown(f"**Sample Setup Case {idx}:**")
                        st.code(f"Input Data Stream:\n{tc.get('input','')}\n\nExpected Output Return:\n{tc.get('expected_output','')}", language="text")

        # ------------------------------------
        # FRAME 2 (RIGHT PANEL): CODE & TEST CASES CONSOLE
        # ------------------------------------
        with frame_right:
            if question["type"] != "programming":
                st.info("Isolated secondary workspace framework panels targeting objective index selections remain passive. Configure context metrics entirely using left viewport configurations.")
            else:
                meta = get_programming_meta(question)
                stored_code, stored_language = parse_program_answer(stored_ans, meta.get("language", "java"))
                
                language_options = list(PROGRAMMING_LANGUAGE_LABELS.keys())
                current_language_label = get_programming_language_meta(stored_language)["label"]
                
                selected_language_label = st.selectbox(
                    "Target Platform Compilation Language Profile",
                    language_options,
                    index=language_options.index(current_language_label) if current_language_label in language_options else 0,
                    key=f"f2_lang_{qid}"
                )
                selected_language = PROGRAMMING_LANGUAGE_LABELS[selected_language_label]
                lang_meta = get_programming_language_meta(selected_language)

                # FRAME 2 - PART A: CODE FRAME
                st.markdown("""
                    <div style="background-color:#0e1117; padding:8px; border-radius:6px; color:#4a90d9; font-weight:bold; font-size:0.9rem; margin-bottom:5px;">
                        💻 FRAME 2 - PART 1: CODE EDITOR CANVAS
                    </div>
                """, unsafe_allow_html=True)
                
                enable_textarea_tab_support()
                editor_value = stored_code if stored_code else lang_meta["default_code"]
                answer_code = st.text_area(
                    f"Platform Console {lang_meta['label']} Compiler Environment Interface:", 
                    value=editor_value, 
                    key=f"f2_editor_{qid}", 
                    height=320
                )
                
                st.session_state.answers[qid] = {"code": answer_code, "language": selected_language}
                save_programming_exam_session(status="active")
                
                # FRAME 2 - PART B: TEST CASES CONSOLE LOG
                st.markdown("""
                    <div style="background-color:#0e1117; padding:8px; border-radius:6px; color:#2ea043; font-weight:bold; font-size:0.9rem; margin-top:15px; margin-bottom:5px;">
                        📊 FRAME 2 - PART 2: CONSOLE LOG & TEST VERIFICATIONS
                    </div>
                """, unsafe_allow_html=True)
                
                custom_input = st.text_area(
                    "Isolated Standard Input Custom Param Stream Buffer:", 
                    key=f"f2_stdin_{qid}", 
                    height=70, 
                    placeholder="Provide string attributes lines targets directly into target routine threads..."
                )

                col_btn_run, col_btn_sub, col_btn_cust = st.columns(3)
                with col_btn_run:
                    if st.button("▶️ Run Test Cases", key=f"f2_action_run_{qid}", use_container_width=True):
                        with st.spinner("Piping attributes through check routines..."):
                            st.session_state.program_run_results[str(qid)] = run_programming_test_cases(question, answer_code, selected_language)
                
                with col_btn_sub:
                    if st.button("📥 Submit Program", key=f"f2_action_sub_{qid}", type="primary", use_container_width=True):
                        with st.spinner("Saving structural architecture rules assets..."):
                            score_data = run_programming_test_cases(question, answer_code, selected_language)
                            st.session_state.program_run_results[str(qid)] = score_data
                            st.session_state.program_submissions[str(qid)] = {"code": answer_code, "language": selected_language, "score_data": score_data}
                            save_programming_exam_session(status="active")
                            st.success(f"Program registered metrics: {score_data['earned']}/{score_data['total']} passed.")

                with col_btn_cust:
                    if st.button("⚙️ Custom Run Check", key=f"f2_action_cust_{qid}", use_container_width=True):
                        with st.spinner("Injecting static variables across runtime pipelines..."):
                            custom_result = run_programming_code(answer_code, custom_input, selected_language)
                            custom_result["language"] = selected_language
                            st.session_state.program_custom_results[str(qid)] = custom_result

                saved_prog = st.session_state.program_submissions.get(str(qid), {})
                if saved_prog.get("code") == answer_code and saved_prog.get("score_data"):
                    st.success("✅ Program integrity synchronized. Compilation snapshots aligned cleanly.")
                elif saved_prog:
                    st.warning("⚠️ Code structural asset parameters modified post explicit target snapshot save operations. Re-trigger validation loops.")

                custom_data = st.session_state.program_custom_results.get(str(qid))
                if custom_data and custom_data.get("language") == selected_language:
                    st.markdown("##### 🚀 Runtime Custom System Output Profile:")
                    st.code(custom_data.get("stdout","").strip(), language="text")
                    if custom_data.get("stderr"):
                        st.error(custom_data.get("stderr"))

                run_data = st.session_state.program_run_results.get(str(qid))
                if run_data and run_data.get("language") == selected_language:
                    st.markdown(f"##### 🎯 Matrix Suite Validation: **{run_data['earned']}/{run_data['total']}** Marks Cleared")
                    for res in run_data["results"]:
                        is_hidden = bool(res.get("hidden", False))
                        badge_status = "🟩 PASSED" if res["passed"] else "🟥 FAILED"
                        title_label = f"Secure Hidden Case {res['case']}" if is_hidden else f"Public Sample Case {res['case']}"
                        
                        with st.container(border=True):
                            st.markdown(f"**{title_label}** — {badge_status} ({res['marks']} Marks)")
                            if is_hidden and not res["passed"]:
                                st.caption("Isolated execution context target parameters mismatch detected.")
                            elif not res["passed"]:
                                st.text(f"Expected:\n{res.get('expected_output')}\nReceived Output:\n{res.get('actual_output')}")

            st.divider()
            f_prev, f_next, f_pause = st.columns([1, 1, 2])
            with f_prev:
                if st.button("⬅️ Previous Question", disabled=(current == 0), use_container_width=True, key="workspace_footer_prev"):
                    save_current_q_time_action()
                    st.session_state.question_index -= 1
                    save_programming_exam_session(status="active")
                    st.rerun()
            with f_next:
                if st.button("Next Question ➡️", disabled=(current == total_questions - 1), use_container_width=True, key="workspace_footer_next"):
                    save_current_q_time_action()
                    st.session_state.question_index += 1
                    save_programming_exam_session(status="active")
                    st.rerun()
            with f_pause:
                if is_prog_exam and st.button("⏸️ Save Session & Pause Workspace", use_container_width=True, key="workspace_footer_pause"):
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
