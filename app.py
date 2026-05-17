# app.py

import streamlit as st
from supabase import create_client

# ---------------- SUPABASE CONFIG ----------------

SUPABASE_URL = "https://ntmclisjmohkfpfigwjt.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im50bWNsaXNqbW9oa2ZwZmlnd2p0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg5ODU0NzQsImV4cCI6MjA5NDU2MTQ3NH0.bcm2hEBzCsEBklLKpBVvYGxXsGWNHHOZJOXx0w3YQBc"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------- PAGE CONFIG ----------------

st.set_page_config(
    page_title="Learning Management App",
    layout="wide"
)

# ---------------- CUSTOM CSS ----------------

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

# ---------------- SIDEBAR ----------------

st.sidebar.title("📚 Learning App")

role = st.sidebar.selectbox(
    "Select Role",
    ["User", "Admin"]
)

# ---------------- ADMIN PANEL ----------------

if role == "Admin":

    st.markdown(
        '<p class="title">👨‍💼 Admin Dashboard</p>',
        unsafe_allow_html=True
    )

    menu = st.sidebar.radio(
        "Menu",
        [
            "Add Module",
            "Edit Module",
            "Delete Module",
            "Add Topic",
            "Edit Topic",
            "Delete Topic",
            "Add Session",
            "Edit Session",
            "Delete Session"
        ]
    )

    # =====================================================
    # ADD MODULE
    # =====================================================

    if menu == "Add Module":

        st.subheader("➕ Add Module")

        module_name = st.text_input("Module Name")

        if st.button("Save Module"):

            supabase.table("modules").insert({
                "module_name": module_name
            }).execute()

            st.success("Module Added Successfully!")

    # =====================================================
    # EDIT MODULE
    # =====================================================

    elif menu == "Edit Module":

        st.subheader("✏️ Edit Module")

        modules = supabase.table("modules").select("*").execute()

        if modules.data:

            module_dict = {
                module["module_name"]: module["id"]
                for module in modules.data
            }

            selected_module = st.selectbox(
                "Select Module",
                list(module_dict.keys())
            )

            new_name = st.text_input(
                "New Module Name",
                value=selected_module
            )

            if st.button("Update Module"):

                supabase.table("modules").update({
                    "module_name": new_name
                }).eq(
                    "id",
                    module_dict[selected_module]
                ).execute()

                st.success("Module Updated!")

        else:
            st.warning("No Modules Found")

    # =====================================================
    # DELETE MODULE
    # =====================================================

    elif menu == "Delete Module":

        st.subheader("🗑️ Delete Module")

        modules = supabase.table("modules").select("*").execute()

        if modules.data:

            module_dict = {
                module["module_name"]: module["id"]
                for module in modules.data
            }

            selected_module = st.selectbox(
                "Select Module",
                list(module_dict.keys())
            )

            if st.button("Delete Module"):

                supabase.table("modules").delete().eq(
                    "id",
                    module_dict[selected_module]
                ).execute()

                st.success("Module Deleted!")

        else:
            st.warning("No Modules Found")

    # =====================================================
    # ADD TOPIC
    # =====================================================

    elif menu == "Add Topic":

        st.subheader("➕ Add Topic")

        modules = supabase.table("modules").select("*").execute()

        if modules.data:

            module_dict = {
                module["module_name"]: module["id"]
                for module in modules.data
            }

            selected_module = st.selectbox(
                "Select Module",
                list(module_dict.keys())
            )

            topic_name = st.text_input("Topic Name")

            if st.button("Save Topic"):

                supabase.table("topics").insert({
                    "module_id": module_dict[selected_module],
                    "topic_name": topic_name
                }).execute()

                st.success("Topic Added!")

        else:
            st.warning("Please Add Module First")

    # =====================================================
    # EDIT TOPIC
    # =====================================================

    elif menu == "Edit Topic":

        st.subheader("✏️ Edit Topic")

        topics = supabase.table("topics").select("*").execute()

        if topics.data:

            topic_dict = {
                topic["topic_name"]: topic["id"]
                for topic in topics.data
            }

            selected_topic = st.selectbox(
                "Select Topic",
                list(topic_dict.keys())
            )

            new_topic = st.text_input(
                "New Topic Name",
                value=selected_topic
            )

            if st.button("Update Topic"):

                supabase.table("topics").update({
                    "topic_name": new_topic
                }).eq(
                    "id",
                    topic_dict[selected_topic]
                ).execute()

                st.success("Topic Updated!")

        else:
            st.warning("No Topics Found")

    # =====================================================
    # DELETE TOPIC
    # =====================================================

    elif menu == "Delete Topic":

        st.subheader("🗑️ Delete Topic")

        topics = supabase.table("topics").select("*").execute()

        if topics.data:

            topic_dict = {
                topic["topic_name"]: topic["id"]
                for topic in topics.data
            }

            selected_topic = st.selectbox(
                "Select Topic",
                list(topic_dict.keys())
            )

            if st.button("Delete Topic"):

                supabase.table("topics").delete().eq(
                    "id",
                    topic_dict[selected_topic]
                ).execute()

                st.success("Topic Deleted!")

        else:
            st.warning("No Topics Found")

    # =====================================================
    # ADD SESSION
    # =====================================================

    elif menu == "Add Session":

        st.subheader("➕ Add Session")

        topics = supabase.table("topics").select("*").execute()

        if topics.data:

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

            timing = st.text_input("Class Timing")

            meeting_link = st.text_input("Meeting Link")

            video_link = st.text_input("Video Link")

            exam_link = st.text_input("Exam Link")

            notes_link = st.text_input("Notes Link")

            if st.button("Save Session"):

                supabase.table("sessions").insert({

                    "topic_id": topic_dict[selected_topic],
                    "day": day,
                    "intro": intro,
                    "timing": timing,
                    "meeting_link": meeting_link,
                    "video_link": video_link,
                    "exam_link": exam_link,
                    "notes_link": notes_link

                }).execute()

                st.success("Session Added!")

        else:
            st.warning("Please Add Topics First")

    # =====================================================
    # EDIT SESSION
    # =====================================================

    elif menu == "Edit Session":

        st.subheader("✏️ Edit Session")

        sessions = supabase.table("sessions").select("*").execute()

        if sessions.data:

            session_names = [
                f"{session['day']} - {session['intro']}"
                for session in sessions.data
            ]

            selected = st.selectbox(
                "Select Session",
                session_names
            )

            selected_index = session_names.index(selected)

            session_data = sessions.data[selected_index]

            new_day = st.text_input(
                "Day",
                value=session_data["day"]
            )

            new_intro = st.text_area(
                "Introduction",
                value=session_data["intro"]
            )

            new_timing = st.text_input(
                "Timing",
                value=session_data["timing"]
            )

            new_meeting = st.text_input(
                "Meeting Link",
                value=session_data["meeting_link"]
            )

            new_video = st.text_input(
                "Video Link",
                value=session_data["video_link"]
            )

            new_exam = st.text_input(
                "Exam Link",
                value=session_data["exam_link"]
            )

            new_notes = st.text_input(
                "Notes Link",
                value=session_data["notes_link"]
            )

            if st.button("Update Session"):

                supabase.table("sessions").update({

                    "day": new_day,
                    "intro": new_intro,
                    "timing": new_timing,
                    "meeting_link": new_meeting,
                    "video_link": new_video,
                    "exam_link": new_exam,
                    "notes_link": new_notes

                }).eq(
                    "id",
                    session_data["id"]
                ).execute()

                st.success("Session Updated!")

        else:
            st.warning("No Sessions Found")

    # =====================================================
    # DELETE SESSION
    # =====================================================

    elif menu == "Delete Session":

        st.subheader("🗑️ Delete Session")

        sessions = supabase.table("sessions").select("*").execute()

        if sessions.data:

            session_names = [
                f"{session['day']} - {session['intro']}"
                for session in sessions.data
            ]

            selected = st.selectbox(
                "Select Session",
                session_names
            )

            selected_index = session_names.index(selected)

            session_data = sessions.data[selected_index]

            if st.button("Delete Session"):

                supabase.table("sessions").delete().eq(
                    "id",
                    session_data["id"]
                ).execute()

                st.success("Session Deleted!")

        else:
            st.warning("No Sessions Found")

