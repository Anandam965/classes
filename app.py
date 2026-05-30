import os
import uuid
import time
import json
import requests  # FIX 1: requests import add chesamu

import streamlit as st
from supabase import create_client
import google.generativeai as genai

# =========================
# PAGE CONFIG - FIX 2: Must be FIRST streamlit call
# =========================
st.set_page_config(
    page_title="Advanced LMS Admin Portal",
    layout="wide"
)

# =========================
# SUPABASE + GEMINI INIT - FIX 3: Only ONE supabase client, no duplicate
# =========================
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error("Secrets లో విలువలు కనపడటం లేదు. Settings -> Secrets ని ఒకసారి చెక్ చేయండి.")
    st.stop()

# FIX 4: Gemini API key configure chesamu (secrets lo GEMINI_API_KEY add cheyyandi)
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except Exception:
    pass  # AI tab use cheyyanappudu error raadu

# =========================
# SESSION STATES INITIALIZATION
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
    "pin_verified": False,      # PIN verify అయిందా లేదా
    "pin_setup_mode": False,    # కొత్త PIN set చేస్తున్నారా
    "email_temp": "",           # PIN screen కోసం email store
    "user_id_temp": "",         # PIN screen కోసం user_id store
    "role_temp": "",            # PIN screen కోసం role store
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# =========================
# JAVA CODE EVALUATOR
# =========================
def evaluate_java_code(user_code, input_data, expected_output):
    url = "https://judge0-ce.p.rapidapi.com/submissions?base64_encoded=false&fields=*"
    payload = {
        "source_code": user_code,
        "language_id": 27,
        "stdin": input_data
    }
    headers = {
        "x-rapidapi-key": st.secrets.get("RAPIDAPI_KEY", ""),  # FIX 5: secrets lo pettandi
        "Content-Type": "application/json"
    }
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
# LOGIN FUNCTION
# =========================
def login():
    st.title("📚 LMS Login")

    login_method = st.radio(
        "Login method:",
        ["📧 Email & Password", "🔑 PIN తో Login"],
        horizontal=True,
        key="login_method_radio"
    )

    if login_method == "📧 Email & Password":
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")

        if st.button("Login", type="primary", use_container_width=True, key="email_login_btn"):
            try:
                response = supabase.auth.sign_in_with_password({
                    "email": email, "password": password
                })
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
        # PIN only login — globally unique PIN
        st.caption("మీ unique PIN enter చేయండి.")
        pin = st.text_input("🔑 PIN", type="password", max_chars=6, key="pin_only_input")

        if st.button("🔓 Enter App", type="primary", use_container_width=True, key="pin_only_btn"):
            if not pin:
                st.error("PIN enter చేయండి.")
            else:
                try:
                    # PIN unique కాబట్టి directly DB లో search చేయి
                    user_data = supabase.table("users").select("*").eq("app_pin", pin).execute()
                    if not user_data.data:
                        st.error("❌ Wrong PIN! మళ్ళీ try చేయండి.")
                    else:
                        urow = user_data.data[0]
                        st.session_state.logged_in = True
                        st.session_state.role = urow["role"]
                        st.session_state.user_id = urow["id"]
                        st.session_state.pin_verified = True
                        st.rerun()
                except Exception as e:
                    st.error(str(e))


def pin_screen():
    """PIN setup లేదా verify screen"""
    st.title("🔒 App Lock")

    if st.session_state.pin_setup_mode:
        # కొత్త PIN set చేయాలి
        st.subheader("మీ PIN set చేయండి (4-6 digits)")
        st.caption("ఈ PIN globally unique గా ఉంటుంది. మీకు మాత్రమే తెలిసిన PIN ఇవ్వండి.")
        pin1 = st.text_input("కొత్త PIN (4-6 digits)", type="password", max_chars=6, key="pin_new")
        pin2 = st.text_input("PIN మళ్ళీ enter చేయండి", type="password", max_chars=6, key="pin_confirm")

        if st.button("✅ PIN Set చేయి", type="primary", use_container_width=True):
            if not pin1.isdigit() or len(pin1) < 4:
                st.error("4-6 digits మాత్రమే enter చేయండి!")
            elif pin1 != pin2:
                st.error("రెండు PINలు match కాలేదు!")
            else:
                # Unique check — ఈ PIN వేరె user వాడుతున్నారా?
                existing = supabase.table("users").select("id").eq("app_pin", pin1).execute().data
                if existing and existing[0]["id"] != st.session_state.user_id_temp:
                    st.error("❌ ఈ PIN వేరె user వాడుతున్నారు. వేరే PIN try చేయండి!")
                else:
                    supabase.table("users").update({"app_pin": pin1})                         .eq("id", st.session_state.user_id_temp).execute()
                    st.session_state.logged_in = True
                    st.session_state.role = st.session_state.role_temp
                    st.session_state.user_id = st.session_state.user_id_temp
                    st.session_state.pin_verified = True
                    st.success("PIN set అయింది! Welcome 🎉")
                    st.rerun()

    else:
        # Existing PIN verify చేయాలి
        st.subheader("మీ PIN enter చేయండి")
        pin_input = st.text_input("4-digit PIN", type="password", max_chars=4, key="pin_entry")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔓 Enter App", type="primary", use_container_width=True):
                # DB నుండి PIN fetch చేసి compare చేయి
                urow = supabase.table("users").select("app_pin").eq("id", st.session_state.user_id_temp).execute().data
                if urow and urow[0]["app_pin"] == pin_input:
                    st.session_state.logged_in = True
                    st.session_state.role = st.session_state.role_temp
                    st.session_state.user_id = st.session_state.user_id_temp
                    st.session_state.pin_verified = True
                    st.rerun()
                else:
                    st.error("❌ Wrong PIN! మళ్ళీ try చేయండి.")
        with col2:
            if st.button("🔙 వేరే Account తో Login", use_container_width=True):
                # Temp state clear చేసి login కి తిరిగి వెళ్ళు
                st.session_state.email_temp = ""
                st.session_state.user_id_temp = ""
                st.session_state.role_temp = ""
                st.session_state.pin_verified = False
                st.session_state.pin_setup_mode = False
                st.rerun()

