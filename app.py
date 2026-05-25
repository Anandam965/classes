# ----------------------------------------------------
    # TAB 2: MANAGE EXAMS AND QUESTIONS (PREMIUM INTERFACE)
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

        # --- NEW ADVANCED QUESTION PAPER BUILDER ---
        with ex_tab2:
            st.subheader("🛠️ Premium Question Paper Creator")
            
            exams_q = supabase.table("exams").select("*").execute().data
            ex_options = {e["title"]: e["id"] for e in exams_q} if exams_q else {}
            
            if not ex_options:
                st.warning("⚠️ దయచేసి ప్రశ్నలు యాడ్ చేయడానికి ముందు ఒక ఎగ్జామ్‌ని క్రియేట్ చేయండి.")
            else:
                # 1. Select Exam
                selected_exam_title = st.selectbox("🎯 ఏ ఎగ్జామ్ కి ప్రశ్నలు యాడ్ చేయాలి?", list(ex_options.keys()), key="builder_exam_select")
                target_exam_id = ex_options[selected_exam_title]
                
                # Form Container
                st.markdown("---")
                st.markdown("### 📝 Add New Question")
                
                q_type = st.radio("ప్రశ్న రకం ఎంచుకోండి (Question Type):", ["Multiple Choice (MCQ)", "Fill in the Blanks"], horizontal=True)
                q_text = st.text_area("🤔 ఇక్కడ మీ ప్రశ్న టైప్ చేయండి (Question Text):", height=100)
                
                # Dynamic inputs based on type
                a, b, c, d = "", "", "", ""
                if q_type == "Multiple Choice (MCQ)":
                    st.markdown("#### Options Setup")
                    op_col1, op_col2 = st.columns(2)
                    with op_col1:
                        a = st.text_input("🔹 Option A", placeholder="First option...")
                        b = st.text_input("🔹 Option B", placeholder="Second option...")
                    with op_col2:
                        c = st.text_input("🔹 Option C", placeholder="Third option...")
                        d = st.text_input("🔹 Option D", placeholder="Fourth option...")
                    
                    # Dropdown for MCQ correct answer
                    correct_answer = st.selectbox("✅ Correct Option ఏది?", [a, b, c, d], help="పై ఆప్షన్లలో సరైన దాన్ని సెలెక్ట్ చేయండి")
                    q_type_db = "mcq"
                else:
                    correct_answer = st.text_input("✅ Correct Answer టైప్ చేయండి:", placeholder="Type exact answer key...")
                    q_type_db = "blank"
                    
                hint_text = st.text_input("💡 హింట్ (Hint - Optional):", placeholder="Students కి హెల్ప్ అయ్యే చిన్న హింట్...")
                
                # Submit Button
                if st.button("🚀 Add This Question to Paper", type="primary", use_container_width=True):
                    if not q_text.strip() or not correct_answer.strip():
                        st.error("❌ ప్రశ్ర మరియు కరెక్ట్ ఆన్సర్ ఖాళీగా వదిలేయకూడదు!")
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

                # 2. Live Question Bank Viewer / Management
                st.markdown("---")
                st.markdown(f"### 📚 Active Test Bank ({selected_exam_title})")
                
                # Fetch questions for this exam specifically
                current_questions = supabase.table("questions").select("*").eq("exam_id", target_exam_id).execute().data
                
                if not current_questions:
                    st.info("ఈ ఎగ్జామ్‌లో ఇంకా ఎలాంటి ప్రశ్నలు లేవు. పైన ఫామ్ ఉపయోగించి యాడ్ చేయండి.")
                else:
                    st.write(f"మొత్తం ప్రశ్నలు: **{len(current_questions)}**")
                    
                    # Dynamic Table UI for management
                    for idx, q in enumerate(current_questions):
                        with st.container():
                            view_col1, view_col2 = st.columns([5, 1])
                            
                            with view_col1:
                                type_badge = "🔷 MCQ" if q["type"] == "mcq" else "🔶 Blank"
                                st.markdown(f"**Q{idx+1}. {q['question']}** &nbsp;&nbsp; `{type_badge}`")
                                if q["type"] == "mcq":
                                    st.caption(f"A) {q['option_a']} | B) {q['option_b']} | C) {q['option_c']} | D) {q['option_d']}")
                                st.markdown(f"👉 **Key:** `{q['correct_answer']}` | *Hint:* _{q['hint'] if q['hint'] else 'None'}_")
                            
                            with view_col2:
                                st.write("") # Alignment spacing
                                if st.button("🗑️ Remove", key=f"del_q_{q['id']}", use_container_width=True, type="secondary"):
                                    supabase.table("questions").delete().eq("id", q["id"]).execute()
                                    st.warning(f"Question {idx+1} Deleted!")
                                    st.rerun()
                            st.markdown("<p style='margin-bottom: -5px;'></p>", unsafe_allow_html=True)
                            st.divider()
