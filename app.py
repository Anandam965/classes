import os
import uuid
import time
import json
import requests
from datetime import date, timedelta

import streamlit as st
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
            st.error("IMGBB_API_KEY secrets లో లేదు!")
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
    st.error("Secrets లో విలువలు కనపడటం లేదు. Settings -> Secrets ని చెక్ చేయండి.")
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
    "user_page": "📚 My Classes",
    "question_start_time": {},
    "question_time_log": {},
    "attendance_marked_date": "",
    "ai_generated_qs": None,
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# =========================
# PERSISTENT LOGIN
# =========================
if not st.session_state.logged_in:
    try:
        qp = st.query_params
        saved_uid = qp.get("uid", "")
        saved_role = qp.get("role", "")
        if saved_uid and saved_role:
            urow_data = supabase.table("users").select("*").eq("id", saved_uid).execute().data
            if urow_data and urow_data[0]["role"] == saved_role:
                st.session_state.logged_in = True
                st.session_state.role = saved_role
                st.session_state.user_id = saved_uid
                st.session_state.pin_verified = True
    except Exception:
        pass

# =========================
# JAVA CODE EVALUATOR
# =========================
def evaluate_java_code(user_code, input_data, expected_output):
    url = "https://judge0-ce.p.rapidapi.com/submissions?base64_encoded=false&fields=*"
    payload = {"source_code": user_code, "language_id": 27, "stdin": input_data}
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

# =========================
# OCR: IMAGE → QUESTION EXTRACT
# =========================
def extract_question_from_image(image_source):
    """Image nundi OCR.space API use chesi question + options extract cheyyali"""
    import re

    def parse_ocr_text(raw_text):
        text = raw_text.replace("\r", "\n")
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        clean = "\n".join(lines)
        opt_pat = re.compile(
            r"(?im)^\s*(?:option\s*)?([A-D]|[1-4])[\)\].:\-]\s*(.+?)(?=\n\s*(?:option\s*)?(?:[A-D]|[1-4])[\)\].:\-]\s*|\Z)",
            re.S
        )
        matches = list(opt_pat.finditer(clean))
        options = {"A": "", "B": "", "C": "", "D": ""}
        first_opt_start = len(clean)
        for m in matches:
            lbl = m.group(1).upper()
            if lbl in ["1","2","3","4"]:
                lbl = chr(ord("A") + int(lbl) - 1)
            if lbl in options and not options[lbl]:
                options[lbl] = " ".join(m.group(2).split())
                first_opt_start = min(first_opt_start, m.start())
        question = clean[:first_opt_start].strip()
        answer = ""
        ans_m = re.search(r"(?im)(?:answer|correct\s*answer|ans)\s*[:\-]\s*([A-D]|[1-4]|.+)$", clean)
        if ans_m:
            answer = ans_m.group(1).strip()
            if answer.upper() in options and options[answer.upper()]:
                answer = options[answer.upper()]
            elif answer in ["1","2","3","4"]:
                answer = options.get(chr(ord("A") + int(answer) - 1), answer)
        if not question:
            question = clean
        return {
            "question": question,
            "type": "mcq" if any(options.values()) else "blank",
            "option_a": options["A"], "option_b": options["B"],
            "option_c": options["C"], "option_d": options["D"],
            "correct_answer": answer, "hint": "",
        }

    try:
        api_key = st.secrets.get("OCR_SPACE_API_KEY", "")
        if not api_key:
            st.error("OCR_SPACE_API_KEY Streamlit secrets లో add చేయండి.")
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
            st.error("Image లో text clear గా కనిపించలేదు.")
            return None
        st.caption("📄 OCR extracted text:")
        st.code(raw_text)
        return parse_ocr_text(raw_text)
    except Exception as e:
        st.error(f"Image నుండి question extract కాలేదు: {e}")
        return None


def login():
    st.title("📚 LMS Login")
    login_method = st.radio("Login method:", ["📧 Email & Password", "🔑 PIN తో Login"], horizontal=True, key="login_method_radio")

    if login_method == "📧 Email & Password":
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
                    st.error("User record కనపడటం లేదు.")
            except Exception as e:
                st.error(str(e))
    else:
        st.caption("మీ unique PIN enter చేయండి.")
        pin = st.text_input("🔑 PIN", type="password", max_chars=6, key="pin_only_input")
        if st.button("🔓 Enter App", type="primary", use_container_width=True, key="pin_only_btn"):
            if not pin:
                st.error("PIN enter చేయండి.")
            else:
                try:
                    user_data = supabase.table("users").select("*").eq("app_pin", pin).execute()
                    if not user_data.data:
                        st.error("❌ Wrong PIN! మళ్ళీ try చేయండి.")
                    else:
                        urow = user_data.data[0]
                        st.session_state.logged_in = True
                        st.session_state.role = urow["role"]
                        st.session_state.user_id = urow["id"]
                        st.session_state.pin_verified = True
                        st.query_params["uid"] = str(urow["id"])
                        st.query_params["role"] = urow["role"]
                        st.rerun()
                except Exception as e:
                    st.error(str(e))


