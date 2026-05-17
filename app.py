# app.py

import streamlit as st
from supabase import create_client
import pandas as pd

# ---------------- SUPABASE CONFIG ----------------

SUPABASE_URL = "sb_publishable_YDD9XnJx26XgEwZWRd1jeA_dIArpaQs"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im50bWNsaXNqbW9oa2ZwZmlnd2p0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg5ODU0NzQsImV4cCI6MjA5NDU2MTQ3NH0.bcm2hEBzCsEBklLKpBVvYGxXsGWNHHOZJOXx0w3YQBc"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------- PAGE CONFIG ----------------

st.set_page_config(
    page_title="Learning Platform",
    layout="wide"
)

# ---------------- CUSTOM CSS ----------------

st.markdown("""
<style>
.main {
    background-color: #0E1117;
    color: white;
}

.stButton>button {
    width: 100%;
    border-radius: 10px;
    height: 45px;
    font-size: 16px;
    font-weight: bold;
}

.card {
    background-color: #1E1E1E;
    padding: 20px;
    border-radius: 15px;
    margin-bottom: 20px;
}

.title {
    font-size: 30px;
    font-weight: bold;
    color: #8B5CF6;
}
</style>
""", unsafe_allow_html=True)

# ---------------- LOGIN ----------------

st.sidebar.title("🔐 Login")

role = st.sidebar.selectbox("Select Role", ["User", "Admin"])

email = st.sidebar.text_input("Email")
password = st.sidebar.text_input("Password", type="password")

login_btn = st.sidebar.button("Login")

if login_btn:
    st.success(f"Logged in as {role}")

# ---------------- ADMIN PANEL ----------------

if role == "Admin":

    st.markdown('<p class="title">👨‍💼 Admin Dashboard</p>', unsafe_allow_html=True)

    menu = st.sidebar.radio(
        "Menu",
        ["Add Module", "Add Topic", "Add Session"]
    )

    # ---------- ADD MODULE ----------

    if menu == "Add Module":

        st.subheader("➕ Add Module")

        module_name = st.text_input("Module Name")

        if st.button("Save Module"):

            data = {
                "module_name": module_name
            }

            supabase.table("modules").insert(data).execute()

            st.success("Module Added Successfully!")

    # ---------- ADD TOPIC ----------

    elif menu == "Add Topic":

        st.subheader("➕ Add Topic")

        modules = supabase.table("modules").select("*").execute()

        module_list = {
            module['module_name']: module['id']
            for module in modules.data
        }

        selected_module = st.selectbox(
            "Select Module",
            list(module_list.keys())
        )

        topic_name = st.text_input("Topic Name")

        if st.button("Save Topic"):

            data = {
                "module_id": module_list[selected_module],
                "topic_name": topic_name
            }

            supabase.table("topics").insert(data).execute()

            st.success("Topic Added Successfully!")

    # ---------- ADD SESSION ----------

    elif menu == "Add Session":

        st.subheader("➕ Add Session")

        topics = supabase.table("topics").select("*").execute()

        topic_list = {
            topic['topic_name']: topic['id']
            for topic in topics.data
        }

        selected_topic = st.selectbox(
            "Select Topic",
            list(topic_list.keys())
        )

        day = st.text_input("Day")

        intro = st.text_area("Introduction")

        timing = st.text_input("Class Timing")

        meeting_link = st.text_input("Meeting Link")

        video_link = st.text_input("Recorded Video Link")

        exam_link = st.text_input("Exam Link")

        notes_link = st.text_input("Notes Link")

        if st.button("Save Session"):

            data = {
                "topic_id": topic_list[selected_topic],
                "day": day,
                "intro": intro,
                "timing": timing,
                "meeting_link": meeting_link,
                "video_link": video_link,
                "exam_link": exam_link,
                "notes_link": notes_link
            }

            supabase.table("sessions").insert(data).execute()

            st.success("Session Added Successfully!")

# ---------------- USER DASHBOARD ----------------

else:

    st.markdown('<p class="title">📚 Learning Dashboard</p>', unsafe_allow_html=True)

    modules = supabase.table("modules").select("*").execute()

    for module in modules.data:

        with st.expander(f"📘 {module['module_name']}"):

            topics = supabase.table("topics").select("*").eq(
                "module_id",
                module['id']
            ).execute()

            for topic in topics.data:

                st.markdown(f"### 🔹 {topic['topic_name']}")

                sessions = supabase.table("sessions").select("*").eq(
                    "topic_id",
                    topic['id']
                ).execute()

                for session in sessions.data:

                    st.markdown(f"""
                    <div class="card">
                    <h4>{session['day']}</h4>
                    <p>{session['intro']}</p>
                    <p>⏰ {session['timing']}</p>
                    </div>
                    """, unsafe_allow_html=True)

                    col1, col2, col3, col4 = st.columns(4)

                    with col1:
                        st.link_button(
                            "🎥 Join Class",
                            session['meeting_link']
                        )

                    with col2:
                        st.link_button(
                            "▶️ Recording",
                            session['video_link']
                        )

                    with col3:
                        st.link_button(
                            "📝 Exam",
                            session['exam_link']
                        )

                    with col4:
                        st.link_button(
                            "📄 Notes",
                            session['notes_link']
                        )

                    st.divider()