# =========================
# HELPER: LEADERBOARD
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
                leaderboard.append({
                    "Name": user_info[0]["name"],
                    "Email": user_info[0]["email"],
                    "Score": max_score
                })
        return sorted(leaderboard, key=lambda x: x["Score"], reverse=True)
    except Exception:
        return []

# =========================
# ADMIN DASHBOARD
# =========================
def admin_dashboard():
    st.sidebar.title("🛡️ Admin Workspace")

    if st.sidebar.button("🚪 Logout", use_container_width=True):
        for key in defaults:
            st.session_state[key] = defaults[key]
        st.rerun()

    if "admin_preview_mode" not in st.session_state:
        st.session_state.admin_preview_mode = False

    st.sidebar.divider()
    if st.session_state.admin_preview_mode:
        if st.sidebar.button("🛡️ Admin View కి తిరిగి వెళ్ళు", use_container_width=True, type="primary"):
            st.session_state.admin_preview_mode = False
            st.rerun()
        user_dashboard(preview_mode=True)
        return
    else:
        if st.sidebar.button("👁️ Student View Preview", use_container_width=True):
            st.session_state.admin_preview_mode = True
            st.rerun()
    st.sidebar.divider()

    menu = st.sidebar.selectbox(
        "Navigation Control",
        ["🗂️ Manage Course Content", "📝 Manage Exams & Questions", "📊 Student Results & Ranks", "💬 Group Chat"]
    )

    if menu == "🗂️ Manage Course Content":
        tab1, tab2, tab3 = st.tabs(["📁 Modules Setup", "📂 Submodules Setup", "🖥️ Live/Recorded Classes"])

        with tab1:
            st.subheader("Manage Core Modules")
            with st.form("add_module_form", clear_on_submit=True):
                module_name = st.text_input("New Module Title")
                if st.form_submit_button("✨ Save Module"):
                    if module_name.strip():
                        supabase.table("modules").insert({"title": module_name}).execute()
                        st.success("Module Added Successfully!")
                        st.rerun()

            st.divider()
            st.write("### Existing Modules")
            modules = supabase.table("modules").select("*").execute().data
            for m in modules:
                col1, col2, col3 = st.columns([4, 1, 1])
                with col1:
                    new_m_title = st.text_input("Module Name", value=m["title"], key=f"mod_t_{m['id']}")
                with col2:
                    if st.button("💾 Update", key=f"mod_u_{m['id']}", use_container_width=True):
                        supabase.table("modules").update({"title": new_m_title}).eq("id", m["id"]).execute()
                        st.success("Updated!")
                        st.rerun()
                with col3:
                    if st.button("🗑️ Delete", key=f"mod_d_{m['id']}", type="secondary", use_container_width=True):
                        supabase.table("modules").delete().eq("id", m["id"]).execute()
                        st.warning("Module Deleted!")
                        st.rerun()

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
                        st.success("Submodule Linked!")
                        st.rerun()

            st.divider()
            st.write("### Existing Submodules")
            submodules = supabase.table("submodules").select("*").execute().data
            for s in submodules:
                p_module = supabase.table("modules").select("title").eq("id", s["module_id"]).execute().data
                p_title = p_module[0]["title"] if p_module else "Unknown Module"
                col1, col2, col3, col4 = st.columns([2, 3, 1, 1])
                with col1:
                    st.caption(f"Parent: {p_title}")
                with col2:
                    new_s_title = st.text_input("Edit Title", value=s["title"], key=f"sub_t_{s['id']}", label_visibility="collapsed")
                with col3:
                    if st.button("💾 Update", key=f"sub_u_{s['id']}", use_container_width=True):
                        supabase.table("submodules").update({"title": new_s_title}).eq("id", s["id"]).execute()
                        st.success("Updated!")
                        st.rerun()
                with col4:
                    if st.button("🗑️ Delete", key=f"sub_d_{s['id']}", type="secondary", use_container_width=True):
                        supabase.table("submodules").delete().eq("id", s["id"]).execute()
                        st.warning("Deleted!")
                        st.rerun()

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
                            st.success("Class Data Broadcasted!")
                            st.rerun()

            st.divider()
            st.write("### Active Classes Directory")

            # Total enrolled users count (role = student)
            # admin కాకుండా అన్ని users count చేయాలి
            all_users = supabase.table("users").select("id, role").execute().data
            total_users = len([u for u in all_users if u.get("role") == "user"])

            classes = supabase.table("classes").select("*").execute().data
            for cls in classes:
                # Completion stats
                comp_data = supabase.table("class_completions").select("user_id").eq("class_id", cls["id"]).execute().data
                comp_count = len(comp_data)
                pct = int((comp_count / total_users * 100)) if total_users > 0 else 0

                # Expander title లోనే percentage చూపించాలి
                expander_label = f"🖥️ {cls['title']}  —  {comp_count}/{total_users} students  ({pct}%)"
                with st.expander(expander_label):

                    # Progress bar
                    col_prog, col_num = st.columns([5, 1])
                    with col_prog:
                        st.progress(pct / 100)
                    with col_num:
                        st.markdown(f"**{pct}%**")

                    # Completed students list (expandable)
                    if comp_count > 0:
                        with st.expander(f"👥 {comp_count} మంది complete చేశారు — చూడు"):
                            for row in comp_data:
                                u = supabase.table("users").select("name, email").eq("id", row["user_id"]).execute().data
                                if u:
                                    st.caption(f"✅ {u[0]['name']} ({u[0]['email']})")

                    st.divider()
                    ec_title = st.text_input("Title", value=cls["title"], key=f"ct_{cls['id']}")
                    ec_link = st.text_input("Live Link", value=cls.get("class_link", ""), key=f"cl_{cls['id']}")
                    ev_link = st.text_input("Video Link", value=cls.get("recorded_video", ""), key=f"cv_{cls['id']}")
                    ep_link = st.text_input("PDF Link", value=cls.get("notes_pdf", ""), key=f"cp_{cls['id']}")

                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("💾 Save Changes", key=f"cu_{cls['id']}", type="primary", use_container_width=True):
                            supabase.table("classes").update({
                                "title": ec_title, "class_link": ec_link,
                                "recorded_video": ev_link, "notes_pdf": ep_link
                            }).eq("id", cls["id"]).execute()
                            st.success("Class Record Saved!")
                            st.rerun()
                    with b2:
                        if st.button("🗑️ Remove Class", key=f"cd_{cls['id']}", use_container_width=True):
                            supabase.table("classes").delete().eq("id", cls["id"]).execute()
                            st.warning("Class Data Purged!")
                            st.rerun()

    elif menu == "📝 Manage Exams & Questions":
        ex_tab1, ex_tab2, ex_tab3, ex_tab4, ex_tab5 = st.tabs([
            "📝 Exams Setup",
            "❓ Add Questions",
            "🔍 Review Papers",
            "📁 Bulk Upload (CSV)",
            "🤖 AI Gen"
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
                            "class_id": cls_options[sel_cls],
                            "title": e_title,
                            "duration_mins": int(e_duration),
                            "password": e_pwd.strip() if e_pwd.strip() else None,
                            "enabled": c_en,
                            "show_answers": c_ans
                        }).execute()
                        st.success("Exam Created!")
                        st.rerun()

            st.divider()
            st.write("### ⚙️ Live Exam Controls")
            exams_all = supabase.table("exams").select("*").execute().data
            for ex in exams_all:
                with st.container(border=True):
                    st.markdown(f"#### 📄 **{ex['title']}**")
                    col_e1, col_e2, col_e3 = st.columns([2, 2, 2])
                    with col_e1:
                        updated_dur = st.number_input("Duration (Mins)", min_value=1, max_value=180,
                                                       value=int(ex.get("duration_mins", 30)), key=f"dur_{ex['id']}")
                    with col_e2:
                        updated_pwd = st.text_input("Password", value=str(ex.get("password", "") or ""), key=f"pwd_ed_{ex['id']}")
                    with col_e3:
                        t_active = st.toggle("Active", value=ex["enabled"], key=f"tog_en_{ex['id']}")
                        t_ans = st.toggle("Show Answers", value=ex["show_answers"], key=f"tog_ans_{ex['id']}")

                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("💾 Save", key=f"up_ex_{ex['id']}", type="primary", use_container_width=True):
                            supabase.table("exams").update({
                                "duration_mins": int(updated_dur),
                                "password": updated_pwd.strip() if updated_pwd.strip() else None,
                                "enabled": t_active,
                                "show_answers": t_ans
                            }).eq("id", ex["id"]).execute()
                            st.success("Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Delete Exam", key=f"del_ex_{ex['id']}", type="secondary", use_container_width=True):
                            supabase.table("exams").delete().eq("id", ex["id"]).execute()
                            st.warning("Exam Deleted!")
                            st.rerun()

        with ex_tab2:
            st.subheader("Add Questions")
            exams_q = supabase.table("exams").select("*").execute().data
            ex_options = {e["title"]: e["id"] for e in exams_q} if exams_q else {}

            with st.form("add_question_form", clear_on_submit=True):
                sel_ex = st.selectbox("Select Exam", list(ex_options.keys()) or ["No exams yet"])
                q_type = st.selectbox("Question Type", ["mcq", "blank", "programming"])
                q_text = st.text_area("Question Text")
                a = st.text_input("Choice A")
                b = st.text_input("Choice B")
                c = st.text_input("Choice C")
                d = st.text_input("Choice D")
                h_text = st.text_input("Hint")
                c_ans_text = st.text_input("Correct Answer")
                if st.form_submit_button("➕ Add Question"):
                    if sel_ex in ex_options and q_text.strip():
                        supabase.table("questions").insert({
                            "exam_id": ex_options[sel_ex], "question": q_text, "type": q_type,
                            "option_a": a, "option_b": b, "option_c": c, "option_d": d,
                            "correct_answer": c_ans_text if q_type != "programming" else "Manual Review Required",
                            "hint": h_text
                        }).execute()
                        st.success("Question Added!")
                        st.rerun()

        with ex_tab4:
            st.subheader("📁 Bulk Upload Questions (CSV)")
            exams = supabase.table("exams").select("id, title").execute()
            exam_options = {ex["title"]: ex["id"] for ex in exams.data} if exams.data else {}
            if exam_options:
                selected_exam = st.selectbox("Select Exam:", list(exam_options.keys()))
                exam_id = exam_options[selected_exam]
                uploaded_file = st.file_uploader("Upload CSV", type=["csv"])
                if uploaded_file is not None:
                    import pandas as pd
                    df = pd.read_csv(uploaded_file)
                    st.write("Preview:", df.head())
                    if st.button("Upload to DB"):
                        try:
                            for _, row in df.iterrows():
                                supabase.table("questions").insert({
                                    "exam_id": exam_id,
                                    "question": row["question"],
                                    "type": row["type"],
                                    "option_a": row.get("option_a", ""),
                                    "option_b": row.get("option_b", ""),
                                    "option_c": row.get("option_c", ""),
                                    "option_d": row.get("option_d", ""),
                                    "correct_answer": row.get("correct_answer", ""),
                                    "hint": row.get("hint", "")
                                }).execute()
                            st.success(f"Successfully uploaded {len(df)} questions!")
                        except Exception as e:
                            st.error(f"Upload Error: {e}")
            else:
                st.warning("ముందుగా ఒక Exam create చేయండి.")

        with ex_tab5:
            st.subheader("🤖 AI Question Generator")
            lesson_text = st.text_area("Paste your Lesson Content here:")
            if st.button("✨ Generate Questions"):
                if not lesson_text.strip():
                    st.warning("దయచేసి పాఠాన్ని పైన పేస్ట్ చేయండి!")
                else:
                    try:
                        prompt = (
                            "Convert this text into 5 MCQ questions in JSON format. "
                            "Return ONLY a JSON array. Each item: question, option_a, option_b, "
                            f"option_c, option_d, correct_answer. Text: {lesson_text}"
                        )
                        model = genai.GenerativeModel(model_name="gemini-1.5-pro")
                        response = model.generate_content(prompt)
                        st.subheader("Generated Questions:")
                        st.write(response.text)
                    except Exception as e:
                        st.error(f"AI Error: {e}")

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

                st.write(f"### Questions in **{selected_exam_title}** ({len(current_questions)} total)")
                if not current_questions:
                    st.warning("No questions in this exam.")
                else:
                    for idx, q in enumerate(current_questions):
                        with st.container(border=True):
                            col_q1, col_q2 = st.columns([5, 1])
                            with col_q1:
                                st.markdown(f"**Q{idx+1}. {q['question']}** `({str(q['type']).upper()})`")
                                if q["type"] == "mcq":
                                    st.caption(f"A: {q['option_a']} | B: {q['option_b']} | C: {q['option_c']} | D: {q['option_d']}")
                                st.caption(f"🎯 Answer: {q['correct_answer']} | 💡 Hint: {q['hint']}")
                            with col_q2:
                                if st.button("🗑️ Delete", key=f"del_q_{q['id']}", type="secondary", use_container_width=True):
                                    supabase.table("questions").delete().eq("id", q["id"]).execute()
                                    st.success(f"Q{idx+1} Deleted!")
                                    st.rerun()

                st.divider()
                st.markdown("#### ➕ Quick Add Question")
                with st.form("quick_add_question_form", clear_on_submit=True):
                    q_type_new = st.selectbox("Type", ["mcq", "blank", "programming"], key="new_q_type")
                    q_text_new = st.text_area("Question Text", key="new_q_text")
                    col_opts1, col_opts2 = st.columns(2)
                    with col_opts1:
                        a_new = st.text_input("Option A", key="new_a")
                        b_new = st.text_input("Option B", key="new_b")
                    with col_opts2:
                        c_new = st.text_input("Option C", key="new_c")
                        d_new = st.text_input("Option D", key="new_d")
                    h_text_new = st.text_input("Hint", key="new_hint")
                    c_ans_new = st.text_input("Correct Answer", key="new_ans")
                    if st.form_submit_button("🚀 Add Question"):
                        if q_text_new.strip():
                            supabase.table("questions").insert({
                                "exam_id": selected_exam_id, "question": q_text_new, "type": q_type_new,
                                "option_a": a_new, "option_b": b_new, "option_c": c_new, "option_d": d_new,
                                "correct_answer": c_ans_new if q_type_new != "programming" else "Manual Review Required",
                                "hint": h_text_new
                            }).execute()
                            st.success("Question Added!")
                            st.rerun()
                        else:
                            st.error("Question text cannot be empty!")

    elif menu == "📊 Student Results & Ranks":
        r_tab1, r_tab2, r_tab3, r_tab4 = st.tabs([
            "🏆 Leaderboards", "📝 Manual Evaluation", "📜 Score Summary", "🔄 Re-Exam Requests"
        ])

        with r_tab1:
            st.title("🏆 Leaderboard")
            exams = supabase.table("exams").select("*").execute().data
            if exams:
                exam_titles = [e["title"] for e in exams]
                sel_ex_lb = st.selectbox("Select Exam", exam_titles)
                target_ex = next((e for e in exams if e["title"] == sel_ex_lb), None)
                if target_ex:
                    board = get_exam_leaderboard(target_ex["id"])
                    if board:
                        for rank, st_row in enumerate(board):
                            medal = "🥇" if rank == 0 else "🥈" if rank == 1 else "🥉" if rank == 2 else f"{rank+1}."
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
                                st.code(att.get("submitted_answers", "# No code submitted."), language="python")
                            with col_s2:
                                new_score = st.number_input("Score", min_value=0, max_value=100,
                                                             value=int(att["score"]), key=f"score_in_{att['id']}")
                                if st.button("💾 Save", key=f"btn_score_{att['id']}", type="primary", use_container_width=True):
                                    supabase.table("exam_attempts").update({"score": new_score}).eq("id", att["id"]).execute()
                                    st.success("Score Saved!")
                                    st.rerun()

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
                        st.markdown(f"👤 **{u_prof[0]['name']}** completed **{e_prof[0]['title']}** | Score: **{att['score']}**")
                        st.divider()


        with r_tab4:
            st.title("🔄 Re-Exam Requests")
            requests_data = supabase.table("exam_retake_requests").select("*")                 .eq("status", "pending").order("requested_at", desc=True).execute().data

            if not requests_data:
                st.info("ఇప్పుడు pending requests లేవు.")
            else:
                for req in requests_data:
                    u_info = supabase.table("users").select("name, email").eq("id", req["user_id"]).execute().data
                    e_info = supabase.table("exams").select("title").eq("id", req["exam_id"]).execute().data
                    if u_info and e_info:
                        with st.container(border=True):
                            col1, col2, col3 = st.columns([4, 1, 1])
                            with col1:
                                st.markdown(f"**👤 {u_info[0]['name']}** ({u_info[0]['email']})")
                                st.caption(f"📝 Exam: {e_info[0]['title']} | Requested: {req['requested_at'][:10]}")
                            with col2:
                                if st.button("✅ Approve", key=f"apr_{req['id']}", type="primary", use_container_width=True):
                                    supabase.table("exam_retake_requests").update({
                                        "status": "approved",
                                        "reviewed_at": "now()"
                                    }).eq("id", req["id"]).execute()
                                    st.success("Approved!")
                                    st.rerun()
                            with col3:
                                if st.button("❌ Reject", key=f"rej_{req['id']}", use_container_width=True):
                                    supabase.table("exam_retake_requests").update({
                                        "status": "rejected",
                                        "reviewed_at": "now()"
                                    }).eq("id", req["id"]).execute()
                                    st.warning("Rejected!")
                                    st.rerun()


    elif menu == "💬 Group Chat":
        group_chat()

