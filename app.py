import os
os.system("pip install google-generativeai")
import streamlit as st
from supabase import create_client
import uuid
import time
import google.generativeai as genai
import json


supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(
    page_title="Advanced LMS Admin Portal",
    layout="wide"
)

# =========================
# SESSION STATES INITIALIZATION
# =========================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "role" not in st.session_state:
    st.session_state.role = ""
if "user_id" not in st.session_state:
    st.session_state.user_id = ""
if "question_index" not in st.session_state:
    st.session_state.question_index = 0
if "answers" not in st.session_state:
    st.session_state.answers = {}
if "start_exam" not in st.session_state:
    st.session_state.start_exam = False
if "exam_submitted" not in st.session_state:
    st.session_state.exam_submitted = False
if "exam_id" not in st.session_state:
    st.session_state.exam_id = ""
if "exam_title" not in st.session_state:
    st.session_state.exam_title = ""
if "exam_end_time" not in st.session_state:
    st.session_state.exam_end_time = 0.0
if "current_questions" not in st.session_state:
    st.session_state.current_questions = []

# =========================
# LOGIN FUNCTION
# =========================
def login():
    st.title("📚 LMS Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Login", type="primary", use_container_width=True):
        try:
            response = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            user = response.user
            user_data = supabase.table("users").select("*").eq("email", email).execute()

            if len(user_data.data) > 0:
                role = user_data.data[0]["role"]
                st.session_state.logged_in = True
                st.session_state.role = role
                st.session_state.user_id = user.id
                st.rerun()
        except Exception as e:
            st.error(str(e))