# ---------------- USER DASHBOARD ----------------

else:

    st.markdown(
        '<p class="title">📘 Learning Dashboard</p>',
        unsafe_allow_html=True
    )

    modules = supabase.table("modules").select("*").execute()

    if modules.data:

        for module in modules.data:

            with st.expander(f"📚 {module['module_name']}"):

                topics = supabase.table("topics").select("*").eq(
                    "module_id",
                    module["id"]
                ).execute()

                if topics.data:

                    for topic in topics.data:

                        st.markdown(f"## 🔹 {topic['topic_name']}")

                        sessions = supabase.table("sessions").select("*").eq(
                            "topic_id",
                            topic["id"]
                        ).execute()

                        if sessions.data:

                            for session in sessions.data:

                                st.markdown(f"""
                                <div class="card">
                                <h3>{session['day']}</h3>
                                <p>{session['intro']}</p>
                                <p>⏰ {session['timing']}</p>
                                </div>
                                """, unsafe_allow_html=True)

                                col1, col2, col3, col4 = st.columns(4)

                                with col1:
                                    st.link_button(
                                        "🎥 Join Class",
                                        session["meeting_link"]
                                    )

                                with col2:
                                    st.link_button(
                                        "▶️ Recording",
                                        session["video_link"]
                                    )

                                with col3:
                                    st.link_button(
                                        "📝 Exam",
                                        session["exam_link"]
                                    )

                                with col4:
                                    st.link_button(
                                        "📄 Notes",
                                        session["notes_link"]
                                    )

                                st.divider()

                        else:
                            st.info("No Sessions Available")

                else:
                    st.info("No Topics Available")

    else:
        st.warning("No Modules Found")