def pin_screen():
    st.title("🔒 App Lock")
    if st.session_state.pin_setup_mode:
        st.subheader("మీ PIN set చేయండి (4-6 digits)")
        st.caption("ఈ PIN globally unique గా ఉంటుంది.")
        pin1 = st.text_input("కొత్త PIN (4-6 digits)", type="password", max_chars=6, key="pin_new")
        pin2 = st.text_input("PIN మళ్ళీ enter చేయండి", type="password", max_chars=6, key="pin_confirm")
        if st.button("✅ PIN Set చేయి", type="primary", use_container_width=True):
            if not pin1.isdigit() or len(pin1) < 4:
                st.error("4-6 digits మాత్రమే enter చేయండి!")
            elif pin1 != pin2:
                st.error("రెండు PINలు match కాలేదు!")
            else:
                existing = supabase.table("users").select("id").eq("app_pin", pin1).execute().data
                if existing and existing[0]["id"] != st.session_state.user_id_temp:
                    st.error("❌ ఈ PIN వేరె user వాడుతున్నారు.")
                else:
                    supabase.table("users").update({"app_pin": pin1}).eq("id", st.session_state.user_id_temp).execute()
                    st.session_state.logged_in = True
                    st.session_state.role = st.session_state.role_temp
                    st.session_state.user_id = st.session_state.user_id_temp
                    st.session_state.pin_verified = True
                    st.query_params["uid"] = str(st.session_state.user_id_temp)
                    st.query_params["role"] = st.session_state.role_temp
                    st.success("PIN set అయింది! Welcome 🎉")
                    st.rerun()
    else:
        st.subheader("మీ PIN enter చేయండి")
        pin_input = st.text_input("4-digit PIN", type="password", max_chars=4, key="pin_entry")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔓 Enter App", type="primary", use_container_width=True):
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
                    st.error("❌ Wrong PIN!")
        with col2:
            if st.button("🔙 వేరే Account తో Login", use_container_width=True):
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
    notif_html = "".join(f"<div class='notif-wrap'>🔔 {n['message']}</div>" for n in notifs)
    st.markdown(notif_html, unsafe_allow_html=True)
    if st.button(f"✅ Mark all as Read ({len(notifs)})", key="mark_notif_read", type="secondary"):
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
    st.title("💬 Group Chat")
    user_id = str(st.session_state.user_id)
    messages = supabase.table("messages").select("*").order("created_at", desc=False).limit(50).execute().data
    chat_container = st.container(height=450)
    with chat_container:
        if not messages:
            st.info("ఇంకా messages లేవు. మొదటిగా message చేయండి! 👋")
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
        new_msg = st.text_input("Message రాయండి...", key="chat_input", label_visibility="collapsed")
    with col_send:
        send = st.button("📤 Send", use_container_width=True, type="primary")
    with col_read:
        mark_read = st.button("✅ Read", use_container_width=True)
    if send and new_msg.strip():
        uinfo = supabase.table("users").select("name").eq("id", user_id).execute().data
        uname = uinfo[0]["name"] if uinfo else "Unknown"
        supabase.table("messages").insert({"user_id": user_id, "user_name": uname, "message": new_msg.strip()}).execute()
        supabase.table("message_reads").upsert({"user_id": user_id, "last_read_at": "now()"}, on_conflict="user_id").execute()
        st.rerun()
    if mark_read:
        supabase.table("message_reads").upsert({"user_id": user_id, "last_read_at": "now()"}, on_conflict="user_id").execute()
        st.success("✅ అన్ని messages చదివినట్లు mark అయింది!")
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
    st.title("📅 My Attendance")
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
        st.warning("Attendance table database లో లేదు. Admin SQL run చేయండి.")
        with st.expander("📋 SQL to create attendance table"):
            st.code("""
CREATE TABLE IF NOT EXISTS attendance (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  attendance_date date NOT NULL,
  created_at timestamptz DEFAULT now(),
  UNIQUE(user_id, attendance_date)
);""", language="sql")
        return

    total = len(attended)
    streak = 0
    cursor = today
    while cursor.isoformat() in attended:
        streak += 1
        cursor -= timedelta(days=1)

    # Longest streak
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
    c1.metric("📊 Total Days", total)
    c2.metric("🔥 Current Streak", f"{streak} days")
    c3.metric("🏆 Longest Streak", f"{longest} days")
    c4.metric("📅 Today", "✅ Present" if today.isoformat() in attended else "⏳ Pending")

    st.divider()

    # Build heatmap — weeks as columns, days as rows (Sun=0 .. Sat=6)
    # Align start to Sunday
    offset = start_day.isoweekday() % 7  # Sun=0
    grid_start = start_day - timedelta(days=offset)
    all_days = [grid_start + timedelta(days=i) for i in range((today - grid_start).days + 1)]
    weeks = [all_days[i:i+7] for i in range(0, len(all_days), 7)]

    # Month labels row
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
            title = f"{d.strftime('%d %b %Y')} — {'Present' if d.isoformat() in attended else 'Absent'}"
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
          <div class="att-sub">Login చేసిన రోజులు 🟩 green గా కనిపిస్తాయి (last 1 year)</div>
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
            # Header row: Q number + badge + 📌 button
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
                    if st.button("✅ Marked", key=f"exp_{qid}", use_container_width=True, type="primary"):
                        st.session_state.explain_selected.discard(qid)
                        st.rerun()
                else:
                    if st.button("📌 Explain", key=f"exp_{qid}", use_container_width=True):
                        st.session_state.explain_selected.add(qid)
                        st.rerun()

            # Time spent
            ua_data = supabase.table("user_answers").select("time_spent_seconds") \
                .eq("attempt_id", db_attempt[0]["id"]).eq("question_id", q["id"]).execute().data
            t_spent = ua_data[0]["time_spent_seconds"] if ua_data and ua_data[0].get("time_spent_seconds") else 0
            if t_spent and t_spent > 0:
                mins_s, secs_s = divmod(t_spent, 60)
                tstr = f"{mins_s}m {secs_s}s" if mins_s > 0 else f"{secs_s}s"
                st.caption(f"⏱️ Time spent: **{tstr}**")

            # MCQ styled options
            if q["type"] == "mcq":
                opts = [("A", q.get("option_a","")), ("B", q.get("option_b","")),
                        ("C", q.get("option_c","")), ("D", q.get("option_d",""))]
                correct_display = c_ans
                opts_html = ""
                for lbl, otxt in opts:
                    # Is this the correct option?
                    is_opt_correct = (
                        c_ans.upper() == lbl
                        or c_ans.lower() == str(otxt).strip().lower()
                    )
                    # Is this what the user picked?
                    is_user_pick = (
                        str(u_ans).strip().upper() == lbl
                        or str(u_ans).strip().lower() == str(otxt).strip().lower()
                    )
                    if is_opt_correct:
                        correct_display = f"{lbl}. {otxt}"
                        bg, br, col, suffix, fw = "#eafaf0","#27ae60","#1b5e34","  ✓","700"
                    elif is_user_pick and not is_correct:
                        bg, br, col, suffix, fw = "#fdecea","#e74c3c","#c0392b","  (Your Answer) ✗","700"
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
                st.code(u_ans, language="java")

            else:
                ans_bg = "#eafaf0" if is_correct else "#fdecea"
                ans_br = "#27ae60" if is_correct else "#e74c3c"
                ans_col = "#1b5e34" if is_correct else "#c0392b"
                ans_sfx = " ✓" if is_correct else " (Your Answer) ✗"
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

            # Answer Explanation box
            explanation = str(q.get("explanation", "") or "").strip()
            if explanation:
                st.markdown(
                    f"<div style='background:#f5f6fa;border:1px solid #d0d8e8;border-radius:10px;"
                    f"padding:14px 16px;margin-top:6px;'>"
                    f"<div style='font-weight:700;margin-bottom:5px;'>Answer Explanation</div>"
                    f"<div style='color:#444;line-height:1.6;'>{explanation}</div></div>",
                    unsafe_allow_html=True
                )

            # Report Question link style
            st.markdown(
                "<div style='margin-top:8px;'>"
                "<span style='color:#e74c3c;font-size:0.82rem;cursor:pointer;'>⚠️ Report Question</span>"
                "</div>",
                unsafe_allow_html=True
            )

    # Explain request send
    st.divider()
    selected_count = len(st.session_state.explain_selected)
    if selected_count > 0:
        st.info(f"📌 {selected_count} questions marked for explanation")
        if st.button(f"📨 Admin కి Explain Request పంపు ({selected_count} questions)", type="primary", use_container_width=True):
            try:
                supabase.table("explain_requests").insert({
                    "user_id": str(st.session_state.user_id),
                    "exam_id": str(st.session_state.exam_id),
                    "question_ids": json.dumps(list(st.session_state.explain_selected)),
                    "status": "pending"
                }).execute()
                uinfo = supabase.table("users").select("name").eq("id", st.session_state.user_id).execute().data
                uname = uinfo[0]["name"] if uinfo else "Student"
                send_notification(f"📌 {uname} {selected_count} questions కి explanation request చేశారు!")
                st.session_state.explain_selected = set()
                st.success("✅ Request పంపబడింది!")
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
    txt(ts, "Correct → Green  |  Wrong → White", 0.5, 4.6, 9, 0.4, sz=12, italic=True, color="8899CC", align=PP_ALIGN.CENTER)

    for idx, q in enumerate(questions):
        sl = prs.slides.add_slide(BL); box(sl, 0, 0, 10, 5.625, LGT)
        cur_y = 0.18
        box(sl, 0.3, cur_y, 0.7, 0.42, ACC)
        txt(sl, f"Q{idx+1}", 0.3, cur_y, 0.7, 0.42, sz=14, bold=True, color=WHT, align=PP_ALIGN.CENTER)
        txt(sl, q.get("question",""), 1.12, cur_y, 8.55, 0.72, sz=15, bold=True, color=DRK)
        cur_y += 0.78
        if q_requesters and q.get("id") in q_requesters:
            names = q_requesters[q["id"]][:4]
            ns = "📌 " + ",  ".join(names)
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
            txt(sl, f"✓  Correct: {correct_ans}", 0.3, 5.15, 9, 0.35, sz=11, bold=True, color=GRN)
        else:
            box(sl, 0.3, cur_y, 9.4, 1.1, "EAF7EE", GRN, Pt(2))
            txt(sl, correct_ans, 0.5, cur_y+0.1, 9.0, 0.9, sz=14, bold=True, color=GRN)
        hint = str(q.get("hint","") or "").strip()
        if hint:
            txt(sl, f"💡 {hint}", 0.3, 5.38, 9, 0.25, sz=10, italic=True, color=MUT)
        txt(sl, f"{idx+1}/{len(questions)}", 8.6, 5.38, 1.1, 0.25, sz=9, color=MUT, align=PP_ALIGN.RIGHT)

    es = prs.slides.add_slide(BL); box(es, 0, 0, 10, 5.625, NAV)
    txt(es, "End of Review", 0.5, 1.8, 9, 1.5, sz=38, bold=True, color=WHT, align=PP_ALIGN.CENTER)
    txt(es, "Keep improving!", 0.5, 3.4, 9, 0.6, sz=18, italic=True, color="CADCFC", align=PP_ALIGN.CENTER)

    buf = io.BytesIO(); prs.save(buf); buf.seek(0)
    return buf.read()

