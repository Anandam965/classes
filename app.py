# app.py

import streamlit as st
from supabase import create_client
import uuid

# =========================
# SUPABASE CONFIG
# =========================

SUPABASE_URL = "https://lybhhtorasnwwaehqvnc.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx5YmhodG9yYXNud3dhZWhxdm5jIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzkxMDk0NTksImV4cCI6MjA5NDY4NTQ1OX0.8LO08tXBNBD83TIrR8oiuCIo97CtvvaupSIahTBAAuo"


supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================
# PAGE CONFIG
# =========================

st.set_page_config(
    page_title="LMS Application",
    layout="wide"
)

# =========================
# SESSION STATES
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

if "marked" not in st.session_state:
    st.session_state.marked = []

if "read_questions" not in st.session_state:
    st.session_state.read_questions = []

# =========================
# LOGIN FUNCTION
# =========================

def login():

    st.title("📚 LMS Login")

    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Login"):

        try:

            response = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            user = response.user

            user_data = supabase.table("users").select("*").eq(
                "email",
                email
            ).execute()

            if len(user_data.data) > 0:

                role = user_data.data[0]["role"]

                st.session_state.logged_in = True
                st.session_state.role = role
                st.session_state.user_id = user.id

                st.rerun()

        except Exception as e:
            st.error(str(e))

# =========================
# ADMIN DASHBOARD
# =========================

def admin_dashboard():

    st.sidebar.title("Admin Panel")

    menu = st.sidebar.selectbox(
        "Menu",
        [
            "Add Module",
            "Add Submodule",
            "Add Class",
            "Create Exam",
            "Add Questions",
            "View Results"
        ]
    )

    # =========================
    # ADD MODULE
    # =========================

    if menu == "Add Module":

        st.title("Add Module")

        module_name = st.text_input("Module Name")

        if st.button("Add Module"):

            supabase.table("modules").insert({
                "title": module_name
            }).execute()

            st.success("Module Added")

    # =========================
    # ADD SUBMODULE
    # =========================

    elif menu == "Add Submodule":

        st.title("Add Submodule")

        modules = supabase.table("modules").select("*").execute().data

        module_names = [m["title"] for m in modules]

        selected_module = st.selectbox("Select Module", module_names)

        submodule_name = st.text_input("Submodule Name")

        if st.button("Add Submodule"):

            module_id = None

            for m in modules:
                if m["title"] == selected_module:
                    module_id = m["id"]

            supabase.table("submodules").insert({
                "module_id": module_id,
                "title": submodule_name
            }).execute()

            st.success("Submodule Added")

    # =========================
    # ADD CLASS
    # =========================
    # =========================
    # VIEW RESULTS
    # =========================
    
    elif menu == "View Results":
    
        st.title("Student Exam Results")
    
        attempts = supabase.table(
            "exam_attempts"
        ).select("*").execute().data
    
        if len(attempts) == 0:
    
            st.warning("No attempts found")
    
        else:
    
            for attempt in attempts:
    
                user_data = supabase.table(
                    "users"
                ).select("*").eq(
                    "id",
                    attempt["user_id"]
                ).execute().data
    
                exam_data = supabase.table(
                    "exams"
                ).select("*").eq(
                    "id",
                    attempt["exam_id"]
                ).execute().data
    
                if len(user_data) == 0 or len(exam_data) == 0:
                    continue
    
                user = user_data[0]
                exam = exam_data[0]
    
                st.divider()
    
                st.subheader(
                    f"{user['name']} - {exam['title']}"
                )
    
                st.success(
                    f"Score : {attempt['score']}"
                )
    
                user_answers = supabase.table(
                    "user_answers"
                ).select("*").eq(
                    "attempt_id",
                    attempt["id"]
                ).execute().data
    
                for ua in user_answers:
    
                    question_data = supabase.table(
                        "questions"
                    ).select("*").eq(
                        "id",
                        ua["question_id"]
                    ).execute().data
    
                    if len(question_data) == 0:
                        continue
    
                    q = question_data[0]
    
                    st.markdown(
                        f"### {q['question']}"
                    )
    
                    st.info(
                        f"User Answer : {ua['answer']}"
                    )
    
                    correct_answer = q["correct_answer"]
    
                    if ua["answer"].strip().lower() == correct_answer.strip().lower():
    
                        st.success("✅ Correct")
    
                    else:
    
                        st.error("❌ Wrong")
    
                        st.warning(
                            f"Correct Answer : {correct_answer}"
                        )
    
                    # SHOW OPTIONS FOR MCQ
    
                    if q["type"] == "mcq":
    
                        st.write("Options:")
    
                        st.write(
                            f"A. {q['option_a']}"
                        )
    
                        st.write(
                            f"B. {q['option_b']}"
                        )
    
                        st.write(
                            f"C. {q['option_c']}"
                        )
    
                        st.write(
                            f"D. {q['option_d']}"
                        )
    
                    # SHOW HINT FOR BLANKS
    
                    if q["type"] == "blank":
    
                        st.info(
                            f"Hint : {q['hint']}"
                        )
    
                    st.divider()
    elif menu == "Add Class":

        st.title("Add Class")

        submodules = supabase.table("submodules").select("*").execute().data

        sub_names = [s["title"] for s in submodules]

        selected_sub = st.selectbox("Select Submodule", sub_names)

        class_title = st.text_input("Class Title")

        class_link = st.text_input("Class Link")

        video_link = st.text_input("Recorded Video Link")

        notes_pdf = st.text_input("Notes PDF URL")

        if st.button("Add Class"):

            submodule_id = None

            for s in submodules:
                if s["title"] == selected_sub:
                    submodule_id = s["id"]

            supabase.table("classes").insert({
                "submodule_id": submodule_id,
                "title": class_title,
                "class_link": class_link,
                "recorded_video": video_link,
                "notes_pdf": notes_pdf
            }).execute()

            st.success("Class Added")

    # =========================
    # CREATE EXAM
    # =========================

    elif menu == "Create Exam":

        st.title("Create Exam")

        classes = supabase.table("classes").select("*").execute().data

        class_titles = [c["title"] for c in classes]

        selected_class = st.selectbox("Select Class", class_titles)

        exam_title = st.text_input("Exam Title")

        enable_exam = st.checkbox("Enable Exam")

        show_answers = st.checkbox("Enable Answers")

        if st.button("Create Exam"):

            class_id = None

            for c in classes:
                if c["title"] == selected_class:
                    class_id = c["id"]

            supabase.table("exams").insert({
                "class_id": class_id,
                "title": exam_title,
                "enabled": enable_exam,
                "show_answers": show_answers
            }).execute()

            st.success("Exam Created")

    # =========================
    # ADD QUESTIONS
    # =========================

    elif menu == "Add Questions":

        st.title("Add Questions")

        exams = supabase.table("exams").select("*").execute().data

        exam_titles = [e["title"] for e in exams]

        selected_exam = st.selectbox("Select Exam", exam_titles)

        q_type = st.selectbox(
            "Question Type",
            ["mcq", "blank"]
        )

        question = st.text_area("Question")

        option_a = ""
        option_b = ""
        option_c = ""
        option_d = ""

        if q_type == "mcq":

            option_a = st.text_input("Option A")
            option_b = st.text_input("Option B")
            option_c = st.text_input("Option C")
            option_d = st.text_input("Option D")

        hint = st.text_input("Hint")

        correct_answer = st.text_input("Correct Answer")

        if st.button("Add Question"):

            exam_id = None

            for e in exams:
                if e["title"] == selected_exam:
                    exam_id = e["id"]

            supabase.table("questions").insert({
                "exam_id": exam_id,
                "question": question,
                "type": q_type,
                "option_a": option_a,
                "option_b": option_b,
                "option_c": option_c,
                "option_d": option_d,
                "correct_answer": correct_answer,
                "hint": hint
            }).execute()

            st.success("Question Added")

