# =========================================================
# COMPLETE LMS + EXAM SYSTEM
# FILE: app.py
# =========================================================

import streamlit as st
from supabase import create_client

# =========================================================
# SUPABASE
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
    page_title="LMS",
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
# LOGIN / SIGNUP
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

            response = supabase.table(
                "users"
            ).select("*").eq(
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

    else:

        st.subheader("📝 Sign Up")

        name = st.text_input("Full Name")

        username = st.text_input("Username")

        password = st.text_input(
            "Password",
            type="password"
        )

        if st.button("Create Account"):

            existing = supabase.table(
                "users"
            ).select("*").eq(
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
                    "Account Created! Wait For Admin Approval"
                )

# =========================================================
# MAIN APP
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
    # ADMIN
    # =====================================================

    if st.session_state.role == "admin":

        st.title("👨‍💼 Admin Dashboard")

        menu = st.sidebar.radio(

            "Menu",

            [

                "Approve Users",

                "Add Module",
                "Delete Module",

                "Add Topic",
                "Delete Topic",

                "Add Session",
                "Delete Session",

                "Add Exam",
                "Delete Exam",

                "Add Question",
                "Delete Question",

                "User View"

            ]
        )

        # =================================================
        # APPROVE USERS
        # =================================================

        if menu == "Approve Users":

            pending = supabase.table(
                "users"
            ).select("*").eq(
                "status",
                "pending"
            ).execute()

            if pending.data:

                for user in pending.data:

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

            st.subheader("➕ Add Module")

            module_name = st.text_input(
                "Module Name"
            )

            if st.button("Save Module"):

                supabase.table("modules").insert({

                    "module_name": module_name

                }).execute()

                st.success("Module Added")

        # =================================================
        # DELETE MODULE
        # =================================================

        elif menu == "Delete Module":

            modules = supabase.table(
                "modules"
            ).select("*").execute()

            if modules.data:

                module_dict = {

                    module["module_name"]: module["id"]

                    for module in modules.data
                }

                selected = st.selectbox(
                    "Select Module",
                    list(module_dict.keys())
                )

                if st.button("Delete Module"):

                    supabase.table("modules").delete().eq(
                        "id",
                        module_dict[selected]
                    ).execute()

                    st.success("Deleted")

                    st.rerun()

        # =================================================
        # ADD TOPIC
        # =================================================

        elif menu == "Add Topic":

            modules = supabase.table(
                "modules"
            ).select("*").execute()

            if modules.data:

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
        # DELETE TOPIC
        # =================================================

        elif menu == "Delete Topic":

            topics = supabase.table(
                "topics"
            ).select("*").execute()

            if topics.data:

                topic_dict = {

                    topic["topic_name"]: topic["id"]

                    for topic in topics.data
                }

                selected = st.selectbox(
                    "Select Topic",
                    list(topic_dict.keys())
                )

                if st.button("Delete Topic"):

                    supabase.table("topics").delete().eq(
                        "id",
                        topic_dict[selected]
                    ).execute()

                    st.success("Deleted")

                    st.rerun()

        # =================================================
        # ADD SESSION
        # =================================================

        elif menu == "Add Session":

            topics = supabase.table(
                "topics"
            ).select("*").execute()

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
        # USER VIEW
        # =================================================

        elif menu == "User View":

            st.title("📘 User View Preview")

            modules = supabase.table(
                "modules"
            ).select("*").execute()

            if modules.data:

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

                        if topics.data:

                            for topic in topics.data:

                                st.markdown(
                                    f"## 🔹 {topic['topic_name']}"
                                )

                                sessions = supabase.table(
                                    "sessions"
                                ).select("*").eq(
                                    "topic_id",
                                    topic["id"]
                                ).execute()

                                if sessions.data:

                                    for session in sessions.data:

                                        st.markdown(f"""
                                        <div class="card">

                                        <h3>{session['day']}</h3>

                                        <p>{session['intro']}</p>

                                        <p>
                                        ⏰ {session['timing']}
                                        </p>

                                        </div>
                                        """, unsafe_allow_html=True)

    # =====================================================
    # USER DASHBOARD
    # =====================================================

    elif st.session_state.role == "user":

        st.title("📘 User Dashboard")

        modules = supabase.table(
            "modules"
        ).select("*").execute()

        if modules.data:

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

                    if topics.data:

                        for topic in topics.data:

                            st.markdown(
                                f"## 🔹 {topic['topic_name']}"
                            )

                            # ==========================
                            # SESSIONS
                            # ==========================

                            sessions = supabase.table(
                                "sessions"
                            ).select("*").eq(
                                "topic_id",
                                topic["id"]
                            ).execute()

                            if sessions.data:

                                st.subheader("🎥 Classes")

                                for session in sessions.data:

                                    st.markdown(f"""
                                    <div class="card">

                                    <h3>{session['day']}</h3>

                                    <p>{session['intro']}</p>

                                    <p>
                                    ⏰ {session['timing']}
                                    </p>

                                    </div>
                                    """, unsafe_allow_html=True)

                                    col1, col2, col3 = st.columns(3)

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
                                            "📄 Notes",
                                            session["notes_link"]
                                        )

                            else:

                                st.warning(
                                    "No Sessions Added"
                                )

                            # ==========================
                            # EXAMS
                            # ==========================

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

                                    <p>
                                    Duration:
                                    {exam['duration']} Minutes
                                    </p>

                                    </div>
                                    """, unsafe_allow_html=True)

                                    st.button(
                                        f"Start {exam['exam_name']}",
                                        key=f"exam_{exam['id']}"
                                    )

                            else:

                                st.warning(
                                    "No Exams Added"
                                )