# =========================
# GROUP CHAT
# =========================
def group_chat():
    st.title("💬 Group Chat")

    # Messages fetch — latest 50
    messages = supabase.table("messages").select("*")         .order("created_at", desc=False).limit(50).execute().data

    # Chat container
    chat_container = st.container(height=450)
    with chat_container:
        if not messages:
            st.info("ఇంకా messages లేవు. మొదటిగా message చేయండి! 👋")
        for msg in messages:
            is_me = msg["user_id"] == st.session_state.user_id
            if is_me:
                # Right side — own message
                col1, col2 = st.columns([2, 5])
                with col2:
                    st.markdown(
                        f"""<div style='background:#dcf8c6;padding:10px 14px;border-radius:12px 12px 0px 12px;margin:4px 0;'>
                        <small style='color:#555;font-weight:600'>You</small><br>
                        {msg['message']}
                        <br><small style='color:#999;font-size:10px'>{str(msg.get('created_at',''))[:16]}</small>
                        </div>""",
                        unsafe_allow_html=True
                    )
            else:
                # Left side — others message
                col1, col2 = st.columns([5, 2])
                with col1:
                    st.markdown(
                        f"""<div style='background:#f1f0f0;padding:10px 14px;border-radius:12px 12px 12px 0px;margin:4px 0;'>
                        <small style='color:#0084ff;font-weight:600'>{msg.get('user_name','Unknown')}</small><br>
                        {msg['message']}
                        <br><small style='color:#999;font-size:10px'>{str(msg.get('created_at',''))[:16]}</small>
                        </div>""",
                        unsafe_allow_html=True
                    )

    st.divider()

    # Message input
    col_input, col_btn = st.columns([6, 1])
    with col_input:
        new_msg = st.text_input("Message రాయండి...", key="chat_input", label_visibility="collapsed")
    with col_btn:
        send = st.button("📤 Send", use_container_width=True, type="primary")

    if send and new_msg.strip():
        # user name తీసుకోవాలి
        uinfo = supabase.table("users").select("name").eq("id", st.session_state.user_id).execute().data
        uname = uinfo[0]["name"] if uinfo else "Unknown"
        supabase.table("messages").insert({
            "user_id": str(st.session_state.user_id),
            "user_name": uname,
            "message": new_msg.strip()
        }).execute()
        st.rerun()