# =========================
# USER DASHBOARD
# =========================

def user_dashboard():

    st.sidebar.title("User Panel")

    modules = supabase.table("modules").select("*").execute().data

    for module in modules:

        with st.expander(module["title"]):

            submodules = supabase.table("submodules").select("*").eq(
                "module_id",
                module["id"]
            ).execute().data

            for sub in submodules:

                st.subheader(sub["title"])

                classes = supabase.table("classes").select("*").eq(
                    "submodule_id",
                    sub["id"]
                ).execute().data

                for cls in classes:

                    st.markdown(f"### {cls['title']}")

                    st.link_button(
                        "Join Class",
                        cls["class_link"]
                    )

                    st.link_button(
                        "Watch Video",
                        cls["recorded_video"]
                    )

                    st.link_button(
                        "Notes PDF",
                        cls["notes_pdf"]
                    )

                    exams = supabase.table("exams").select("*").eq(
                        "class_id",
                        cls["id"]
                    ).execute().data

                    for exam in exams:

                        if exam["enabled"]:

                            if st.button(
                                f"Start Exam - {exam['title']}",
                                key=exam["id"]
                            ):
                            
                                st.session_state.exam_id = exam["id"]
                                st.session_state.exam_title = exam["title"]
                            
                                st.session_state.start_exam = True
                            
                                st.rerun()
                            

# =========================
# MAIN
# =========================

if not st.session_state.logged_in:
    login()

else:

    if st.session_state.role == "admin":
        admin_dashboard()

    else:
        user_dashboard()
# =========================
# OPEN EXAM PAGE
# =========================

if "start_exam" not in st.session_state:
    st.session_state.start_exam = False

