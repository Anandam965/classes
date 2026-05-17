# =========================================================
# app.py
# =========================================================

import streamlit as st
from supabase import create_client

# =========================================================
# SUPABASE CONFIG
# =========================================================

SUPABASE_URL = "https://ntmclisjmohkfpfigwjt.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im50bWNsaXNqbW9oa2ZwZmlnd2p0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg5ODU0NzQsImV4cCI6MjA5NDU2MTQ3NH0.bcm2hEBzCsEBklLKpBVvYGxXsGWNHHOZJOXx0w3YQBc"

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="Learning Management System",
    layout="wide"
)

# =========================================================
# CSS
# =========================================================

st.markdown("""
<style>

.main {
    background-color: #0E1117;
    color: white;
}

.title {
    font-size: 35px;
    font-weight: bold;
    color: #8B5CF6;
}

.card {
    background-color: #1E1E1E;
    padding: 20px;
    border-radius: 15px;
    margin-bottom: 20px;
}

.stButton > button {
    width: 100%;
    border-radius: 10px;
    height: 45px;
    font-size: 16px;
    font-weight: bold;
}

</style>
""", unsafe_allow_html=True)

# =========================================================
# SESSION STATE
# =========================================================

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "role" not in st.session_state:
    st.session_state.role = None

if "name" not in st.session_state:
    st.session_state.name = ""

# =========================================================
# HOME PAGE
# =========================================================

if not st.session_state.logged_in:

    st.markdown(
        '<p class="title">📚 Learning Management System</p>',
        unsafe_allow_html=True
    )

    option = st.radio(
        "Select Option",
        ["Sign In", "Sign Up"]
    )

    # =====================================================
    # SIGN IN
    # =====================================================

    if option == "Sign In":

        st.subheader("🔐 Sign In")

        username = st.text_input("Username")

        password = st.text_input(
            "Password",
            type="password"
        )

        if st.button("Login"):

            response = supabase.table("users").select("*").eq(
                "username",
                username
            ).eq(
                "password",
                password
            ).execute()

            if response.data:

                user = response.data[0]

                if user["status"] != "approved":

                    st.error(
                        "Admin approval pending"
                    )

                else:

                    st.session_state.logged_in = True
                    st.session_state.role = user["role"]
                    st.session_state.name = user["username"]

                    st.rerun()

            else:

                st.error("Invalid Credentials")

    # =====================================================
    # SIGN UP
    # =====================================================

    elif option == "Sign Up":

        st.subheader("📝 Sign Up")

        name = st.text_input("Full Name")

        username = st.text_input("Username")

        password = st.text_input(
            "Password",
            type="password"
        )

        if st.button("Create Account"):

            existing = supabase.table("users").select("*").eq(
                "username",
                username
            ).execute()

            if existing.data:

                st.error(
                    "Username already exists"
                )

            else:

                supabase.table("users").insert({

                    "name": name,
                    "username": username,
                    "password": password,
                    "role": "user",
                    "status": "pending"

                }).execute()

                st.success(
                    "Account Created! Wait for Admin Approval."
                )

# =========================================================
# LOGOUT
# =========================================================

