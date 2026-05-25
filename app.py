import streamlit as st
from supabase import create_client, Client
import os

# ==========================================
# 1. DATABASE CONNECTION (SUPABASE SETUP)
# ==========================================
# గమనిక: మీ Supabase Credentials ని ఇక్కడ సెట్ చేసుకోండి లేదా Environment Variables ఉపయోగించండి
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://your-supabase-url.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "your-supabase-anon-key")

@st.cache_resource
def init_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)

try:
    supabase: Client = init_supabase()
except Exception as e:
    st.error(f"Supabase Connection Failed: {e}")

# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def get_exam_leaderboard(exam_id):
    """ఎగ్జామ్ ఐడి ఆధారంగా టాప్ స్కోర్స్ సాధించిన విద్యార్థుల లిస్ట్ తెస్తుంది"""
    try:
        response = supabase.table("exam_attempts").select("score, user_id").eq("exam_id", exam_id).order("score", desc=True).execute()
        attempts = response.data
        
        leaderboard = []
        for att in attempts:
            user_resp = supabase.table("users").select("name, email").eq("id", att["user_id"]).execute()
            if user_resp.data:
                leaderboard.append({
                    "Name": user_resp.data[0]["name"],
                    "Email": user_resp.data[0]["email"],
                    "Score": att["score"]
                })
        return leaderboard
    except Exception as e:
        return []

