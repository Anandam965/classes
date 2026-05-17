# =========================================================
# app.py
# COMPLETE LMS + EXAM SYSTEM
# =========================================================

import streamlit as st
from supabase import create_client

# =========================================================
# SUPABASE
# =========================================================

SUPABASE_URL = "YOUR_SUPABASE_URL"
SUPABASE_KEY = "YOUR_SUPABASE_KEY"

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

    elif option == "Sign Up":

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
                    "Account Created! Wait for Admin Approval."
                )

# =========================================================
# MAIN SYSTEM
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

        st.markdown(
            '<p class="title">👨‍💼 Admin Dashboard</p>',
            unsafe_allow_html=True
        )

        menu = st.sidebar.radio(

            "Menu",

            [

                "Approve Users",

                "Add Module",
                "Edit Module",
                "Delete Module",

                "Add Topic",
                "Edit Topic",
                "Delete Topic",

                "Add Session",
                "Edit Session",
                "Delete Session",

                "Add Exam",
                "Delete Exam",

                "Add Question",
                "Delete Question",

                "Enable Answers",
                "Enable Solutions",

                "View Results",

                "User View"

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

            else:

                st.info("No Pending Users")

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
        # EDIT MODULE
        # =================================================

        elif menu == "Edit Module":

            st.subheader("✏️ Edit Module")

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

                    st.success("Module Updated")

                    st.rerun()

        # =================================================
        # DELETE MODULE
        # =================================================

        elif menu == "Delete Module":

            st.subheader("🗑️ Delete Module")

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

                if st.button("Delete Module"):

                    supabase.table("modules").delete().eq(

                        "id",

                        module_dict[selected_module]

                    ).execute()

                    st.success("Module Deleted")

                    st.rerun()

        # =================================================
        # ADD TOPIC
        # =================================================

        elif menu == "Add Topic":

            st.subheader("➕ Add Topic")

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
        # EDIT TOPIC
        # =================================================

        elif menu == "Edit Topic":

            st.subheader("✏️ Edit Topic")

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

            new_topic = st.text_input(
                "New Topic",
                value=selected_topic
            )

            if st.button("Update Topic"):

                supabase.table("topics").update({

                    "topic_name": new_topic

                }).eq(

                    "id",

                    topic_dict[selected_topic]

                ).execute()

                st.success("Topic Updated")

                st.rerun()

        # =================================================
        # DELETE TOPIC
        # =================================================

        elif menu == "Delete Topic":

            st.subheader("🗑️ Delete Topic")

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

            if st.button("Delete Topic"):

                supabase.table("topics").delete().eq(

                    "id",

                    topic_dict[selected_topic]

                ).execute()

                st.success("Topic Deleted")

                st.rerun()

        # =================================================
        # ADD SESSION
        # =================================================

        elif menu == "Add Session":

            st.subheader("➕ Add Session")

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
        # DELETE SESSION
        # =================================================

        elif menu == "Delete Session":

            st.subheader("🗑️ Delete Session")

            sessions = supabase.table(
                "sessions"
            ).select("*").execute()

            session_dict = {

                f"{session['day']} - {session['intro']}":
                session["id"]

                for session in sessions.data
            }

            selected_session = st.selectbox(

                "Select Session",

                list(session_dict.keys())

            )

            if st.button("Delete Session"):

                supabase.table("sessions").delete().eq(

                    "id",

                    session_dict[selected_session]

                ).execute()

                st.success("Session Deleted")

                st.rerun()

        # =================================================
        # USER VIEW
        # =================================================

        elif menu == "User View":

            st.subheader("📘 User View Preview")

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