# =========================
# HELPER: FETCH LEADERBOARD DATA
# =========================
def get_exam_leaderboard(exam_id):
    try:
        attempts = supabase.table("exam_attempts").select("*").eq("exam_id", exam_id).execute().data
        leaderboard = []
        user_best_scores = {}
        for att in attempts:
            uid = att["user_id"]
            score = att["score"]
            if uid not in user_best_scores or score > user_best_scores[uid]:
                user_best_scores[uid] = score

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
        st.session_state.logged_in = False
        st.session_state.role = ""
        st.session_state.user_id = ""
        st.rerun()
        
    menu = st.sidebar.selectbox(
        "Navigation Control",
        ["🗂️ Manage Course Content", "📝 Manage Exams & Questions", "📊 Student Results & Ranks"]
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
            st.write("### Existing Modules (Edit / Delete Panel)")
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
                sel_mod = st.selectbox("Select Parent Module", list(mod_options.keys()))
                sub_name = st.text_input("Submodule Title")
                if st.form_submit_button("✨ Save Submodule"):
                    if sub_name.strip() and sel_mod:
                        supabase.table("submodules").insert({"module_id": mod_options[sel_mod], "title": sub_name}).execute()
                        st.success("Submodule Linked!")
                        st.rerun()

            st.divider()
            st.write("### Existing Submodules (Edit / Delete Panel)")
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
                    sel_sub = st.selectbox("Link to Submodule", list(sub_options.keys()))
                    c_title = st.text_input("Class Title")
                    c_link = st.text_input("Live Stream Link")
                    v_link = st.text_input("Recorded Video URL")
                    p_link = st.text_input("Notes PDF URL")
                    if st.form_submit_button("🚀 Deploy Class"):
                        supabase.table("classes").insert({
                            "submodule_id": sub_options[sel_sub], "title": c_title,
                            "class_link": c_link, "recorded_video": v_link, "notes_pdf": p_link
                        }).execute()
                        st.success("Class Data Broadcasted!")
                        st.rerun()

            st.divider()
            st.write("### Active Classes Directory")
            classes = supabase.table("classes").select("*").execute().data
            for cls in classes:
                with st.expander(f"🖥️ {cls['title']} Settings"):
                    ec_title = st.text_input("Title", value=cls["title"], key=f"ct_{cls['id']}")
                    ec_link = st.text_input("Live Link", value=cls["class_link"], key=f"cl_{cls['id']}")
                    ev_link = st.text_input("Video Link", value=cls["recorded_video"], key=f"cv_{cls['id']}")
                    ep_link = st.text_input("PDF Link", value=cls["notes_pdf"], key=f"cp_{cls['id']}")
                    
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("💾 Save Changes", key=f"cu_{cls['id']}", type="primary", use_container_width=True):
                            supabase.table("classes").update({
                                "title": ec_title, "class_link": ec_link, "recorded_video": ev_link, "notes_pdf": ep_link
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
                sel_cls = st.selectbox("Link with Lesson Class", list(cls_options.keys()))
                e_title = st.text_input("Exam Sheet Name")
                e_duration = st.number_input("Exam Duration (Minutes)", min_value=1, max_value=180, value=30)
                e_pwd = st.text_input("Exam Password Entry (Optional)", type="password")
                c_en = st.checkbox("Turn On Exam (Visible to Students immediately)", value=True)
                c_ans = st.checkbox("Enable Answers Visibility Sheet")
                if st.form_submit_button("📋 Generate Exam Layout"):
                    supabase.table("exams").insert({
                        "class_id": cls_options[sel_cls], 
                        "title": e_title, 
                        "duration_mins": int(e_duration),
                        "password": e_pwd if e_pwd.strip() != "" else None,
                        "enabled": c_en, 
                        "show_answers": c_ans
                    }).execute()
                    st.success("Exam Created with Password Control!")
                    st.rerun()

            st.divider()
            st.write("### ⚙️ Live Exam Controls & Password Viewer")
            exams_all = supabase.table("exams").select("*").execute().data
            
            for ex in exams_all:
                with st.container(border=True):
                    st.markdown(f"#### 📄 Exam Sheet: **{ex['title']}**")
                    
                    col_e1, col_e2, col_e3 = st.columns([2, 2, 2])
                    with col_e1:
                        current_dur = ex.get("duration_mins", 30)
                        updated_dur = st.number_input("Edit Duration (Mins)", min_value=1, max_value=180, value=int(current_dur), key=f"dur_{ex['id']}")
                    with col_e2:
                        current_pwd = ex.get("password", "")
                        current_pwd_str = str(current_pwd) if current_pwd else ""
                        updated_pwd = st.text_input("Exam Password (View/Edit)", value=current_pwd_str, key=f"pwd_ed_{ex['id']}")
                    with col_e3:
                        st.write("") 
                        t_active = st.toggle("Active (Visible)", value=ex["enabled"], key=f"tog_en_{ex['id']}")
                        t_ans = st.toggle("Show Answer Key", value=ex["show_answers"], key=f"tog_ans_{ex['id']}")
                    
                    col_btn1, col_btn2 = st.columns([1, 1])
                    with col_btn1:
                        if st.button("💾 Save Settings & Password", key=f"up_ex_{ex['id']}", type="primary", use_container_width=True):
                            pwd_final = updated_pwd.strip() if updated_pwd.strip() != "" else None
                            supabase.table("exams").update({
                                "duration_mins": int(updated_dur),
                                "password": pwd_final,
                                "enabled": t_active, 
                                "show_answers": t_ans
                            }).eq("id", ex["id"]).execute()
                            st.success("Exam Records and Password Updated!")
                            st.rerun()
                    with col_btn2:
                        if st.button("🗑️ Wipe Exam Paper", key=f"del_ex_{ex['id']}", type="secondary", use_container_width=True):
                            supabase.table("exams").delete().eq("id", ex["id"]).execute()
                            st.warning("Exam Purged!")
                            st.rerun()

        with ex_tab2:
            st.subheader("Add Questions to Active Test Bank")
            exams_q = supabase.table("exams").select("*").execute().data
            ex_options = {e["title"]: e["id"] for e in exams_q} if exams_q else {}
            
            with st.form("add_question_form", clear_on_submit=True):
                sel_ex = st.selectbox("Select Target Exam Sheet", list(ex_options.keys()))
                q_type = st.selectbox("Choose Response Type", ["mcq", "blank", "programming"])
                q_text = st.text_area("Question/Task Input Paragraph")
                
                a = st.text_input("Choice A (Leave blank if Blank or Programming)")
                b = st.text_input("Choice B")
                c = st.text_input("Choice C")
                d = st.text_input("Choice D")
                
                h_text = st.text_input("Hint Description")
                c_ans_text = st.text_input("Literal Correct Answer String Matching Key (For MCQ/Blank)")
                
                if st.form_submit_button("➕ Add Question Row"):
                    supabase.table("questions").insert({
                        "exam_id": ex_options[sel_ex], "question": q_text, "type": q_type,
                        "option_a": a, "option_b": b, "option_c": c, "option_d": d,
                        "correct_answer": c_ans_text if q_type != "programming" else "Manual Review Required", 
                        "hint": h_text
                    }).execute()
                    st.success("Question Added to Database Queue!")
                    st.rerun()
        with ex_tab4:
            st.subheader("📁 Bulk Upload Questions (CSV)")
            st.write("CSV ఫార్మాట్: question, type, option_a, option_b, option_c, option_d, correct_answer, hint")
            
            uploaded_file = st.file_uploader("Upload CSV File", type="csv")
            if uploaded_file:
                df = pd.read_csv(uploaded_file)
                st.write("Preview:", df.head())
                
                exam_list = supabase.table("exams").select("id, title").execute().data
                exam_map = {e["title"]: e["id"] for e in exam_list}
                target_exam = st.selectbox("Select Exam to Link", list(exam_map.keys()))
                
                if st.button("🚀 Upload All Questions"):
                    data_to_insert = []
                    for _, row in df.iterrows():
                        data_to_insert.append({
                            "exam_id": exam_map[target_exam],
                            "question": row["question"],
                            "type": row["type"],
                            "option_a": row["option_a"],
                            "option_b": row["option_b"],
                            "option_c": row["option_c"],
                            "option_d": row["option_d"],
                            "correct_answer": row["correct_answer"],
                            "hint": row["hint"]
                        })
                    supabase.table("questions").insert(data_to_insert).execute()
                    st.success("All questions injected successfully!")
            
        with ex_tab5:
            st.subheader("🤖 AI Question Generator")
            lesson_text = st.text_area("Paste your Lesson Content here:")
            
            if st.button("✨ Generate Questions"):
                model = genai.GenerativeModel('gemini-1.5-flash')
                prompt = f"Convert this text into 5 MCQ questions in JSON format: {lesson_text}. Fields needed: question, option_a, option_b, option_c, option_d, correct_answer, hint"
                
                response = model.generate_content(prompt)
                # ఇక్కడ response ని json.loads() ద్వారా పార్స్ చేసి డేటాబేస్ కి పంపవచ్చు
                st.json(response.text)
                st.info("Copy the JSON and upload it or use a script to push to Supabase.")
            
        with ex_tab3:
            st.subheader("🔍 Review and Edit Existing Exam Papers")
            exams_all_edit = supabase.table("exams").select("*").execute().data
            
            if not exams_all_edit:
                st.info("No exams created yet.")
            else:
                exam_edit_options = {ex["title"]: ex["id"] for ex in exams_all_edit}
                selected_exam_title = st.selectbox("Choose Exam Paper to Review", list(exam_edit_options.keys()))
                selected_exam_id = exam_edit_options[selected_exam_title]
                
                current_questions = supabase.table("questions").select("*").eq("exam_id", selected_exam_id).execute().data
                
                st.write(f"### Questions in **{selected_exam_title}** ({len(current_questions)} total)")
                
                if not current_questions:
                    st.warning("This exam paper currently has no questions.")
                else:
                    for idx, q in enumerate(current_questions):
                        with st.container(border=True):
                            col_q1, col_q2 = st.columns([5, 1])
                            with col_q1:
                                st.markdown(f"**Q{idx+1}. {q['question']}** `({str(q['type']).upper()})`")
                                if q["type"] == "mcq":
                                    st.caption(f"A: {q['option_a']} | B: {q['option_b']} | C: {q['option_c']} | D: {q['option_d']}")
                                st.caption(f"🎯 **Correct Answer:** {q['correct_answer']} | 💡 **Hint:** {q['hint']}")
                            with col_q2:
                                if st.button("🗑️ Delete", key=f"del_q_{q['id']}", type="secondary", use_container_width=True):
                                    supabase.table("questions").delete().eq("id", q["id"]).execute()
                                    st.success(f"Question {idx+1} Deleted!")
                                    st.rerun()
                
                st.divider()
                st.markdown("#### ➕ Add a Missing Question to this Paper")
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
                    c_ans_new = st.text_input("Correct Answer Key", key="new_ans")
                    
                    if st.form_submit_button("🚀 Add Question Instantly"):
                        if q_text_new.strip():
                            supabase.table("questions").insert({
                                "exam_id": selected_exam_id, "question": q_text_new, "type": q_type_new,
                                "option_a": a_new, "option_b": b_new, "option_c": c_new, "option_d": d_new,
                                "correct_answer": c_ans_new if q_type_new != "programming" else "Manual Review Required", 
                                "hint": h_text_new
                            }).execute()
                            st.success("New question injected into this paper!")
                            st.rerun()
                        else:
                            st.error("Question text cannot be empty!")

    elif menu == "📊 Student Results & Ranks":
        r_tab1, r_tab2, r_tab3 = st.tabs(["🏆 Live Dynamic Leaderboards", "📝 Manual Evaluation (Code/Text)", "📜 Individual Score Summary"])
        
        with r_tab1:
            st.title("🏆 Leaderboard Sorting Panel")
            exams = supabase.table("exams").select("*").execute().data
            if exams:
                exam_titles = [e["title"] for e in exams]
                sel_ex_lb = st.selectbox("Select Target Exam to Sort Rankings", exam_titles)
                target_ex = next((e for e in exams if e["title"] == sel_ex_lb), None)
                
                if target_ex:
                    board = get_exam_leaderboard(target_ex["id"])
                    if board:
                        for rank, st_row in enumerate(board):
                            medal = "🥇" if rank == 0 else "🥈" if rank == 1 else "🥉" if rank == 2 else f" {rank+1}."
                            st.write(f"{medal} **{st_row['Name']}** ({st_row['Email']}) — Score Result: **{st_row['Score']}**")
                    else:
                        st.info("No attempts recorded for this layout test sheet.")
                        
        with r_tab2:
            st.title("📝 Manual Code & Essay Evaluator")
            attempts_to_eval = supabase.table("exam_attempts").select("*").execute().data
            
            if not attempts_to_eval:
                st.info("No student submissions available for code review.")
            else:
                for att in attempts_to_eval:
                    u_data = supabase.table("users").select("*").eq("id", att["user_id"]).execute().data
                    e_data = supabase.table("exams").select("*").eq("id", att["exam_id"]).execute().data
                    
                    if u_data and e_data:
                        with st.container(border=True):
                            col_s1, col_s2 = st.columns([3, 1])
                            with col_s1:
                                st.markdown(f"##### 👤 **Student:** {u_data[0]['name']} | 🎯 **Exam:** {e_data[0]['title']}")
                                st.caption("💻 Submitted Answer / Programming Code:")
                                st.code(att.get("submitted_answers", "# No code answer text submitted."), language="python")
                            with col_s2:
                                st.markdown("##### 🔢 Score Panel")
                                new_score = st.number_input("Set Score", min_value=0, max_value=100, value=int(att["score"]), key=f"score_in_{att['id']}")
                                if st.button("💾 Save Score", key=f"btn_score_{att['id']}", type="primary", use_container_width=True):
                                    supabase.table("exam_attempts").update({"score": new_score}).eq("id", att["id"]).execute()
                                    st.success("Score Saved!")
                                    st.rerun()

        with r_tab3:
            st.title("Raw Student Attempts Review Logger")
            attempts = supabase.table("exam_attempts").select("*").execute().data
            if len(attempts) == 0:
                st.warning("Zero user submissions reported.")
            else:
                for att in attempts:
                    u_prof = supabase.table("users").select("*").eq("id", att["user_id"]).execute().data
                    e_prof = supabase.table("exams").select("*").eq("id", att["exam_id"]).execute().data
                    if u_prof and e_prof:
                        st.markdown(f"👤 **{u_prof[0]['name']}** completed **{e_prof[0]['title']}** | Earned Score: **{att['score']}**")
                        st.divider()

# =========================
# USER DASHBOARD
# =========================
def user_dashboard():
    st.sidebar.title("User Workspace Panel")
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.role = ""
        st.session_state.user_id = ""
        st.rerun()

    modules = supabase.table("modules").select("*").execute().data

    for module in modules:
        with st.expander(module["title"]):
            submodules = supabase.table("submodules").select("*").eq("module_id", module["id"]).execute().data
            for sub in submodules:
                st.subheader(sub["title"])
                classes = supabase.table("classes").select("*").eq("submodule_id", sub["id"]).execute().data
                for cls in classes:
                    st.markdown(f"### {cls['title']}")
                    col_link1, col_link2, col_link3 = st.columns(3)
                    with col_link1:
                        st.link_button("Join Class", cls["class_link"], use_container_width=True)
                    with col_link2:
                        st.link_button("Watch Video", cls["recorded_video"], use_container_width=True)
                    with col_link3:
                        st.link_button("Notes PDF", cls["notes_pdf"], use_container_width=True)

                    exams = supabase.table("exams").select("*").eq("class_id", cls["id"]).execute().data
                    for exam in exams:
                        if exam["enabled"]:
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
                                check_attempt = supabase.table("exam_attempts").select("*")\
                                    .eq("user_id", st.session_state.user_id)\
                                    .eq("exam_id", exam["id"]).execute().data
                                
                                if len(check_attempt) > 0:
                                    if st.button(f"🔍 Show Answers", key=f"view_{exam['id']}", use_container_width=True):
                                        st.session_state.exam_id = exam["id"]
                                        st.session_state.exam_title = exam["title"]
                                        st.session_state.start_exam = True
                                        st.session_state.exam_submitted = True 
                                        st.session_state.current_questions = supabase.table("questions").select("*").eq("exam_id", exam["id"]).execute().data
                                        st.rerun()
                                else:
                                    has_password = exam.get("password") is not None and str(exam["password"]).strip() != ""
                                    if has_password:
                                        entered_pwd = st.text_input(f"Access Code for {exam['title']}", type="password", key=f"pwd_{exam['id']}")
                                        
                                    if st.button(f"📝 Start Exam", key=f"btn_{exam['id']}", use_container_width=True):
                                        if has_password and entered_pwd.strip() != str(exam["password"]).strip():
                                            st.error("Wrong Exam Password!")
                                        else:
                                            # 'Start Exam' నొక్కగానే నేరుగా ఎగ్జామ్ మరియు టైమర్ స్టార్ట్ అవుతాయి
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
# LIVE ACTIVE EXAM WORKSPACE VIEW
# =========================
def exam_workspace_view():
    questions = st.session_state.current_questions
    total_questions = len(questions)

    if total_questions == 0:
        st.warning("No questions available in this exam.")
        if st.button("Go Back"):
            st.session_state.start_exam = False
            st.rerun()
        return

    remaining_time = 0
    if not st.session_state.exam_submitted:
        remaining_time = int(st.session_state.exam_end_time - time.time())
        
        if remaining_time <= 0:
            st.error("⏰ Time Out! Saving your progress and submitting the exam...")
            time.sleep(2)
            
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
        db_attempt = supabase.table("exam_attempts").select("*")\
            .eq("user_id", st.session_state.user_id)\
            .eq("exam_id", st.session_state.exam_id).execute().data
            
        if len(db_attempt) > 0:
            score = db_attempt[0]["score"]
            st.success(f"🎉 Exam Submitted! Your Score: {score}/{total_questions}")
        
        db_answers = supabase.table("user_answers").select("*").eq("attempt_id", db_attempt[0]["id"]).execute().data if len(db_attempt) > 0 else []
        ans_map = {a["question_id"]: a["answer"] for a in db_answers}

        exam_data = supabase.table("exams").select("*").eq("id", st.session_state.exam_id).execute().data
        if len(exam_data) > 0 and exam_data[0]["show_answers"]:
            st.subheader("📚 Review Sheet")
            for i, q in enumerate(questions):
                st.markdown(f"**Question {i+1}:** {q['question']}")
                u_ans = ans_map.get(q["id"], 'Not Answered')
                c_ans = q["correct_answer"]
                
                if q["type"] != "programming":
                    if str(u_ans).strip().lower() == str(c_ans).strip().lower():
                        st.success(f"Your Answer: {u_ans} (Correct)")
                    else:
                        st.error(f"Your Answer: {u_ans}")
                        st.warning(f"Correct Answer: {c_ans}")
                else:
                    st.info(f"Your Code/Answer: {u_ans} (Manual Review Item)")
                st.divider()

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
            st.metric(label="⏱️ Time Remaining", value=f"{mins:02d}:{secs:02d}")
            st.divider()
            
            st.subheader("Questions Panel")
            cols = st.columns(3)
            for i in range(total_questions):
                with cols[i % 3]:
                    q_id = questions[i]["id"]
                    label = f"🔴 {i+1}"
                    if q_id in st.session_state.answers and st.session_state.answers[q_id]:
                        label = f"🟢 {i+1}"
                    if i == current:
                        label = f"🔵 {i+1}"

                    if st.button(label, key=f"qnav_{i}", use_container_width=True):
                        st.session_state.question_index = i
                        st.rerun()

        with left:
            st.subheader(f"Question {current+1}/{total_questions}")
            st.write(question["question"])

            stored_ans = st.session_state.answers.get(question["id"], "")
            
            if question["type"] == "mcq":
                opts = [question["option_a"], question["option_b"], question["option_c"], question["option_d"]]
                try:
                    default_idx = opts.index(stored_ans) if stored_ans in opts else None
                except ValueError:
                    default_idx = None
                answer = st.radio("Choose Answer", opts, index=default_idx, key=f"radio_{question['id']}")
            elif question["type"] == "blank":
                answer = st.text_input("Your Answer", value=stored_ans, key=f"text_{question['id']}")
            else:
                answer = st.text_area("Write your Code/Answer here:", value=stored_ans, key=f"code_{question['id']}", height=250)

            if answer != stored_ans:
                st.session_state.answers[question["id"]] = answer

            st.write("")
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
                if st.button("🚀 Finalize & Submit Exam", type="primary", use_container_width=True):
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
        
        time.sleep(1)
        st.rerun()

# =========================
# MAIN ROUTING ENGINE CONTROL
# =========================
if not st.session_state.logged_in:
    login()
else:
    if st.session_state.role == "admin":
        admin_dashboard()
    elif st.session_state.start_exam:
        exam_workspace_view()
    else:
        user_dashboard()
