# exam.py

import streamlit as st
from supabase import create_client


SUPABASE_URL = "https://ntmclisjmohkfpfigwjt.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im50bWNsaXNqbW9oa2ZwZmlnd2p0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg5ODU0NzQsImV4cCI6MjA5NDU2MTQ3NH0.bcm2hEBzCsEBklLKpBVvYGxXsGWNHHOZJOXx0w3YQBc"


supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

exam_id = st.session_state.exam_id
user_id = st.session_state.user_id

attempt = supabase.table("exam_attempts").select("*").eq(
    "user_id",
    user_id
).eq(
    "exam_id",
    exam_id
).execute()

if len(attempt.data) > 0:

    st.error("You already completed this exam.")
    st.stop()

questions = supabase.table("questions").select("*").eq(
    "exam_id",
    exam_id
).execute().data

total_questions = len(questions)

current = st.session_state.question_index

question = questions[current]

# =========================
# STATUS PANEL
# =========================

answered = len(st.session_state.answers)
marked = len(st.session_state.marked)
readed = len(st.session_state.read_questions)

col1, col2 = st.columns([3,1])

with col2:

    st.info(f"Answered : {answered}")
    st.warning(f"Marked : {marked}")
    st.success(f"Read : {readed}")
    st.error(f"Remaining : {total_questions - answered}")

# =========================
# QUESTION
# =========================

with col1:

    st.subheader(
        f"Question {current+1}/{total_questions}"
    )

    st.write(question["question"])

    if question["id"] not in st.session_state.read_questions:
        st.session_state.read_questions.append(question["id"])

    answer = None

    if question["type"] == "mcq":

        answer = st.radio(
            "Choose Answer",
            [
                question["option_a"],
                question["option_b"],
                question["option_c"],
                question["option_d"]
            ],
            key=question["id"]
        )

    else:

        st.info(f"Hint : {question['hint']}")

        answer = st.text_input(
            "Your Answer",
            key=question["id"]
        )

    st.session_state.answers[question["id"]] = answer

# =========================
# BUTTONS
# =========================

c1, c2, c3 = st.columns(3)

with c1:

    if st.button("Previous"):

        if current > 0:
            st.session_state.question_index -= 1
            st.rerun()

with c2:

    if st.button("Mark For Review"):

        if question["id"] not in st.session_state.marked:
            st.session_state.marked.append(question["id"])

with c3:

    if st.button("Next"):

        if current < total_questions - 1:
            st.session_state.question_index += 1
            st.rerun()

# =========================
# SUBMIT
# =========================

if current == total_questions - 1:

    if st.button("Submit Exam"):

        score = 0

        for q in questions:

            user_ans = st.session_state.answers.get(q["id"], "")

            if user_ans:

                if user_ans.strip().lower() == q["correct_answer"].strip().lower():
                    score += 1

        attempt_id = str(user_id)

        supabase.table("exam_attempts").insert({
            "id": attempt_id,
            "user_id": user_id,
            "exam_id": exam_id,
            "score": score,
            "submitted": True
        }).execute()

        for q in questions:

            supabase.table("user_answers").insert({
                "attempt_id": attempt_id,
                "question_id": q["id"],
                "answer": st.session_state.answers.get(q["id"], "")
            }).execute()

        st.success(f"Your Score : {score}/{total_questions}")

        exam = supabase.table("exams").select("*").eq(
            "id",
            exam_id
        ).execute().data[0]

        if exam["show_answers"]:

            st.subheader("Solutions")

            for q in questions:

                st.write(q["question"])
                st.success(f"Correct Answer : {q['correct_answer']}")

        st.stop()