def check_mcq_correct(user_val, q):
    """MCQ answer check — user_val can be label (A/B/C/D) or full text"""
    correct = str(q.get("correct_answer","")).strip()
    user = str(user_val).strip()
    if not user or not correct:
        return False
    # Direct match
    if user.lower() == correct.lower():
        return True
    # User answered as label, correct stored as text
    label_map = {
        "A": str(q.get("option_a","")), "B": str(q.get("option_b","")),
        "C": str(q.get("option_c","")), "D": str(q.get("option_d","")),
    }
    if user.upper() in label_map:
        return label_map[user.upper()].strip().lower() == correct.lower()
    # User answered as text, correct stored as label
    if correct.upper() in label_map:
        return label_map[correct.upper()].strip().lower() == user.lower()
    return False


def admin_dashboard():
    st.sidebar.title("🛡️ Admin Workspace")
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        for key in defaults:
            st.session_state[key] = defaults[key]
        st.query_params.clear()
        st.rerun()

    st.sidebar.divider()
    if st.session_state.admin_preview_mode:
        if st.sidebar.button("🛡️ Admin View కి తిరిగి వెళ్ళు", use_container_width=True, type="primary"):
            st.session_state.admin_preview_mode = False
            st.rerun()
        user_dashboard(preview_mode=True)
        return
    else:
        show_notification_banner(st.session_state.user_id)
        if st.sidebar.button("👁️ Student View Preview", use_container_width=True):
            st.session_state.admin_preview_mode = True
            st.rerun()
    st.sidebar.divider()

    unread_admin = get_unread_count(st.session_state.user_id)
    chat_menu_label = f"💬 Group Chat 🔴 {unread_admin}" if unread_admin > 0 else "💬 Group Chat"
    menu = st.sidebar.selectbox("Navigation Control",
        ["🗂️ Manage Course Content", "📝 Manage Exams & Questions", "📊 Student Results & Ranks", chat_menu_label])
    if "Group Chat" in menu:
        menu = "💬 Group Chat"

    if menu == "🗂️ Manage Course Content":
        tab1, tab2, tab3 = st.tabs(["📁 Modules Setup", "📂 Submodules Setup", "🖥️ Live/Recorded Classes"])

        with tab1:
            st.subheader("Manage Core Modules")
            with st.form("add_module_form", clear_on_submit=True):
                module_name = st.text_input("New Module Title")
                if st.form_submit_button("✨ Save Module"):
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
                    if st.button("💾 Update", key=f"mod_u_{m['id']}", use_container_width=True):
                        supabase.table("modules").update({"title": new_m_title}).eq("id", m["id"]).execute()
                        st.success("Updated!"); st.rerun()
                with col3:
                    if st.button("🗑️ Delete", key=f"mod_d_{m['id']}", type="secondary", use_container_width=True):
                        supabase.table("modules").delete().eq("id", m["id"]).execute()
                        st.warning("Deleted!"); st.rerun()

        with tab2:
            st.subheader("Manage Submodules")
            modules_list = supabase.table("modules").select("*").execute().data
            mod_options = {m["title"]: m["id"] for m in modules_list} if modules_list else {}
            with st.form("add_sub_form", clear_on_submit=True):
                sel_mod = st.selectbox("Select Parent Module", list(mod_options.keys()) or ["No modules yet"])
                sub_name = st.text_input("Submodule Title")
                if st.form_submit_button("✨ Save Submodule"):
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
                    if st.button("💾 Update", key=f"sub_u_{s['id']}", use_container_width=True):
                        supabase.table("submodules").update({"title": new_s_title}).eq("id", s["id"]).execute()
                        st.success("Updated!"); st.rerun()
                with col4:
                    if st.button("🗑️ Delete", key=f"sub_d_{s['id']}", type="secondary", use_container_width=True):
                        supabase.table("submodules").delete().eq("id", s["id"]).execute()
                        st.warning("Deleted!"); st.rerun()

        with tab3:
            st.subheader("Manage Stream/Video Classes")
            sub_list = supabase.table("submodules").select("*").execute().data
            sub_options = {s["title"]: s["id"] for s in sub_list} if sub_list else {}
            with st.expander("➕ Add New Class Room"):
                with st.form("add_class_form", clear_on_submit=True):
                    sel_sub = st.selectbox("Link to Submodule", list(sub_options.keys()) or ["No submodules yet"])
                    c_title = st.text_input("Class Title")
                    c_link = st.text_input("Live Stream Link")
                    v_link = st.text_input("Recorded Video URL")
                    p_link = st.text_input("Notes PDF URL")
                    if st.form_submit_button("🚀 Deploy Class"):
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
                with st.expander(f"🖥️ {cls['title']}  —  {comp_count}/{total_users} students  ({pct}%)"):
                    col_prog, col_num = st.columns([5, 1])
                    with col_prog: st.progress(pct / 100)
                    with col_num: st.markdown(f"**{pct}%**")
                    if comp_count > 0:
                        with st.expander(f"👥 {comp_count} మంది complete చేశారు"):
                            for row in comp_data:
                                u = supabase.table("users").select("name, email").eq("id", row["user_id"]).execute().data
                                if u: st.caption(f"✅ {u[0]['name']} ({u[0]['email']})")
                    st.divider()
                    ec_title = st.text_input("Title", value=cls["title"], key=f"ct_{cls['id']}")
                    ec_link = st.text_input("Live Link", value=cls.get("class_link",""), key=f"cl_{cls['id']}")
                    ev_link = st.text_input("Video Link", value=cls.get("recorded_video",""), key=f"cv_{cls['id']}")
                    ep_link = st.text_input("PDF Link", value=cls.get("notes_pdf",""), key=f"cp_{cls['id']}")
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("💾 Save Changes", key=f"cu_{cls['id']}", type="primary", use_container_width=True):
                            supabase.table("classes").update({"title": ec_title, "class_link": ec_link, "recorded_video": ev_link, "notes_pdf": ep_link}).eq("id", cls["id"]).execute()
                            st.success("Saved!"); st.rerun()
                    with b2:
                        if st.button("🗑️ Remove Class", key=f"cd_{cls['id']}", use_container_width=True):
                            supabase.table("classes").delete().eq("id", cls["id"]).execute()
                            st.warning("Deleted!"); st.rerun()

    elif menu == "📝 Manage Exams & Questions":
        ex_tab1, ex_tab2, ex_tab3, ex_tab4, ex_tab5 = st.tabs([
            "📝 Exams Setup", "❓ Add Questions", "🔍 Review Papers", "📁 Bulk Upload (CSV)", "🤖 AI Gen"
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
                if st.form_submit_button("📋 Generate Exam Layout"):
                    if sel_cls in cls_options:
                        supabase.table("exams").insert({
                            "class_id": cls_options[sel_cls], "title": e_title,
                            "duration_mins": int(e_duration),
                            "password": e_pwd.strip() if e_pwd.strip() else None,
                            "enabled": c_en, "show_answers": c_ans
                        }).execute()
                        st.success("Exam Created!"); st.rerun()
            st.divider()
            st.write("### ⚙️ Live Exam Controls")
            exams_all = supabase.table("exams").select("*").execute().data
            for ex in exams_all:
                with st.container(border=True):
                    st.markdown(f"#### 📄 **{ex['title']}**")
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
                        if st.button("💾 Save", key=f"up_ex_{ex['id']}", type="primary", use_container_width=True):
                            old_pwd = str(ex.get("password") or "")
                            new_pwd = updated_pwd.strip()
                            supabase.table("exams").update({
                                "duration_mins": int(updated_dur),
                                "password": new_pwd if new_pwd else None,
                                "enabled": t_active, "show_answers": t_ans
                            }).eq("id", ex["id"]).execute()
                            if new_pwd and new_pwd != old_pwd:
                                send_notification(f"📝 '{ex['title']}' exam కి password set అయింది: {new_pwd}")
                            st.success("Updated!"); st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete Exam", key=f"del_ex_{ex['id']}", type="secondary", use_container_width=True):
                            supabase.table("exams").delete().eq("id", ex["id"]).execute()
                            st.warning("Deleted!"); st.rerun()

        with ex_tab2:
            st.subheader("Add Questions")
            exams_q = supabase.table("exams").select("*").execute().data
            ex_options = {e["title"]: e["id"] for e in exams_q} if exams_q else {}
            st.markdown("#### ➕ Add Question")
            sel_ex = st.selectbox("Select Exam", list(ex_options.keys()) or ["No exams yet"], key="add_q_exam")

            # ── Image upload / URL → auto OCR extract ──────────────────────
            st.caption("📷 Image upload చేస్తే automatically question + options extract అవుతాయి")
            img_col1, img_col2 = st.columns(2)
            with img_col1:
                img_url_input = st.text_input("Image URL", key="add_img_url", placeholder="https://...")
            with img_col2:
                img_file = st.file_uploader("Image upload", type=["jpg","jpeg","png","gif","webp"], key="add_img_file")

            # Auto-extract trigger
            extract_source = img_file if img_file else (img_url_input.strip() if img_url_input.strip() else None)
            if extract_source:
                if st.button("🔍 Image నుండి Question Extract చేయి", use_container_width=True, key="extract_ocr_btn"):
                    with st.spinner("OCR processing..."):
                        extracted = extract_question_from_image(extract_source)
                    if extracted:
                        st.session_state["ocr_q_text"]   = extracted.get("question", "")
                        st.session_state["ocr_q_type"]   = extracted.get("type", "mcq")
                        st.session_state["ocr_a"]        = extracted.get("option_a", "")
                        st.session_state["ocr_b"]        = extracted.get("option_b", "")
                        st.session_state["ocr_c"]        = extracted.get("option_c", "")
                        st.session_state["ocr_d"]        = extracted.get("option_d", "")
                        st.session_state["ocr_ans"]      = extracted.get("correct_answer", "")
                        st.session_state["ocr_hint"]     = extracted.get("hint", "")
                        st.success("✅ Question extract అయింది! Check చేసి Save చేయండి.")

            st.divider()

            # Use OCR values as defaults if available
            default_q_text = st.session_state.get("ocr_q_text", "")
            default_q_type = st.session_state.get("ocr_q_type", "mcq")
            default_a      = st.session_state.get("ocr_a", "")
            default_b      = st.session_state.get("ocr_b", "")
            default_c      = st.session_state.get("ocr_c", "")
            default_d      = st.session_state.get("ocr_d", "")
            default_ans    = st.session_state.get("ocr_ans", "")
            default_hint   = st.session_state.get("ocr_hint", "")

            type_options = ["mcq", "blank", "programming"]
            type_idx = type_options.index(default_q_type) if default_q_type in type_options else 0
            q_type = st.selectbox("Question Type", type_options, index=type_idx, key="add_q_type")
            q_text = st.text_area("Question Text", value=default_q_text, key="add_q_text")

            # ── 4 Options with ✓ Set Correct button ──────────────────────
            st.markdown("**Options** — సరైన option పక్కన **✓ Set Correct** నొక్కండి")

            opt_defaults = {"A": default_a, "B": default_b, "C": default_c, "D": default_d}
            opt_vals = {}
            for lbl in ["A","B","C","D"]:
                oc1, oc2, oc3 = st.columns([1, 6, 2])
                with oc1:
                    st.markdown(f"<div style='padding-top:8px;font-weight:700;'>{lbl}.</div>", unsafe_allow_html=True)
                with oc2:
                    val = st.text_input(f"Option {lbl}", value=opt_defaults[lbl],
                                        key=f"add_opt_{lbl}", label_visibility="collapsed")
                    opt_vals[lbl] = val
                with oc3:
                    cur_correct = st.session_state.get("add_correct_lbl", default_ans)
                    already = (cur_correct.upper() == lbl)
                    btn_type  = "primary"   if already else "secondary"
                    btn_label = "✅ Correct" if already else "✓ Set Correct"
                    if st.button(btn_label, key=f"setcor_{lbl}", use_container_width=True, type=btn_type):
                        st.session_state["add_correct_lbl"] = lbl
                        st.rerun()

            # Final correct answer label
            correct_lbl = st.session_state.get("add_correct_lbl", default_ans)
            if correct_lbl:
                opt_text = opt_vals.get(correct_lbl.upper(), "")
                disp = f"{correct_lbl}. {opt_text}" if opt_text else correct_lbl
                st.info(f"🎯 Correct Answer: **{disp}**")

            h_text   = st.text_input("💡 Hint", value=default_hint, key="add_hint")
            exp_text = st.text_area("📖 Answer Explanation (optional)", key="add_explanation",
                                     placeholder="ఈ సమాధానం ఎందుకు correct అో వివరించండి...")

            if st.button("➕ Add Question", type="primary", key="add_q_btn", use_container_width=True):
                if sel_ex in ex_options and q_text.strip():
                    final_img_url = None
                    if img_file:
                        final_img_url = upload_image_to_imgbb(img_file)
                    elif img_url_input.strip():
                        final_img_url = img_url_input.strip()
                    # Save correct answer as label if available, else fallback
                    save_ans = correct_lbl if correct_lbl else ""
                    supabase.table("questions").insert({
                        "exam_id": ex_options[sel_ex], "question": q_text, "type": q_type,
                        "option_a": opt_vals.get("A",""),
                        "option_b": opt_vals.get("B",""),
                        "option_c": opt_vals.get("C",""),
                        "option_d": opt_vals.get("D",""),
                        "correct_answer": save_ans,
                        "hint": h_text, "image_url": final_img_url,
                        "explanation": exp_text.strip() if exp_text.strip() else None
                    }).execute()
                    # Clear OCR + correct label state
                    for k in ["ocr_q_text","ocr_q_type","ocr_a","ocr_b","ocr_c","ocr_d",
                              "ocr_ans","ocr_hint","add_correct_lbl"]:
                        st.session_state.pop(k, None)
                    st.success("✅ Question Added!")
                    st.rerun()
                else:
                    st.error("Exam select చేయండి మరియు question text enter చేయండి.")

        with ex_tab4:
            st.subheader("📁 Bulk Upload Questions (CSV)")
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
                            st.error(f"CSV లో ఈ columns లేవు: {missing}")
                            st.caption("Expected: question, type, option_a..d, correct_answer, hint, explanation")
                        else:
                            df = df.fillna("")
                            st.success(f"✅ {len(df)} rows loaded!")
                            st.write("Preview:", df.head())
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
                                    st.success(f"✅ {len(df)} questions uploaded!")
                                except Exception as e:
                                    st.error(f"Upload Error: {e}")
                    except Exception as e:
                        st.error(f"CSV చదవలేకపోయాం: {e}")
            else:
                st.warning("ముందుగా ఒక Exam create చేయండి.")

        with ex_tab5:
            st.subheader("🤖 AI Question Generator (Gemini)")
            exams_ai = supabase.table("exams").select("*").execute().data
            ai_ex_options = {e["title"]: e["id"] for e in exams_ai} if exams_ai else {}
            sel_ai_ex = st.selectbox("Save to Exam", list(ai_ex_options.keys()) or ["No exams yet"], key="ai_gen_exam")
            lesson_text = st.text_area("Paste Lesson Content here:")
            if st.button("✨ Generate Questions"):
                if not lesson_text.strip():
                    st.warning("దయచేసి lesson text పైన paste చేయండి!")
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
                        st.success(f"✅ {len(parsed_qs)} questions generated!")
                    except Exception as e:
                        st.error(f"AI Error: {e}")

            if st.session_state.get("ai_generated_qs"):
                st.subheader("Generated Questions Preview")
                for gi, gq in enumerate(st.session_state.ai_generated_qs):
                    with st.container(border=True):
                        st.markdown(f"**Q{gi+1}. {gq.get('question','')}**")
                        st.caption(f"A: {gq.get('option_a','')} | B: {gq.get('option_b','')} | C: {gq.get('option_c','')} | D: {gq.get('option_d','')}")
                        st.caption(f"🎯 Correct: {gq.get('correct_answer','')}")
                        if gq.get("explanation"):
                            st.caption(f"📖 {gq.get('explanation','')}")
                if sel_ai_ex in ai_ex_options:
                    if st.button("📥 DB లో Save చేయి", type="primary", use_container_width=True):
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
                            st.success(f"✅ {len(st.session_state.ai_generated_qs)} questions saved!")
                            st.session_state.ai_generated_qs = None
                            st.rerun()
                        except Exception as e:
                            st.error(f"Save Error: {e}")

        with ex_tab3:
            st.subheader("🔍 Review Existing Exam Papers")
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
                    if current_questions and st.button("📊 All Questions PPT", use_container_width=True):
                        with st.spinner("PPT generate అవుతుంది..."):
                            ppt_bytes = generate_exam_ppt(current_questions, selected_exam_title, q_requesters=q_requesters)
                            if ppt_bytes:
                                st.download_button("⬇️ Download", data=ppt_bytes,
                                    file_name=f"{selected_exam_title[:25]}_all.pptx",
                                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                                    key="ppt_all_btn")
                with dl_col2:
                    if marked_questions and st.button(f"📌 Marked Questions PPT ({len(marked_questions)})", use_container_width=True, type="primary"):
                        with st.spinner("PPT generate అవుతుంది..."):
                            ppt_bytes = generate_exam_ppt(marked_questions, f"{selected_exam_title} - Explain", q_requesters=q_requesters)
                            if ppt_bytes:
                                st.download_button("⬇️ Download", data=ppt_bytes,
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
                            st.caption(f"🎯 Answer: {q['correct_answer']} | 💡 Hint: {q.get('hint','')}")
                            if q.get("explanation"):
                                st.caption(f"📖 Explanation: {q['explanation']}")
                        with col_q2:
                            if st.button("✏️ Edit", key=f"edit_btn_{q['id']}", use_container_width=True):
                                st.session_state[f"editing_{q['id']}"] = True; st.rerun()
                        with col_q3:
                            if st.button("🗑️ Delete", key=f"del_q_{q['id']}", type="secondary", use_container_width=True):
                                supabase.table("questions").delete().eq("id", q["id"]).execute()
                                st.success(f"Q{idx+1} Deleted!"); st.rerun()

                        if st.session_state.get(f"editing_{q['id']}", False):
                            with st.form(key=f"edit_form_{q['id']}"):
                                st.markdown("##### ✏️ Question Edit")
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
                                eq_explanation = st.text_area("📖 Explanation", value=q.get("explanation","") or "", key=f"eq_exp_{q['id']}")
                                eq_img_url = st.text_input("Image URL", value=q.get("image_url","") or "", key=f"eq_img_{q['id']}")
                                if q.get("image_url"): st.image(q["image_url"], width=150)
                                save_col, cancel_col = st.columns(2)
                                with save_col:
                                    saved = st.form_submit_button("💾 Save", use_container_width=True, type="primary")
                                with cancel_col:
                                    cancelled = st.form_submit_button("✖️ Cancel", use_container_width=True)
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
                st.markdown("#### ➕ Quick Add Question")
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
                    exp_new = st.text_area("📖 Explanation (optional)", key="new_explanation")
                    if st.form_submit_button("🚀 Add Question"):
                        if q_text_new.strip():
                            supabase.table("questions").insert({
                                "exam_id": selected_exam_id, "question": q_text_new, "type": q_type_new,
                                "option_a": a_new, "option_b": b_new, "option_c": c_new, "option_d": d_new,
                                "correct_answer": c_ans_new if q_type_new != "programming" else "Manual Review Required",
                                "hint": h_text_new,
                                "explanation": exp_new.strip() if exp_new.strip() else None
                            }).execute()
                            st.success("Added!"); st.rerun()
                        else:
                            st.error("Question text empty!")

    elif menu == "📊 Student Results & Ranks":
        r_tab1, r_tab2, r_tab3, r_tab4, r_tab5, r_tab6 = st.tabs([
            "🏆 Leaderboards", "📝 Manual Evaluation", "📜 Score Summary",
            "🔄 Re-Exam Requests", "📌 Explain Requests", "📅 Attendance"
        ])

        with r_tab1:
            st.title("🏆 Leaderboard")
            exams = supabase.table("exams").select("*").execute().data
            if exams:
                sel_ex_lb = st.selectbox("Select Exam", [e["title"] for e in exams])
                target_ex = next((e for e in exams if e["title"] == sel_ex_lb), None)
                if target_ex:
                    board = get_exam_leaderboard(target_ex["id"])
                    if board:
                        for rank, st_row in enumerate(board):
                            medal = "🥇" if rank==0 else "🥈" if rank==1 else "🥉" if rank==2 else f"{rank+1}."
                            st.write(f"{medal} **{st_row['Name']}** ({st_row['Email']}) — Score: **{st_row['Score']}**")
                    else:
                        st.info("No attempts yet.")

        with r_tab2:
            st.title("📝 Manual Evaluator")
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
                                st.markdown(f"##### 👤 **{u_data[0]['name']}** | 🎯 **{e_data[0]['title']}**")
                                st.code(att.get("submitted_answers","# No code submitted."), language="python")
                            with col_s2:
                                new_score = st.number_input("Score", min_value=0, max_value=100, value=int(att["score"]), key=f"score_in_{att['id']}")
                                if st.button("💾 Save", key=f"btn_score_{att['id']}", type="primary", use_container_width=True):
                                    supabase.table("exam_attempts").update({"score": new_score}).eq("id", att["id"]).execute()
                                    st.success("Score Saved!"); st.rerun()

        with r_tab3:
            st.title("Score Logger")
            attempts = supabase.table("exam_attempts").select("*").execute().data
            if not attempts:
                st.warning("No submissions yet.")
            else:
                for att in attempts:
                    u_prof = supabase.table("users").select("*").eq("id", att["user_id"]).execute().data
                    e_prof = supabase.table("exams").select("*").eq("id", att["exam_id"]).execute().data
                    if u_prof and e_prof:
                        st.markdown(f"👤 **{u_prof[0]['name']}** — **{e_prof[0]['title']}** — Score: **{att['score']}**")
                        st.divider()

        with r_tab4:
            st.title("🔄 Re-Exam Requests")
            requests_data = supabase.table("exam_retake_requests").select("*").eq("status","pending").order("requested_at",desc=True).execute().data
            if not requests_data:
                st.info("Pending requests లేవు.")
            else:
                for req in requests_data:
                    u_info = supabase.table("users").select("name, email").eq("id", req["user_id"]).execute().data
                    e_info = supabase.table("exams").select("title").eq("id", req["exam_id"]).execute().data
                    if u_info and e_info:
                        with st.container(border=True):
                            col1, col2, col3 = st.columns([4, 1, 1])
                            with col1:
                                st.markdown(f"**👤 {u_info[0]['name']}** ({u_info[0]['email']})")
                                st.caption(f"📝 {e_info[0]['title']} | {req['requested_at'][:10]}")
                            with col2:
                                if st.button("✅ Approve", key=f"apr_{req['id']}", type="primary", use_container_width=True):
                                    supabase.table("exam_retake_requests").update({"status":"approved","reviewed_at":"now()"}).eq("id",req["id"]).execute()
                                    st.success("Approved!"); st.rerun()
                            with col3:
                                if st.button("❌ Reject", key=f"rej_{req['id']}", use_container_width=True):
                                    supabase.table("exam_retake_requests").update({"status":"rejected","reviewed_at":"now()"}).eq("id",req["id"]).execute()
                                    st.warning("Rejected!"); st.rerun()

        with r_tab5:
            st.title("📌 Explain Requests")
            exp_requests = supabase.table("explain_requests").select("*").order("created_at",desc=True).execute().data
            if not exp_requests:
                st.info("Explain requests లేవు.")
            else:
                for req in exp_requests:
                    u_info = supabase.table("users").select("name, email").eq("id", req["user_id"]).execute().data
                    e_info = supabase.table("exams").select("title").eq("id", req["exam_id"]).execute().data
                    uname = u_info[0]["name"] if u_info else "Unknown"
                    ename = e_info[0]["title"] if e_info else "Unknown Exam"
                    qids = json.loads(req["question_ids"]) if req.get("question_ids") else []
                    status = req.get("status","pending")
                    status_color = {"pending":"🟡","done":"🟢","rejected":"🔴"}.get(status,"🟡")
                    with st.container(border=True):
                        col1, col2, col3 = st.columns([4, 1, 1])
                        with col1:
                            st.markdown(f"**👤 {uname}** ({u_info[0]['email'] if u_info else ''})")
                            st.caption(f"📝 {ename} | {len(qids)} questions | {status_color} {status} | {str(req.get('created_at',''))[:10]}")
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
                                        st.download_button("📊 PPT", data=ppt_bytes,
                                            file_name=f"{ename[:20]}_explain.pptx",
                                            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                                            key=f"exp_ppt_{req['id']}")
                        with col3:
                            if status == "pending":
                                if st.button("✅ Done", key=f"exp_done_{req['id']}", use_container_width=True, type="primary"):
                                    supabase.table("explain_requests").update({"status":"done"}).eq("id",req["id"]).execute()
                                    st.rerun()

        with r_tab6:
            st.title("📅 Student Attendance")
            all_students = supabase.table("users").select("id, name, email").eq("role","user").execute().data
            if not all_students:
                st.info("Students లేరు.")
            else:
                sel_student = st.selectbox("Student select చేయండి", [f"{s['name']} ({s['email']})" for s in all_students])
                sel_idx = [f"{s['name']} ({s['email']})" for s in all_students].index(sel_student)
                sel_uid = all_students[sel_idx]["id"]
                show_attendance_tab(sel_uid)

    elif menu == "💬 Group Chat":
        with st.expander("🔔 Broadcast Notification పంపండి"):
            notif_msg = st.text_input("Message", key="broadcast_msg")
            if st.button("📣 Send to All Users", type="primary"):
                if notif_msg.strip():
                    send_notification(notif_msg.strip())
                    st.success("✅ పంపబడింది!"); st.rerun()
                else:
                    st.warning("Message enter చేయండి.")
        st.divider()
        group_chat()

# =========================
# USER DASHBOARD
# =========================
def user_dashboard(preview_mode=False):
    if not preview_mode:
        st.sidebar.title("User Workspace")
        if st.sidebar.button("🚪 Logout", use_container_width=True):
            for key in defaults:
                st.session_state[key] = defaults[key]
            st.query_params.clear()
            st.rerun()
        st.sidebar.divider()
        pages = ["📚 My Classes", "💬 Group Chat", "📅 Attendance"]
        for pg in pages:
            if pg == "💬 Group Chat":
                unread = get_unread_count(st.session_state.user_id)
                label = f"💬 Group Chat  🔴{unread}" if unread > 0 else "💬 Group Chat"
            else:
                label = pg
            if st.sidebar.button(label, use_container_width=True,
                    type="primary" if st.session_state.user_page == pg else "secondary",
                    key=f"nav_{pg}"):
                st.session_state.user_page = pg
                st.rerun()
        user_page = st.session_state.user_page
        # Mark today's attendance on every login
        mark_today_attendance(st.session_state.user_id)
    else:
        st.info("👁️ Student Preview Mode")
        user_page = "📚 My Classes"

    if not preview_mode:
        show_notification_banner(st.session_state.user_id)

    if user_page == "💬 Group Chat":
        group_chat(); return
    if user_page == "📅 Attendance":
        show_attendance_tab(st.session_state.user_id); return

    # My Classes
    modules = supabase.table("modules").select("*").execute().data
    if st.session_state.completed_ids is None:
        all_completions = supabase.table("class_completions").select("class_id").eq("user_id", st.session_state.user_id).execute().data
        st.session_state.completed_ids = {str(c["class_id"]) for c in all_completions}
    completed_ids = st.session_state.completed_ids

    for module in modules:
        module_submodules = supabase.table("submodules").select("id").eq("module_id", module["id"]).execute().data
        sub_ids = [s["id"] for s in module_submodules]
        module_total = 0; module_done = 0
        for sid in sub_ids:
            cls_list = supabase.table("classes").select("id").eq("submodule_id", sid).execute().data
            module_total += len(cls_list)
            module_done += sum(1 for c in cls_list if str(c["id"]) in completed_ids)
        pct = int((module_done / module_total * 100)) if module_total > 0 else 0

        with st.expander(f"{module['title']}  —  {module_done}/{module_total} classes  ({pct}%)"):
            if module_total > 0:
                st.progress(pct / 100, text=f"Module Progress: {pct}%")
            submodules = supabase.table("submodules").select("*").eq("module_id", module["id"]).execute().data
            for sub in submodules:
                sub_classes = supabase.table("classes").select("id").eq("submodule_id", sub["id"]).execute().data
                sub_total = len(sub_classes)
                sub_done = sum(1 for c in sub_classes if str(c["id"]) in completed_ids)
                sub_pct = int((sub_done / sub_total * 100)) if sub_total > 0 else 0
                st.subheader(f"{sub['title']}  ✅ {sub_done}/{sub_total}")
                if sub_total > 0: st.progress(sub_pct / 100)
                classes = supabase.table("classes").select("*").eq("submodule_id", sub["id"]).execute().data
                for cls in classes:
                    is_done = str(cls.get("id")) in completed_ids
                    st.markdown(f"### {'✅' if is_done else '🔲'} {cls['title']}")
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
                        if str(class_id) in completed_ids:
                            st.success("✅ మీరు ఈ క్లాస్ పూర్తి చేశారు!")
                        else:
                            if st.button("✔️ Mark as Completed", key=f"btn_done_{cls['id']}"):
                                try:
                                    supabase.table("class_completions").insert({"user_id": str(st.session_state.user_id), "class_id": cid}).execute()
                                    st.session_state.completed_ids.add(str(class_id))
                                    st.success("✅ క్లాస్ కంప్లీట్ అయ్యింది!")
                                except Exception as e:
                                    st.error(f"Insert Error: {e}")

                    exams = supabase.table("exams").select("*").eq("class_id", cls["id"]).execute().data
                    for exam in exams:
                        if not exam["enabled"]: continue
                        exam_dur = exam.get("duration_mins", 30)
                        st.write(f"📝 **Exam: {exam['title']}** ({exam_dur} Mins)")
                        btn_col, lb_col = st.columns([2, 2])
                        with lb_col:
                            board = get_exam_leaderboard(exam["id"])
                            if board:
                                st.markdown("🏆 **Top Performers:**")
                                for idx, student in enumerate(board[:3]):
                                    medal = "🥇" if idx==0 else "🥈" if idx==1 else "🥉"
                                    st.caption(f"{medal} {student['Name']} — {student['Score']}")
                            else:
                                st.caption("Be the first! 🚀")
                        with btn_col:
                            check_attempt = supabase.table("exam_attempts").select("*").eq("user_id", st.session_state.user_id).eq("exam_id", exam["id"]).execute().data
                            if check_attempt:
                                q_count = supabase.table("questions").select("id").eq("exam_id", exam["id"]).execute().data
                                total_q = len(q_count)
                                st.markdown("**📊 మీ Attempts:**")
                                for idx, att in enumerate(check_attempt):
                                    st.caption(f"Attempt {idx+1}: **{att['score']}/{total_q}**")
                                if st.button("🔍 Show Answers", key=f"view_{exam['id']}", use_container_width=True):
                                    st.session_state.exam_id = exam["id"]
                                    st.session_state.exam_title = exam["title"]
                                    st.session_state.start_exam = True
                                    st.session_state.exam_submitted = True
                                    st.session_state.current_questions = supabase.table("questions").select("*").eq("exam_id", exam["id"]).execute().data
                                    st.rerun()
                                retake_req = supabase.table("exam_retake_requests").select("*").eq("user_id", st.session_state.user_id).eq("exam_id", exam["id"]).order("requested_at",desc=True).limit(1).execute().data
                                if retake_req:
                                    status = retake_req[0]["status"]
                                    if status == "pending":
                                        st.warning("⏳ Re-exam request pending...")
                                    elif status == "rejected":
                                        st.error("❌ Re-exam rejected.")
                                        if st.button("🔄 మళ్ళీ Request", key=f"retry_req_{exam['id']}", use_container_width=True):
                                            supabase.table("exam_retake_requests").insert({"user_id": st.session_state.user_id, "exam_id": exam["id"], "status":"pending"}).execute()
                                            st.success("Request పంపబడింది!"); st.rerun()
                                    elif status == "approved":
                                        st.success("✅ Re-exam approved!")
                                        has_pwd = exam.get("password") and str(exam["password"]).strip()
                                        entered_pwd = st.text_input(f"Access Code", type="password", key=f"repwd_{exam['id']}") if has_pwd else ""
                                        if st.button("📝 Re-Exam Start", key=f"rebtn_{exam['id']}", use_container_width=True, type="primary"):
                                            if has_pwd and entered_pwd.strip() != str(exam["password"]).strip():
                                                st.error("Wrong Password!")
                                            else:
                                                supabase.table("exam_retake_requests").update({"status":"used"}).eq("id",retake_req[0]["id"]).execute()
                                                q_data = supabase.table("questions").select("*").eq("exam_id", exam["id"]).execute().data
                                                st.session_state.update({"exam_id":exam["id"],"exam_title":exam["title"],"start_exam":True,"exam_submitted":False,"answers":{},"question_index":0,"current_questions":q_data,"exam_end_time":time.time()+(int(exam_dur)*60)})
                                                st.rerun()
                                else:
                                    if st.button("🔄 Try Again Request", key=f"req_{exam['id']}", use_container_width=True):
                                        supabase.table("exam_retake_requests").insert({"user_id": st.session_state.user_id, "exam_id": exam["id"], "status":"pending"}).execute()
                                        st.success("✅ Request పంపబడింది!"); st.rerun()
                            else:
                                has_pwd = exam.get("password") and str(exam["password"]).strip()
                                entered_pwd = st.text_input(f"Access Code for {exam['title']}", type="password", key=f"pwd_{exam['id']}") if has_pwd else ""
                                if st.button("📝 Start Exam", key=f"btn_{exam['id']}", use_container_width=True):
                                    if has_pwd and entered_pwd.strip() != str(exam["password"]).strip():
                                        st.error("Wrong Password!")
                                    else:
                                        q_data = supabase.table("questions").select("*").eq("exam_id", exam["id"]).execute().data
                                        st.session_state.update({"exam_id":exam["id"],"exam_title":exam["title"],"start_exam":True,"exam_submitted":False,"answers":{},"question_index":0,"current_questions":q_data,"exam_end_time":time.time()+(int(exam_dur)*60)})
                                        st.rerun()
                    st.divider()

# =========================
# EXAM WORKSPACE
# =========================
def exam_workspace_view():
    questions = st.session_state.current_questions
    total_questions = len(questions)
    if total_questions == 0:
        st.warning("No questions in this exam.")
        if st.button("Go Back"): st.session_state.start_exam = False; st.rerun()
        return

    remaining_time = 0
    if not st.session_state.exam_submitted:
        remaining_time = int(st.session_state.exam_end_time - time.time())
        if remaining_time <= 0:
            st.error("⏰ Time Out! Submitting exam...")
            time.sleep(1)
            final_score = 0
            attempt_uuid = str(uuid.uuid4())
            for q in questions:
                user_val = st.session_state.answers.get(q["id"],"")
                if q["type"] != "programming" and check_mcq_correct(user_val, q) if q["type"] == "mcq" else str(user_val).strip().lower() == str(q.get("correct_answer","")).strip().lower():
                    final_score += 1
            supabase.table("exam_attempts").insert({"id":attempt_uuid,"user_id":st.session_state.user_id,"exam_id":st.session_state.exam_id,"score":final_score}).execute()
            for q in questions:
                supabase.table("user_answers").insert({"attempt_id":attempt_uuid,"question_id":q["id"],"answer":st.session_state.answers.get(q["id"],"")}).execute()
            st.session_state.exam_submitted = True; st.rerun()

    if st.session_state.exam_submitted:
        st.title(f"📊 Results: {st.session_state.exam_title}")
        db_attempt = supabase.table("exam_attempts").select("*").eq("user_id", st.session_state.user_id).eq("exam_id", st.session_state.exam_id).execute().data
        if db_attempt:
            st.markdown("### 📊 మీ అన్ని Attempts")
            for idx, att in enumerate(reversed(db_attempt)):
                st.info(f"Attempt {idx+1}: **{att['score']}/{total_questions}**")
            st.divider()
            latest = db_attempt[0]
            st.success(f"🎉 Latest Score: {latest['score']}/{total_questions}")
            db_answers = supabase.table("user_answers").select("*").eq("attempt_id", latest["id"]).execute().data
            ans_map = {a["question_id"]: a["answer"] for a in db_answers}
            exam_data = supabase.table("exams").select("*").eq("id", st.session_state.exam_id).execute().data
            if exam_data and exam_data[0]["show_answers"]:
                st.subheader("📚 Review Sheet")
                render_review_sheet(questions, ans_map, db_attempt)

        if st.button("Return to Dashboard", type="primary"):
            st.session_state.start_exam = False
            st.session_state.exam_submitted = False
            st.session_state.answers = {}
            st.session_state.question_index = 0
            st.session_state.current_questions = []
            st.rerun()
    else:
        st.title(st.session_state.exam_title)
        current = st.session_state.question_index
        question = questions[current]
        left, right = st.columns([4, 1])
        with right:
            mins, secs = divmod(remaining_time, 60)
            st.components.v1.html(f"""
                <div id="timer" style="font-size:2rem;font-weight:600;text-align:center;padding:12px;border-radius:8px;
                    background:{'#fff3cd' if remaining_time<300 else '#e8f4fd'};
                    color:{'#856404' if remaining_time<300 else '#0c63e4'};
                    border:1px solid {'#ffc107' if remaining_time<300 else '#b6d4fe'};">
                    ⏱️ <span id="countdown">{mins:02d}:{secs:02d}</span></div>
                <script>
                    var total={remaining_time};
                    function tick(){{if(total<=0){{document.getElementById('countdown').innerText="00:00";return;}}
                    total--;var m=Math.floor(total/60).toString().padStart(2,'0');var s=(total%60).toString().padStart(2,'0');
                    document.getElementById('countdown').innerText=m+':'+s;
                    if(total<300){{var el=document.getElementById('timer');el.style.background='#fff3cd';el.style.color='#856404';}}}}
                    setInterval(tick,1000);
                </script>""", height=80)
            st.divider()
            st.subheader("Questions")
            cols = st.columns(3)
            for i in range(total_questions):
                with cols[i % 3]:
                    q_id = questions[i]["id"]
                    label = f"🔵 {i+1}" if i==current else (f"🟢 {i+1}" if q_id in st.session_state.answers and st.session_state.answers[q_id] else f"🔴 {i+1}")
                    if st.button(label, key=f"qnav_{i}", use_container_width=True):
                        st.session_state.question_index = i; st.rerun()

        with left:
            hcol1, hcol2 = st.columns([4, 1])
            with hcol1: st.subheader(f"Question {current+1}/{total_questions}")
            with hcol2:
                qid = question["id"]
                already_spent = st.session_state.question_time_log.get(qid, 0)
                st.components.v1.html(f"""
                    <div style="background:#f0f4ff;border:1px solid #b6d4fe;border-radius:8px;padding:6px 10px;
                        text-align:center;font-family:monospace;font-size:1.1rem;font-weight:600;color:#0c63e4;margin-top:8px;">
                        📝 <span id="qtimer">00:00</span></div>
                    <script>var elapsed={already_spent};var qtimer=document.getElementById('qtimer');
                    function qtick(){{elapsed++;var m=Math.floor(elapsed/60).toString().padStart(2,'0');var s=(elapsed%60).toString().padStart(2,'0');qtimer.innerText=m+':'+s;}}
                    setInterval(qtick,1000);</script>""", height=55)

            st.write(question["question"])
            if question.get("image_url"): st.image(question["image_url"], width=350)
            if qid not in st.session_state.question_start_time:
                st.session_state.question_start_time[qid] = time.time()
            stored_ans = st.session_state.answers.get(question["id"],"")

            if question["type"] == "mcq":
                opts = [
                    ("A", question.get("option_a","")),
                    ("B", question.get("option_b","")),
                    ("C", question.get("option_c","")),
                    ("D", question.get("option_d","")),
                ]
                st.markdown("")
                for lbl, otxt in opts:
                    if not otxt:
                        continue
                    is_selected = (stored_ans == lbl or stored_ans == otxt)
                    if is_selected:
                        bg, border, col, fw = "#1a73e8", "#1a73e8", "#ffffff", "700"
                        prefix = "🔵 "
                    else:
                        bg, border, col, fw = "#ffffff", "#d0d8e8", "#2c3e50", "400"
                        prefix = ""
                    # Full-width clickable button styled as option card
                    btn_html = (
                        f"<div style='background:{bg};border:2px solid {border};border-radius:10px;"
                        f"padding:12px 18px;margin-bottom:8px;color:{col};font-weight:{fw};"
                        f"font-size:1rem;cursor:pointer;'>{prefix}{lbl}. {otxt}</div>"
                    )
                    # Render display card + invisible streamlit button below it
                    st.markdown(btn_html, unsafe_allow_html=True)
                    if st.button(f"{lbl}. {otxt}", key=f"opt_{question['id']}_{lbl}",
                                 use_container_width=True,
                                 type="primary" if is_selected else "secondary"):
                        st.session_state.answers[question["id"]] = lbl
                        st.rerun()

            elif question["type"] == "blank":
                answer = st.text_input("Your Answer", value=stored_ans, key=f"text_{question['id']}")
                if answer != stored_ans:
                    st.session_state.answers[question["id"]] = answer
            else:
                answer = st.text_area("Write your Code/Answer:", value=stored_ans, key=f"code_{question['id']}", height=250)
                if answer != stored_ans:
                    st.session_state.answers[question["id"]] = answer

            def save_current_q_time():
                qid_cur = question["id"]
                if qid_cur in st.session_state.question_start_time:
                    elapsed = int(time.time() - st.session_state.question_start_time[qid_cur])
                    prev = st.session_state.question_time_log.get(qid_cur, 0)
                    st.session_state.question_time_log[qid_cur] = prev + elapsed
                    del st.session_state.question_start_time[qid_cur]

            nav_col1, nav_col2, submit_col = st.columns([1, 1, 2])
            with nav_col1:
                if st.button("⬅️ Previous", disabled=(current==0), use_container_width=True):
                    save_current_q_time(); st.session_state.question_index -= 1; st.rerun()
            with nav_col2:
                if st.button("Next ➡️", disabled=(current==total_questions-1), use_container_width=True):
                    save_current_q_time(); st.session_state.question_index += 1; st.rerun()
            with submit_col:
                if st.button("🚀 Submit Exam", type="primary", use_container_width=True):
                    save_current_q_time()
                    final_score = 0
                    attempt_uuid = str(uuid.uuid4())
                    for q in questions:
                        user_val = st.session_state.answers.get(q["id"],"")
                        if q["type"] != "programming" and check_mcq_correct(user_val, q) if q["type"] == "mcq" else str(user_val).strip().lower() == str(q.get("correct_answer","")).strip().lower():
                            final_score += 1
                    supabase.table("exam_attempts").insert({"id":attempt_uuid,"user_id":st.session_state.user_id,"exam_id":st.session_state.exam_id,"score":final_score}).execute()
                    for q in questions:
                        user_val = st.session_state.answers.get(q["id"],"")
                        t_spent = st.session_state.question_time_log.get(q["id"],0)
                        supabase.table("user_answers").insert({"attempt_id":attempt_uuid,"question_id":q["id"],"answer":user_val,"time_spent_seconds":t_spent}).execute()
                    st.session_state.question_time_log = {}
                    st.session_state.question_start_time = {}
                    st.session_state.exam_submitted = True; st.rerun()

        if remaining_time <= 0: st.rerun()

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
    elif st.session_state.start_exam:
        exam_workspace_view()
    else:
        user_dashboard(preview_mode=False)