# =========================
# USER DASHBOARD
# =========================
def user_dashboard(preview_mode=False):
    if not preview_mode:
        st.sidebar.title("User Workspace")
        if st.sidebar.button("🚪 Logout", use_container_width=True):
            for key in defaults:
                st.session_state[key] = defaults[key]
            st.rerun()
        st.sidebar.divider()
        user_page = st.sidebar.radio(
            "Menu",
            ["📚 My Classes", "💬 Group Chat"],
            label_visibility="collapsed"
        )
    else:
        st.info("👁️ ఇది Student Preview Mode — student కి కనపడే view చూస్తున్నారు.")
        user_page = "📚 My Classes"

    if user_page == "💬 Group Chat":
        group_chat()
        return

    modules = supabase.table("modules").select("*").execute().data

    # completed_ids ని session_state లో cache చేయడం — rerun లేకుండా local update చేయడానికి
    if st.session_state.completed_ids is None:
        all_completions = supabase.table("class_completions").select("class_id") \
            .eq("user_id", st.session_state.user_id).execute().data
        st.session_state.completed_ids = {str(c["class_id"]) for c in all_completions}
    completed_ids = st.session_state.completed_ids
    for module in modules:
        # Module లో total classes count చేయడం
        module_submodules = supabase.table("submodules").select("id").eq("module_id", module["id"]).execute().data
        sub_ids = [s["id"] for s in module_submodules]
        module_total = 0
        module_done = 0
        for sid in sub_ids:
            cls_list = supabase.table("classes").select("id").eq("submodule_id", sid).execute().data
            module_total += len(cls_list)
            module_done += sum(1 for c in cls_list if str(c["id"]) in completed_ids)

        pct = int((module_done / module_total * 100)) if module_total > 0 else 0
        expander_label = f"{module['title']}  —  {module_done}/{module_total} classes  ({pct}%)"

        with st.expander(expander_label):
            if module_total > 0:
                st.progress(pct / 100, text=f"Module Progress: {pct}% complete")
            submodules = supabase.table("submodules").select("*").eq("module_id", module["id"]).execute().data
            for sub in submodules:
                # Submodule progress
                sub_classes = supabase.table("classes").select("id").eq("submodule_id", sub["id"]).execute().data
                sub_total = len(sub_classes)
                sub_done = sum(1 for c in sub_classes if str(c["id"]) in completed_ids)
                sub_pct = int((sub_done / sub_total * 100)) if sub_total > 0 else 0

                st.subheader(f"{sub['title']}  ✅ {sub_done}/{sub_total}")
                if sub_total > 0:
                    st.progress(sub_pct / 100)
                classes = supabase.table("classes").select("*").eq("submodule_id", sub["id"]).execute().data
                for cls in classes:
                    is_done = str(cls.get("id")) in completed_ids
                    cls_label = f"✅ {cls['title']}" if is_done else f"🔲 {cls['title']}"
                    st.markdown(f"### {cls_label}")
                    col_link1, col_link2, col_link3 = st.columns(3)
                    with col_link1:
                        if cls.get("class_link"):
                            st.link_button("Join Class", cls["class_link"], use_container_width=True)
                    with col_link2:
                        if cls.get("recorded_video"):
                            st.link_button("Watch Video", cls["recorded_video"], use_container_width=True)
                    with col_link3:
                        if cls.get("notes_pdf"):
                            st.link_button("Notes PDF", cls["notes_pdf"], use_container_width=True)

                    # FIX 6: Class completion logic - clean indentation
                    class_id = cls.get("id")
                    if class_id:
                        try:
                            cid = int(class_id)
                        except (ValueError, TypeError):
                            cid = str(class_id)

                        # rerun లేకుండా — session_state లో check చేయడం
                        if str(class_id) in completed_ids:
                            st.success("✅ మీరు ఈ క్లాస్ పూర్తి చేశారు!")
                        else:
                            if st.button("✔️ Mark as Completed", key=f"btn_done_{cls['id']}"):
                                try:
                                    supabase.table("class_completions").insert({
                                        "user_id": str(st.session_state.user_id),
                                        "class_id": cid
                                    }).execute()
                                    # rerun లేకుండా local state update
                                    st.session_state.completed_ids.add(str(class_id))
                                    st.success("✅ క్లాస్ కంప్లీట్ అయ్యింది!")
                                except Exception as e:
                                    st.error(f"Insert Error: {e}")

                    # Exams for this class
                    exams = supabase.table("exams").select("*").eq("class_id", cls["id"]).execute().data
                    for exam in exams:
                        if not exam["enabled"]:
                            continue
                        exam_dur = exam.get("duration_mins", 30)
                        st.write(f"📝 **Exam: {exam['title']}** ({exam_dur} Mins)")
                        btn_col, lb_col = st.columns([2, 2])

                        with lb_col:
                            board = get_exam_leaderboard(exam["id"])
                            if board:
                                st.markdown("🏆 **Top Performers:**")
                                for idx, student in enumerate(board[:3]):
                                    medal = "🥇" if idx == 0 else "🥈" if idx == 1 else "🥉"
                                    st.caption(f"{medal} {student['Name']} — Score: {student['Score']}")
                            else:
                                st.caption("Be the first to top this exam! 🚀")

                        with btn_col:
                            check_attempt = supabase.table("exam_attempts").select("*") \
                                .eq("user_id", st.session_state.user_id) \
                                .eq("exam_id", exam["id"]).execute().data

                            if check_attempt:
                                # అన్ని attempts scores చూపించాలి
                                # అన్ని attempts scores చూపించాలి
                                q_count = supabase.table("questions").select("id").eq("exam_id", exam["id"]).execute().data
                                total_q = len(q_count)
                                st.markdown("**📊 మీ Attempts:**")
                                for idx, att in enumerate(check_attempt):
                                    attempt_num = idx + 1
                                    st.caption(f"Attempt {attempt_num}: **{att['score']}/{total_q}**")
                                # Latest attempt తో Show Answers
                                if st.button("🔍 Show Answers", key=f"view_{exam['id']}", use_container_width=True):
                                    st.session_state.exam_id = exam["id"]
                                    st.session_state.exam_title = exam["title"]
                                    st.session_state.start_exam = True
                                    st.session_state.exam_submitted = True
                                    st.session_state.current_questions = supabase.table("questions").select("*").eq("exam_id", exam["id"]).execute().data
                                    st.rerun()

                                # Re-exam request status check
                                retake_req = supabase.table("exam_retake_requests").select("*")                                     .eq("user_id", st.session_state.user_id)                                     .eq("exam_id", exam["id"])                                     .order("requested_at", desc=True).limit(1).execute().data

                                if retake_req:
                                    status = retake_req[0]["status"]
                                    if status == "pending":
                                        st.warning("⏳ Re-exam request pending... Admin approval కోసం వేచి ఉండండి.")
                                    elif status == "rejected":
                                        st.error("❌ Re-exam request rejected చేయబడింది.")
                                        if st.button("🔄 మళ్ళీ Request పంపు", key=f"retry_req_{exam['id']}", use_container_width=True):
                                            supabase.table("exam_retake_requests").insert({
                                                "user_id": st.session_state.user_id,
                                                "exam_id": exam["id"],
                                                "status": "pending"
                                            }).execute()
                                            st.success("Request పంపబడింది!")
                                            st.rerun()
                                    elif status == "approved":
                                        st.success("✅ Re-exam approved! మీరు మళ్ళీ రాయవచ్చు.")
                                        has_password = exam.get("password") is not None and str(exam["password"]).strip() != ""
                                        entered_pwd = ""
                                        if has_password:
                                            entered_pwd = st.text_input(
                                                f"Access Code for {exam['title']}", type="password",
                                                key=f"repwd_{exam['id']}"
                                            )
                                        if st.button("📝 Re-Exam Start చేయండి", key=f"rebtn_{exam['id']}", use_container_width=True, type="primary"):
                                            if has_password and entered_pwd.strip() != str(exam["password"]).strip():
                                                st.error("Wrong Password!")
                                            else:
                                                supabase.table("exam_retake_requests").update({"status": "used"})                                                     .eq("id", retake_req[0]["id"]).execute()
                                                q_data = supabase.table("questions").select("*").eq("exam_id", exam["id"]).execute().data
                                                st.session_state.exam_id = exam["id"]
                                                st.session_state.exam_title = exam["title"]
                                                st.session_state.start_exam = True
                                                st.session_state.exam_submitted = False
                                                st.session_state.answers = {}
                                                st.session_state.question_index = 0
                                                st.session_state.current_questions = q_data
                                                st.session_state.exam_end_time = time.time() + (int(exam_dur) * 60)
                                                st.rerun()
                                else:
                                    if st.button("🔄 Try Again Request", key=f"req_{exam['id']}", use_container_width=True):
                                        supabase.table("exam_retake_requests").insert({
                                            "user_id": st.session_state.user_id,
                                            "exam_id": exam["id"],
                                            "status": "pending"
                                        }).execute()
                                        st.success("✅ Request పంపబడింది! Admin approve చేస్తే మళ్ళీ రాయవచ్చు.")
                                        st.rerun()
                            else:
                                has_password = exam.get("password") is not None and str(exam["password"]).strip() != ""
                                entered_pwd = ""
                                if has_password:
                                    entered_pwd = st.text_input(
                                        f"Access Code for {exam['title']}", type="password",
                                        key=f"pwd_{exam['id']}"
                                    )
                                if st.button("📝 Start Exam", key=f"btn_{exam['id']}", use_container_width=True):
                                    if has_password and entered_pwd.strip() != str(exam["password"]).strip():
                                        st.error("Wrong Password!")
                                    else:
                                        q_data = supabase.table("questions").select("*").eq("exam_id", exam["id"]).execute().data
                                        st.session_state.exam_id = exam["id"]
                                        st.session_state.exam_title = exam["title"]
                                        st.session_state.start_exam = True
                                        st.session_state.exam_submitted = False
                                        st.session_state.answers = {}
                                        st.session_state.question_index = 0
                                        st.session_state.current_questions = q_data
                                        st.session_state.exam_end_time = time.time() + (int(exam_dur) * 60)
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
        if st.button("Go Back"):
            st.session_state.start_exam = False
            st.rerun()
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
                user_val = st.session_state.answers.get(q["id"], "")
                if q["type"] != "programming":
                    if str(user_val).strip().lower() == str(q["correct_answer"]).strip().lower():
                        final_score += 1
            supabase.table("exam_attempts").insert({
                "id": attempt_uuid, "user_id": st.session_state.user_id,
                "exam_id": st.session_state.exam_id, "score": final_score
            }).execute()
            for q in questions:
                user_val = st.session_state.answers.get(q["id"], "")
                supabase.table("user_answers").insert({
                    "attempt_id": attempt_uuid, "question_id": q["id"], "answer": user_val
                }).execute()
            st.session_state.exam_submitted = True
            st.rerun()

    if st.session_state.exam_submitted:
        st.title(f"📊 Results: {st.session_state.exam_title}")
        db_attempt = supabase.table("exam_attempts").select("*") \
            .eq("user_id", st.session_state.user_id) \
            .eq("exam_id", st.session_state.exam_id).execute().data

        if db_attempt:
            # అన్ని attempts చూపించాలి
            st.markdown("### 📊 మీ అన్ని Attempts")
            for idx, att in enumerate(reversed(db_attempt)):
                attempt_num = idx + 1
                icon = "🏆" if idx == len(db_attempt) - 1 else f"#{attempt_num}"
                st.info(f"{icon} Attempt {attempt_num}: **{att['score']}/{total_questions}**")

            st.divider()
            # Latest attempt answers చూపించాలి
            latest = db_attempt[0]
            st.success(f"🎉 Latest Score: {latest['score']}/{total_questions}")
            db_answers = supabase.table("user_answers").select("*").eq("attempt_id", latest["id"]).execute().data
            ans_map = {a["question_id"]: a["answer"] for a in db_answers}

            exam_data = supabase.table("exams").select("*").eq("id", st.session_state.exam_id).execute().data
            if exam_data and exam_data[0]["show_answers"]:
                st.subheader("📚 Review Sheet")
                for i, q in enumerate(questions):
                    st.markdown(f"**Q{i+1}:** {q['question']}")
                    u_ans = ans_map.get(q["id"], "Not Answered")
                    c_ans = q["correct_answer"]
                    if q["type"] == "programming":
                        # FIX 7: Programming review - show submitted code only (Judge0 already handled above)
                        st.code(u_ans, language="java")
                    else:
                        if str(u_ans).strip().lower() == str(c_ans).strip().lower():
                            st.success(f"✅ Your answer: {u_ans}")
                        else:
                            st.error(f"❌ Your answer: {u_ans} | Correct: {c_ans}")

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
            # JavaScript తో client-side countdown — page reload అవ్వదు
            st.components.v1.html(f"""
                <div id="timer" style="
                    font-size: 2rem;
                    font-weight: 600;
                    text-align: center;
                    padding: 12px;
                    border-radius: 8px;
                    background: {'#fff3cd' if remaining_time < 300 else '#e8f4fd'};
                    color: {'#856404' if remaining_time < 300 else '#0c63e4'};
                    border: 1px solid {'#ffc107' if remaining_time < 300 else '#b6d4fe'};
                ">⏱️ <span id="countdown">{mins:02d}:{secs:02d}</span></div>
                <script>
                    var total = {remaining_time};
                    function tick() {{
                        if (total <= 0) {{
                            document.getElementById('countdown').innerText = "00:00";
                            window.parent.postMessage({{type: 'streamlit:setComponentValue', value: true}}, '*');
                            return;
                        }}
                        total--;
                        var m = Math.floor(total / 60).toString().padStart(2, '0');
                        var s = (total % 60).toString().padStart(2, '0');
                        document.getElementById('countdown').innerText = m + ':' + s;
                        var el = document.getElementById('timer');
                        if (total < 300) {{
                            el.style.background = '#fff3cd';
                            el.style.color = '#856404';
                            el.style.border = '1px solid #ffc107';
                        }}
                    }}
                    setInterval(tick, 1000);
                </script>
            """, height=80)
            st.divider()
            st.subheader("Questions")
            cols = st.columns(3)
            for i in range(total_questions):
                with cols[i % 3]:
                    q_id = questions[i]["id"]
                    label = f"🔵 {i+1}" if i == current else (
                        f"🟢 {i+1}" if q_id in st.session_state.answers and st.session_state.answers[q_id]
                        else f"🔴 {i+1}"
                    )
                    if st.button(label, key=f"qnav_{i}", use_container_width=True):
                        st.session_state.question_index = i
                        st.rerun()

        with left:
            st.subheader(f"Question {current+1}/{total_questions}")
            st.write(question["question"])
            stored_ans = st.session_state.answers.get(question["id"], "")

            if question["type"] == "mcq":
                opts = [question["option_a"], question["option_b"], question["option_c"], question["option_d"]]
                default_idx = opts.index(stored_ans) if stored_ans in opts else None
                answer = st.radio("Choose Answer", opts, index=default_idx, key=f"radio_{question['id']}")
            elif question["type"] == "blank":
                answer = st.text_input("Your Answer", value=stored_ans, key=f"text_{question['id']}")
            else:
                answer = st.text_area("Write your Code/Answer:", value=stored_ans, key=f"code_{question['id']}", height=250)

            if answer != stored_ans:
                st.session_state.answers[question["id"]] = answer

            nav_col1, nav_col2, submit_col = st.columns([1, 1, 2])
            with nav_col1:
                if st.button("⬅️ Previous", disabled=(current == 0), use_container_width=True):
                    st.session_state.question_index -= 1
                    st.rerun()
            with nav_col2:
                if st.button("Next ➡️", disabled=(current == total_questions - 1), use_container_width=True):
                    st.session_state.question_index += 1
                    st.rerun()
            with submit_col:
                if st.button("🚀 Submit Exam", type="primary", use_container_width=True):
                    final_score = 0
                    attempt_uuid = str(uuid.uuid4())
                    for q in questions:
                        user_val = st.session_state.answers.get(q["id"], "")
                        if q["type"] != "programming":
                            if str(user_val).strip().lower() == str(q["correct_answer"]).strip().lower():
                                final_score += 1
                    supabase.table("exam_attempts").insert({
                        "id": attempt_uuid, "user_id": st.session_state.user_id,
                        "exam_id": st.session_state.exam_id, "score": final_score
                    }).execute()
                    for q in questions:
                        user_val = st.session_state.answers.get(q["id"], "")
                        supabase.table("user_answers").insert({
                            "attempt_id": attempt_uuid, "question_id": q["id"], "answer": user_val
                        }).execute()
                    st.session_state.exam_submitted = True
                    st.rerun()

        # Timer ఇప్పుడు client-side JavaScript లో నడుస్తుంది
        # Time out అయినప్పుడు మాత్రమే rerun కావాలి
        if remaining_time <= 0:
            st.rerun()

# =========================
# MAIN ROUTING
# =========================
if not st.session_state.logged_in:
    # user_id_temp ఉంటే PIN screen చూపించాలి, లేకపోతే login
    if st.session_state.user_id_temp:
        pin_screen()
    else:
        login()
elif st.session_state.role == "admin":
    admin_dashboard()
elif st.session_state.start_exam:
    exam_workspace_view()
else:
    user_dashboard(preview_mode=False)