if st.session_state.start_exam:

    questions = supabase.table("questions").select("*").eq(
        "exam_id",
        st.session_state.exam_id
    ).execute().data

    st.title(st.session_state.exam_title)

    total_questions = len(questions)

    if "question_index" not in st.session_state:
        st.session_state.question_index = 0

    current = st.session_state.question_index

    question = questions[current]

    
    left, right = st.columns([4,1])

    
    with right:
        st.subheader("Questions")
    
        cols = st.columns(3)
    
        for i in range(total_questions):
    
            col = cols[i % 3]
    
            with col:
    
                q_id = questions[i]["id"]
    
                # DEFAULT RED
    
                bg_color = "#ff4b4b"
    
                # ANSWERED GREEN
    
                if (
                    q_id in st.session_state.answers
                    and st.session_state.answers[q_id]
                ):
                    bg_color = "#28a745"
    
                # CURRENT QUESTION BLUE
    
                if i == current:
                    bg_color = "#1f77ff"
    
                st.markdown(
                    f"""
                    <style>
                    div[data-testid="stButton"] button {{
                        background-color: {bg_color};
                        color: white;
                        border-radius: 10px;
                        font-weight: bold;
                    }}
                    </style>
                    """,
                    unsafe_allow_html=True
                )
    
                if st.button(
                    str(i + 1),
                    key=f"nav_btn_{i}_{current}",
                    use_container_width=True
                ):
    
                    st.session_state.question_index = i
                    st.rerun()

        
    
    with left:
    
        st.subheader(
            f"Question {current+1}/{total_questions}"
        )
    
        st.write(question["question"])

    

    if question["type"] == "mcq":
        answer = st.radio(
            "Choose Answer",
            [
                question["option_a"],
                question["option_b"],
                question["option_c"],
                question["option_d"]
            ],
            index=None,
            key=question["id"]
        )
        

    else:

        answer = st.text_input(
            "Your Answer",
            key=question["id"]
        )

    st.session_state.answers[question["id"]] = answer

    col1, col2 = st.columns(2)

    with col1:

        if st.button("Previous"):

            if current > 0:
                st.session_state.question_index -= 1
                st.rerun()

    with col2:

        if st.button("Next"):

            if current < total_questions - 1:
                st.session_state.question_index += 1
                st.rerun()

    if current == total_questions - 1:

        if st.button("Submit Exam"):
    
            score = 0
    
            for q in questions:
    
                user_ans = st.session_state.answers.get(q["id"], "")
    
                if user_ans:
    
                    if user_ans.strip().lower() == q["correct_answer"].strip().lower():
                        score += 1
    
            # SAVE ATTEMPT
            # =========================
            # SAVE ATTEMPT
            # =========================
            
            attempt_response = supabase.table(
                "exam_attempts"
            ).insert({
                "user_id": st.session_state.user_id,
                "exam_id": st.session_state.exam_id,
                "score": score,
                "submitted": True
            }).execute()
            
            # GET ATTEMPT ID
            
            attempt_id = attempt_response.data[0]["id"]
            
            # =========================
            # SAVE USER ANSWERS
            # =========================
            
            for q in questions:
            
                user_answer = st.session_state.answers.get(
                    q["id"],
                    ""
                )
            
                supabase.table(
                    "user_answers"
                ).insert({
                    "attempt_id": attempt_id,
                    "question_id": q["id"],
                    "answer": user_answer
                }).execute()
           
    
            # SHOW SCORE
    
            st.success(
                f"Your Score: {score}/{total_questions}"
            )
    
            # GET EXAM DETAILS
    
            exam_data = supabase.table("exams").select("*").eq(
                "id",
                st.session_state.exam_id
            ).execute().data
    
            if len(exam_data) > 0:
    
                exam = exam_data[0]
    
                # =========================
                # SHOW ANSWERS IF ENABLED
                # =========================
    
            
                if exam["show_answers"]:

                    st.divider()
                
                    # BUTTON
                
                    if st.button("Show Answers"):
                
                        st.subheader("Correct Answers")
                
                        for i, q in enumerate(questions):
                
                            st.markdown(
                                f"### Question {i+1}"
                            )
                
                            st.write(q["question"])
                
                            user_ans = st.session_state.answers.get(
                                q["id"],
                                "No Answer"
                            )
                
                            st.info(
                                f"Your Answer: {user_ans}"
                            )
                
                            correct_answer = q["correct_answer"]
                
                            # CORRECT / WRONG
                
                            if str(user_ans).strip().lower() == str(correct_answer).strip().lower():
                
                                st.success("✅ Correct")
                
                            else:
                
                                st.error("❌ Wrong")
                
                            st.success(
                                f"Correct Answer: {correct_answer}"
                            )
                
                            # MCQ OPTIONS
                
                            if q["type"] == "mcq":
                
                                st.write("Options:")
                
                                st.write(
                                    f"A. {q['option_a']}"
                                )
                
                                st.write(
                                    f"B. {q['option_b']}"
                                )
                
                                st.write(
                                    f"C. {q['option_c']}"
                                )
                
                                st.write(
                                    f"D. {q['option_d']}"
                                )
                
                            # BLANK HINT
                
                            if q["type"] == "blank":
                
                                st.warning(
                                    f"Hint: {q['hint']}"
                                )
                
                            st.divider()
                
                else:
                
                    st.warning(
                        "Answers are disabled by admin."
                    )
                    
            st.session_state.start_exam = False
