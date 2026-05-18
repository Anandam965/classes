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
            "Add Questions"
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

                                st.switch_page("exam.py")

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