# ==========================================
# 3. ADMIN DASHBOARD WORKSPACE
# ==========================================
def admin_dashboard():
    st.sidebar.title("🛡️ Admin Workspace")
    
    # Simple Clean Categorization Sidebar Menu
    menu = st.sidebar.selectbox(
        "Navigation Control",
        ["🗂️ Manage Course Content", "📝 Manage Exams & Questions", "📊 Student Results & Ranks"]
    )

    # ----------------------------------------------------
    # TAB 1: MANAGE COURSE CONTENT
    # ----------------------------------------------------
    if menu == "🗂️ Manage Course Content":
        tab1, tab2, tab3 = st.tabs(["📁 Modules Setup", "📂 Submodules Setup", "🖥️ Live/Recorded Classes"])
        
        # --- MODULES SETUP ---
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

        # --- SUBMODULES SETUP ---
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

        # --- CLASSES SETUP ---
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

    # ----------------------------------------------------
    # TAB 2: MANAGE EXAMS AND QUESTIONS
    # ----------------------------------------------------
    elif menu == "📝 Manage Exams & Questions":
        ex_tab1, ex_tab2 = st.tabs(["📝 Exams Setup & Instant Control", "❓ Advanced Question Paper Builder"])
        
        # --- EXAMS SETUP TAB ---
        with ex_tab1:
            st.subheader("Setup Dynamic Exams")
            classes_list = supabase.table("classes").select("*").execute().data
            cls_options = {c["title"]: c["id"] for c in classes_list} if classes_list else {}
            
            with st.form("create_exam_form", clear_on_submit=True):
                sel_cls = st.selectbox("Link with Lesson Class", list(cls_options.keys()))
                e_title = st.text_input("Exam Sheet Name")
                e_pwd = st.text_input("Exam Password Entry (Optional)", type="password")
                c_en = st.checkbox("Turn On Exam (Visible to Students immediately)", value=True)
                c_ans = st.checkbox("Enable Answers Visibility Sheet")
                if st.form_submit_button("📋 Generate Exam Layout"):
                    supabase.table("exams").insert({
                        "class_id": cls_options[sel_cls], "title": e_title, "password": e_pwd if e_pwd.strip() != "" else None,
                        "enabled": c_en, "show_answers": c_ans
                    }).execute()
                    st.success("Exam Created!")
                    st.rerun()

            st.divider()
            st.write("### ⚙️ Live Exam Master Controls")
            exams_all = supabase.table("exams").select("*").execute().data
            
            for ex in exams_all:
                st.markdown(f"#### 📄 Exam Sheet: **{ex['title']}**")
                col_e1, col_e2, col_e3, col_e4 = st.columns([2, 2, 1, 1])
                
                with col_e1:
                    t_active = st.toggle("Exam State (Active/Disabled)", value=ex["enabled"], key=f"tog_en_{ex['id']}")
                with col_e2:
                    t_ans = st.toggle("Show Answer Key Sheet to User", value=ex["show_answers"], key=f"tog_ans_{ex['id']}")
                with col_e3:
                    if st.button("⚡ Update Status", key=f"up_ex_{ex['id']}", use_container_width=True):
                        supabase.table("exams").update({"enabled": t_active, "show_answers": t_ans}).eq("id", ex["id"]).execute()
                        st.success("Toggles Applied!")
                        st.rerun()
                with col_e4:
                    if st.button("🗑️ Wipe Exam", key=f"del_ex_{ex['id']}", type="secondary", use_container_width=True):
                        supabase.table("exams").delete().eq("id", ex["id"]).execute()
                        st.warning("Exam Purged!")
                        st.rerun()
                st.divider()

        # --- ADVANCED QUESTION PAPER BUILDER ---
        with ex_tab2:
            st.subheader("🛠️ Premium Question Paper Creator")
            
            exams_q = supabase.table("exams").select("*").execute().data
            ex_options = {e["title"]: e["id"] for e in exams_q} if exams_q else {}
            
            if not ex_options:
                st.warning("⚠️ దయచేసి ప్రశ్నలు యాడ్ చేయడానికి ముందు ఒక ఎగ్జామ్‌ని క్రియేట్ చేయండి.")
            else:
                selected_exam_title = st.selectbox("🎯 ఏ ఎగ్జామ్ కి ప్రశ్నలు యాడ్ చేయాలి?", list(ex_options.keys()), key="builder_exam_select")
                target_exam_id = ex_options[selected_exam_title]
                
                st.markdown("---")
                st.markdown("### 📝 Add New Question")
                
                q_type = st.radio("ప్రశ్న రకం ఎంచుకోండి (Question Type):", ["Multiple Choice (MCQ)", "Fill in the Blanks", "Programming / Text Answer"], horizontal=True)
                q_text = st.text_area("🤔 ఇక్కడ మీ ప్రశ్న టైప్ చేయండి (Question Text):", height=100)
                
                a, b, c, d = "", "", "", ""
                correct_answer = ""
                q_type_db = "mcq"
                
                if q_type == "Multiple Choice (MCQ)":
                    st.markdown("#### Options Setup")
                    op_col1, op_col2 = st.columns(2)
                    with op_col1:
                        a = st.text_input("🔹 Option A", placeholder="First option...")
                        b = st.text_input("🔹 Option B", placeholder="Second option...")
                    with op_col2:
                        c = st.text_input("🔹 Option C", placeholder="Third option...")
                        d = st.text_input("🔹 Option D", placeholder="Fourth option...")
                    
                    correct_answer = st.selectbox("✅ Correct Option ఏది?", [a, b, c, d], help="పై ఆప్షన్లలో సరైన దాన్ని సెలెక్ట్ చేయండి")
                    q_type_db = "mcq"
                elif q_type == "Fill in the Blanks":
                    correct_answer = st.text_input("✅ Correct Answer టైప్ చేయండి:", placeholder="Type exact answer key...")
                    q_type_db = "blank"
                else:
                    st.info("💡 గమనిక: ప్రోగ్రామింగ్ ప్రశ్నలకి స్టూడెంట్స్ కోడ్ బాక్స్ లో ఆన్సర్ రాస్తారు. దాన్ని అడ్మిన్ మాన్యువల్‌గా రివ్యూ చేసి మార్కులు వేయాల్సి ఉంటుంది.")
                    correct_answer = "Manual Review Required"
                    q_type_db = "programming"
                    
                hint_text = st.text_input("💡 హింట్ (Hint - Optional):", placeholder="Students కి హెల్ప్ అయ్యే చిన్న హింట్...")
                
                if st.button("🚀 Add This Question to Paper", type="primary", use_container_width=True):
                    if not q_text.strip():
                        st.error("❌ ప్రశ్న ఖాళీగా వదిలేయకూడదు!")
                    else:
                        supabase.table("questions").insert({
                            "exam_id": target_exam_id, 
                            "question": q_text, 
                            "type": q_type_db,
                            "option_a": a, 
                            "option_b": b, 
                            "option_c": c, 
                            "option_d": d,
                            "correct_answer": correct_answer, 
                            "hint": hint_text
                        }).execute()
                        st.success("🎉 ప్రశ్న విజయవంతంగా క్వశ్చన్ పేపర్‌లోకి యాడ్ అయిపోయింది!")
                        st.rerun()

                st.markdown("---")
                st.markdown(f"### 📚 Active Test Bank ({selected_exam_title})")
                
                current_questions = supabase.table("questions").select("*").eq("exam_id", target_exam_id).execute().data
                
                if not current_questions:
                    st.info("ఈ ఎగ్జామ్‌లో ఇంకా ఎలాంటి ప్రశ్నలు లేవు. పైన ఫామ్ ఉపయోగించి యాడ్ చేయండి.")
                else:
                    st.write(f"మొత్తం ప్రశ్నలు: **{len(current_questions)}**")
                    
                    for idx, q in enumerate(current_questions):
                        with st.container():
                            view_col1, view_col2 = st.columns([5, 1])
                            
                            with view_col1:
                                if q["type"] == "mcq":
                                    type_badge = "🔷 MCQ"
                                elif q["type"] == "blank":
                                    type_badge = "🔶 Blank"
                                else:
                                    type_badge = "💻 Code"
                                    
                                st.markdown(f"**Q{idx+1}. {q['question']}** &nbsp;&nbsp; `{type_badge}`")
                                if q["type"] == "mcq":
                                    st.caption(f"A) {q['option_a']} | B) {q['option_b']} | C) {q['option_c']} | D) {q['option_d']}")
                                st.markdown(f"👉 **Key:** `{q['correct_answer']}` | *Hint:* _{q['hint'] if q['hint'] else 'None'}_")
                            
                            with view_col2:
                                st.write("")
                                if st.button("🗑️ Remove", key=f"del_q_{q['id']}", use_container_width=True, type="secondary"):
                                    supabase.table("questions").delete().eq("id", q["id"]).execute()
                                    st.warning(f"Question {idx+1} Deleted!")
                                    st.rerun()
                            st.markdown("<p style='margin-bottom: -5px;'></p>", unsafe_allow_html=True)
                            st.divider()

    # ----------------------------------------------------
    # TAB 3: RESULTS & MANUAL EVALUATION
    # ----------------------------------------------------
    elif menu == "📊 Student Results & Ranks":
        r_tab1, r_tab2, r_tab3 = st.tabs([
            "🏆 Live Leaderboards", 
            "📝 Manual Evaluation (Code/Text Reviews)", 
            "📜 All Submissions Log"
        ])
        
        # --- TAB 1: LEADERBOARD ---
        with r_tab1:
            st.subheader("🏆 Exam Rankings")
            exams = supabase.table("exams").select("*").execute().data
            if exams:
                exam_titles = [e["title"] for e in exams]
                sel_ex_lb = st.selectbox("Select Exam for Leaderboard", exam_titles, key="lb_select")
                target_ex = next((e for e in exams if e["title"] == sel_ex_lb), None)
                
                if target_ex:
                    board = get_exam_leaderboard(target_ex["id"])
                    if board:
                        for rank, st_row in enumerate(board):
                            medal = "🥇" if rank == 0 else "🥈" if rank == 1 else "🥉" if rank == 2 else f" {rank+1}."
                            st.write(f"{medal} **{st_row['Name']}** ({st_row['Email']}) — Score: **{st_row['Score']}**")
                    else:
                        st.info("No attempts recorded for this exam yet.")

        # --- TAB 2: MANUAL EVALUATION ---
        with r_tab2:
            st.subheader("📝 Manual Code & Essay Evaluator")
            st.markdown("స్టూడెంట్స్ టైప్ చేసిన ప్రోగ్రామింగ్ కోడ్ లేదా టెక్స్ట్ ఆన్సర్లను ఇక్కడ రివ్యూ చేసి మార్కులు ఇవ్వవచ్చు.")
            
            attempts_to_eval = supabase.table("exam_attempts").select("*").execute().data
            
            if not attempts_to_eval:
                st.info("రివ్యూ చేయడానికి ఎలాంటి స్టూడెంట్ సబ్మిషన్స్ లేవు.")
            else:
                for att in attempts_to_eval:
                    u_data = supabase.table("users").select("*").eq("id", att["user_id"]).execute().data
                    e_data = supabase.table("exams").select("*").eq("id", att["exam_id"]).execute().data
                    
                    if u_data and e_data:
                        student_name = u_data[0]['name']
                        exam_title = e_data[0]['title']
                        
                        with st.container(border=True):
                            col_s1, col_s2 = st.columns([3, 1])
                            with col_s1:
                                st.markdown(f"👤 **Student:** {student_name} | 🎯 **Exam:** {exam_title}")
                                st.caption("💻 Submitted Answer / Code:")
                                
                                # స్టూడెంట్ రాసిన కోడ్ ఇక్కడ డిస్ప్లే అవుతుంది
                                user_code = att.get("submitted_answers", "# No code answer text submitted.")
                                st.code(user_code, language="python")
                            
                            with col_s2:
                                st.markdown("##### 🔢 Score Panel")
                                current_score = int(att["score"])
                                
                                new_score = st.number_input(
                                    f"Set Score", 
                                    min_value=0, 
                                    max_value=100, 
                                    value=current_score, 
                                    key=f"score_in_{att['id']}"
                                )
                                
                                if st.button("💾 Save Score", key=f"btn_score_{att['id']}", type="primary", use_container_width=True):
                                    supabase.table("exam_attempts").update({"score": new_score}).eq("id", att["id"]).execute()
                                    st.success(f"Score updated to {new_score}!")
                                    st.rerun()

        # --- TAB 3: ALL SUBMISSIONS LOG ---
        with r_tab3:
            st.subheader("📜 System Submission Logs")
            attempts = supabase.table("exam_attempts").select("*").execute().data
            if not attempts:
                st.warning("Zero user submissions reported.")
            else:
                for att in attempts:
                    u_prof = supabase.table("users").select("*").eq("id", att["user_id"]).execute().data
                    e_prof = supabase.table("exams").select("*").eq("id", att["exam_id"]).execute().data
                    if u_prof and e_prof:
                        st.markdown(f"🔹 **{u_prof[0]['name']}** completed **{e_prof[0]['title']}** | Final Score: **{att['score']}**")
                        st.divider()

# ==========================================
# 4. USER/STUDENT DASHBOARD WORKSPACE
# ==========================================
def user_dashboard():
    st.title("🎓 Student Learning Portal")
    st.write("Welcome to your dashboard. Here you can view courses and take exams.")
    # మీ పాత యూజర్ డ్యాష్‌బోర్డ్ లాజిక్ కోడ్ అంతా ఇక్కడ వస్తుంది.
    st.info("Student panel functions can be linked here natively.")

# ==========================================
# 5. MAIN APP ENTRY ROUTER
# ==========================================
def main():
    st.set_page_config(page_title="Learning Management System", page_icon="🚀", layout="wide")
    
    # Simple Session State User Role Simulation Selector
    # (మీ అప్లికేషన్ లాగిన్ సిస్టమ్‌ని బట్టి దీన్ని మార్చుకోవచ్చు)
    st.sidebar.markdown("### 🔑 System Access Login")
    role = st.sidebar.radio("Select Interface Role:", ["Admin", "Student"])
    
    if role == "Admin":
        admin_dashboard()
    else:
        user_dashboard()

if __name__ == "__main__":
    main()