else:

    st.sidebar.success(
        f"Welcome {st.session_state.name}"
    )

    if st.sidebar.button("Logout"):

        st.session_state.logged_in = False
        st.session_state.role = None
        st.session_state.name = ""

        st.rerun()

    # =====================================================
    # ADMIN DASHBOARD
    # =====================================================

    if st.session_state.role == "admin":

        st.markdown(
            '<p class="title">👨‍💼 Admin Dashboard</p>',
            unsafe_allow_html=True
        )

        menu = st.sidebar.radio(

            "Menu",

            [

                "Approve Users",

                "Add Module",

                "Add Topic",

                "Add Session",

                "Add Exam",

                "Add Question",

                "Enable Answers",

                "Enable Solutions",

                "View Results"

            ]
        )

        # =================================================
        # APPROVE USERS
        # =================================================

        if menu == "Approve Users":

            st.subheader("✅ Approve Users")

            pending_users = supabase.table(
                "users"
            ).select("*").eq(
                "status",
                "pending"
            ).execute()

            if pending_users.data:

                for user in pending_users.data:

                    st.markdown(f"""
                    <div class="card">

                    <h3>{user['name']}</h3>

                    <p>{user['username']}</p>

                    </div>
                    """, unsafe_allow_html=True)

                    if st.button(
                        f"Approve {user['username']}"
                    ):

                        supabase.table("users").update({

                            "status": "approved"

                        }).eq(
                            "id",
                            user["id"]
                        ).execute()

                        st.success("Approved")

                        st.rerun()

        # =================================================
        # ADD MODULE
        # =================================================

        elif menu == "Add Module":

            module_name = st.text_input(
                "Module Name"
            )

            if st.button("Save Module"):

                supabase.table("modules").insert({

                    "module_name": module_name

                }).execute()

                st.success("Module Added")

        # =================================================
        # ADD TOPIC
        # =================================================

        elif menu == "Add Topic":

            modules = supabase.table(
                "modules"
            ).select("*").execute()

            module_dict = {

                module["module_name"]: module["id"]

                for module in modules.data
            }

            selected_module = st.selectbox(
                "Select Module",
                list(module_dict.keys())
            )

            topic_name = st.text_input(
                "Topic Name"
            )

            if st.button("Save Topic"):

                supabase.table("topics").insert({

                    "module_id":
                    module_dict[selected_module],

                    "topic_name":
                    topic_name

                }).execute()

                st.success("Topic Added")

        # =================================================
        # ADD SESSION
        # =================================================

        elif menu == "Add Session":

            topics = supabase.table(
                "topics"
            ).select("*").execute()

            topic_dict = {

                topic["topic_name"]: topic["id"]

                for topic in topics.data
            }

            selected_topic = st.selectbox(
                "Select Topic",
                list(topic_dict.keys())
            )

            day = st.text_input("Day")

            intro = st.text_area("Introduction")

            timing = st.text_input("Timing")

            meeting_link = st.text_input(
                "Meeting Link"
            )

            video_link = st.text_input(
                "Video Link"
            )

            notes_link = st.text_input(
                "Notes Link"
            )

            if st.button("Save Session"):

                supabase.table("sessions").insert({

                    "topic_id":
                    topic_dict[selected_topic],

                    "day":
                    day,

                    "intro":
                    intro,

                    "timing":
                    timing,

                    "meeting_link":
                    meeting_link,

                    "video_link":
                    video_link,

                    "notes_link":
                    notes_link

                }).execute()

                st.success("Session Added")

        # =================================================
        # ADD EXAM
        # =================================================

        elif menu == "Add Exam":

            topics = supabase.table(
                "topics"
            ).select("*").execute()

            topic_dict = {

                topic["topic_name"]: topic["id"]

                for topic in topics.data
            }

            selected_topic = st.selectbox(
                "Select Topic",
                list(topic_dict.keys())
            )

            exam_name = st.text_input(
                "Exam Name"
            )

            duration = st.number_input(
                "Duration",
                value=30
            )

            if st.button("Create Exam"):

                supabase.table("exams").insert({

                    "topic_id":
                    topic_dict[selected_topic],

                    "exam_name":
                    exam_name,

                    "duration":
                    duration,

                    "answers_enabled":
                    False,

                    "solutions_enabled":
                    False

                }).execute()

                st.success("Exam Added")

        # =================================================
        # ADD QUESTION
        # =================================================

        elif menu == "Add Question":

            exams = supabase.table(
                "exams"
            ).select("*").execute()

            exam_dict = {

                exam["exam_name"]: exam["id"]

                for exam in exams.data
            }

            selected_exam = st.selectbox(
                "Select Exam",
                list(exam_dict.keys())
            )

            question = st.text_area(
                "Question"
            )

            question_type = st.selectbox(

                "Question Type",

                ["MCQ", "TEXT"]

            )

            option1 = ""
            option2 = ""
            option3 = ""
            option4 = ""

            if question_type == "MCQ":

                option1 = st.text_input(
                    "Option 1"
                )

                option2 = st.text_input(
                    "Option 2"
                )

                option3 = st.text_input(
                    "Option 3"
                )

                option4 = st.text_input(
                    "Option 4"
                )

            correct_answer = st.text_input(
                "Correct Answer"
            )

            solution = st.text_area(
                "Solution"
            )

            solution_image = st.text_input(
                "Solution Image URL"
            )

            if st.button("Save Question"):

                supabase.table("questions").insert({

                    "exam_id":
                    exam_dict[selected_exam],

                    "question":
                    question,

                    "question_type":
                    question_type,

                    "option1":
                    option1,

                    "option2":
                    option2,

                    "option3":
                    option3,

                    "option4":
                    option4,

                    "correct_answer":
                    correct_answer,

                    "solution":
                    solution,

                    "solution_image":
                    solution_image

                }).execute()

                st.success("Question Added")

        # =================================================
        # ENABLE ANSWERS
        # =================================================

        elif menu == "Enable Answers":

            exams = supabase.table(
                "exams"
            ).select("*").execute()

            exam_dict = {

                exam["exam_name"]: exam["id"]

                for exam in exams.data
            }

            selected_exam = st.selectbox(
                "Select Exam",
                list(exam_dict.keys())
            )

            if st.button("Enable Answers"):

                supabase.table("exams").update({

                    "answers_enabled": True

                }).eq(
                    "id",
                    exam_dict[selected_exam]
                ).execute()

                st.success("Answers Enabled")

        # =================================================
        # ENABLE SOLUTIONS
        # =================================================

        elif menu == "Enable Solutions":

            exams = supabase.table(
                "exams"
            ).select("*").execute()

            exam_dict = {

                exam["exam_name"]: exam["id"]

                for exam in exams.data
            }

            selected_exam = st.selectbox(
                "Select Exam",
                list(exam_dict.keys())
            )

            if st.button("Enable Solutions"):

                supabase.table("exams").update({

                    "solutions_enabled": True

                }).eq(
                    "id",
                    exam_dict[selected_exam]
                ).execute()

                st.success("Solutions Enabled")

        # =================================================
        # VIEW RESULTS
        # =================================================

        elif menu == "View Results":

            results = supabase.table(
                "exam_results"
            ).select("*").execute()

            if results.data:

                for result in results.data:

                    st.markdown(f"""
                    <div class="card">

                    <h3>{result['username']}</h3>

                    <p>Score:
                    {result['score']}</p>

                    <p>Correct:
                    {result['correct_answers']}</p>

                    <p>Wrong:
                    {result['wrong_answers']}</p>

                    </div>
                    """, unsafe_allow_html=True)

    # =====================================================
    # USER DASHBOARD
    # =====================================================

    elif st.session_state.role == "user":

        st.markdown(
            '<p class="title">📘 User Dashboard</p>',
            unsafe_allow_html=True
        )

        modules = supabase.table(
            "modules"
        ).select("*").execute()

        for module in modules.data:

            with st.expander(
                f"📚 {module['module_name']}"
            ):

                topics = supabase.table(
                    "topics"
                ).select("*").eq(
                    "module_id",
                    module["id"]
                ).execute()

                for topic in topics.data:

                    st.markdown(
                        f"## 🔹 {topic['topic_name']}"
                    )

                    # =====================================
                    # SESSIONS
                    # =====================================

                    sessions = supabase.table(
                        "sessions"
                    ).select("*").eq(
                        "topic_id",
                        topic["id"]
                    ).execute()

                    for session in sessions.data:

                        st.markdown(f"""
                        <div class="card">

                        <h3>{session['day']}</h3>

                        <p>{session['intro']}</p>

                        <p>{session['timing']}</p>

                        </div>
                        """, unsafe_allow_html=True)

                        col1, col2, col3 = st.columns(3)

                        with col1:

                            st.link_button(
                                "🎥 Join",
                                session["meeting_link"]
                            )

                        with col2:

                            st.link_button(
                                "▶️ Video",
                                session["video_link"]
                            )

                        with col3:

                            st.link_button(
                                "📄 Notes",
                                session["notes_link"]
                            )

                    # =====================================
                    # EXAMS
                    # =====================================

                    exams = supabase.table(
                        "exams"
                    ).select("*").eq(
                        "topic_id",
                        topic["id"]
                    ).execute()

                    if exams.data:

                        st.subheader("📝 Exams")

                        for exam in exams.data:

                            st.markdown(f"""
                            <div class="card">

                            <h3>{exam['exam_name']}</h3>

                            <p>Duration:
                            {exam['duration']} Minutes</p>

                            </div>
                            """, unsafe_allow_html=True)

                            if st.button(
                                f"Start {exam['exam_name']}"
                            ):

                                questions = supabase.table(
                                    "questions"
                                ).select("*").eq(
                                    "exam_id",
                                    exam["id"]
                                ).execute()

                                score = 0
                                attempted = 0
                                correct = 0
                                wrong = 0

                                user_answers = {}

                                with st.form(
                                    f"exam_form_{exam['id']}"
                                ):

                                    for q in questions.data:

                                        st.markdown(
                                            f"### {q['question']}"
                                        )

                                        answer = ""

                                        if q["question_type"] == "MCQ":

                                            options = [

                                                q["option1"],
                                                q["option2"],
                                                q["option3"],
                                                q["option4"]

                                            ]

                                            answer = st.radio(

                                                "Select Answer",

                                                options,

                                                key=f"q_{q['id']}",

                                                index=None

                                            )

                                        else:

                                            answer = st.text_area(

                                                "Your Answer",

                                                key=f"text_{q['id']}"

                                            )

                                        user_answers[q["id"]] = answer

                                    submit_exam = st.form_submit_button(
                                        "Submit Exam"
                                    )

                                if submit_exam:

                                    total_questions = len(
                                        questions.data
                                    )

                                    for q in questions.data:

                                        selected = user_answers[q["id"]]

                                        marks = 0

                                        if selected:

                                            attempted += 1

                                            if (
                                                str(selected).strip().lower()
                                                ==
                                                str(q["correct_answer"]).strip().lower()
                                            ):

                                                marks = 1
                                                score += 1
                                                correct += 1

                                            else:

                                                wrong += 1

                                        supabase.table(
                                            "student_answers"
                                        ).insert({

                                            "username":
                                            st.session_state.name,

                                            "exam_id":
                                            exam["id"],

                                            "question_id":
                                            q["id"],

                                            "selected_answer":
                                            selected,

                                            "marks":
                                            marks

                                        }).execute()

                                    supabase.table(
                                        "exam_results"
                                    ).insert({

                                        "username":
                                        st.session_state.name,

                                        "exam_id":
                                        exam["id"],

                                        "total_questions":
                                        total_questions,

                                        "attempted":
                                        attempted,

                                        "correct_answers":
                                        correct,

                                        "wrong_answers":
                                        wrong,

                                        "score":
                                        score

                                    }).execute()

                                    st.success(
                                        f"Score: {score}/{total_questions}"
                                    )

                                    # =====================
                                    # ANSWERS
                                    # =====================

                                    if exam["answers_enabled"]:

                                        st.subheader(
                                            "✅ Answers"
                                        )

                                        for q in questions.data:

                                            st.markdown(
                                                f"### {q['question']}"
                                            )

                                            st.success(
                                                q["correct_answer"]
                                            )

                                    # =====================
                                    # SOLUTIONS
                                    # =====================

                                    if exam["solutions_enabled"]:

                                        st.subheader(
                                            "📘 Solutions"
                                        )

                                        for q in questions.data:

                                            st.markdown(
                                                f"### {q['question']}"
                                            )

                                            st.info(
                                                q["solution"]
                                            )

                                            if q["solution_image"]:

                                                st.image(
                                                    q["solution_image"]
                                                )

        # =================================================
        # PERFORMANCE
        # =================================================

        st.subheader("📊 My Performance")

        results = supabase.table(
            "exam_results"
        ).select("*").eq(
            "username",
            st.session_state.name
        ).execute()

        if results.data:

            total_score = 0

            total_exams = len(
                results.data
            )

            for result in results.data:

                total_score += result["score"]

                st.markdown(f"""
                <div class="card">

                <h3>Exam ID:
                {result['exam_id']}</h3>

                <p>Total Questions:
                {result['total_questions']}</p>

                <p>Attempted:
                {result['attempted']}</p>

                <p>Correct:
                {result['correct_answers']}</p>

                <p>Wrong:
                {result['wrong_answers']}</p>

                <p>Score:
                {result['score']}</p>

                </div>
                """, unsafe_allow_html=True)

            st.success(
                f"Total Score: {total_score}"
            )

            st.success(
                f"Total Exams: {total_exams}"
            )
