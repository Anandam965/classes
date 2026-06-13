        }).execute()
        # Send చేసిన తర్వాత automatically mark as read చేయాలి
        supabase.table("message_reads").upsert({
            "user_id": user_id,
            "last_read_at": "now()"
        }, on_conflict="user_id").execute()
        st.rerun()

    if mark_read:
        supabase.table("message_reads").upsert({
            "user_id": user_id,
            "last_read_at": "now()"
        }, on_conflict="user_id").execute()
        st.success("✅ అన్ని messages చదివినట్లు mark అయింది!")
        st.rerun()

# =========================
# USER ATTENDANCE
# =========================
def mark_today_attendance(user_id):
    """Mark one attendance entry per user per day."""
    today = date.today().isoformat()
    if st.session_state.get("attendance_marked_date") == today:
        return True

    try:
        supabase.table("attendance").upsert({
            "user_id": str(user_id),
            "attendance_date": today
        }, on_conflict="user_id,attendance_date").execute()
        st.session_state.attendance_marked_date = today
        return True
    except Exception as e:
        st.session_state.attendance_error = str(e)
        return False


def render_attendance_grid(user_id):
    today = date.today()
    start_day = today - timedelta(days=364)

    try:
        rows = supabase.table("attendance").select("attendance_date") \
            .eq("user_id", str(user_id)) \
            .gte("attendance_date", start_day.isoformat()) \
            .lte("attendance_date", today.isoformat()) \
            .execute().data
    except Exception as e:
        st.warning("Attendance table database lo create avvaledu. Admin SQL run chesi table create cheyyandi.")
        with st.expander("Attendance table SQL"):
            st.code("""
create table if not exists attendance (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  attendance_date date not null,
  created_at timestamptz default now(),
  unique(user_id, attendance_date)
);
""", language="sql")
        st.caption(f"Database error: {e}")
        return

    attended_days = {str(row.get("attendance_date")) for row in rows if row.get("attendance_date")}
    total_days = len(attended_days)

    streak = 0
    cursor = today
    while cursor.isoformat() in attended_days:
        streak += 1
        cursor -= timedelta(days=1)

    cols = st.columns(3)
    cols[0].metric("Total Attendance", total_days)
    cols[1].metric("Current Streak", streak)
    cols[2].metric("Today", "Marked" if today.isoformat() in attended_days else "Pending")

    days = [start_day + timedelta(days=i) for i in range(365)]
    weeks = [days[i:i + 7] for i in range(0, len(days), 7)]

    month_labels = []
    last_month = ""
    for week in weeks:
        label = week[0].strftime("%b") if week[0].day <= 7 else ""
        if label == last_month:
            label = ""
        if label:
            last_month = label
        month_labels.append(label)

    label_html = "".join(f"<span>{label}</span>" for label in month_labels)
    week_html = ""
    for week in weeks:
        cells = ""
        for day in week:
            day_key = day.isoformat()
            color = "#2ea043" if day_key in attended_days else "#ebedf0"
            title = f"{day.strftime('%d %b %Y')} - {'Present' if day_key in attended_days else 'Absent'}"
            cells += f"<div class='att-cell' title='{title}' style='background:{color}'></div>"
        week_html += f"<div class='att-week'>{cells}</div>"

    st.markdown(
        f"""
        <style>
            .attendance-card {{
                border: 1px solid #d0d7de;
                border-radius: 8px;
                padding: 16px;
                margin: 10px 0 24px 0;
                background: #ffffff;
            }}
            .attendance-title {{
                font-size: 1.15rem;
                font-weight: 700;
                margin-bottom: 4px;
            }}
            .attendance-subtitle {{
                color: #57606a;
                font-size: 0.9rem;
                margin-bottom: 14px;
            }}
            .att-months {{
                display: grid;
                grid-template-columns: repeat({len(weeks)}, 12px);
                gap: 3px;
                margin-bottom: 6px;
                font-size: 10px;
                color: #57606a;
            }}
            .att-grid {{
                display: flex;
                gap: 3px;
                overflow-x: auto;
                padding-bottom: 6px;
            }}
            .att-week {{
                display: grid;
                grid-template-rows: repeat(7, 12px);
                gap: 3px;
            }}
            .att-cell {{
                width: 12px;
                height: 12px;
                border-radius: 2px;
                border: 1px solid rgba(27, 31, 36, 0.06);
            }}
            .att-legend {{
                display: flex;
                align-items: center;
                gap: 6px;
                justify-content: flex-end;
                color: #57606a;
                font-size: 12px;
                margin-top: 8px;
            }}
        </style>
        <div class="attendance-card">
            <div class="attendance-title">Daily Attendance</div>
            <div class="attendance-subtitle">Login ayina rojulu green boxes ga kanipistayi.</div>
            <div class="att-months">{label_html}</div>
            <div class="att-grid">{week_html}</div>
            <div class="att-legend">
                <span>Less</span>
                <div class="att-cell" style="background:#ebedf0"></div>
                <div class="att-cell" style="background:#2ea043"></div>
                <span>More</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

# =========================
# USER DASHBOARD
# =========================
def user_dashboard(preview_mode=False):
    if not preview_mode:
        st.sidebar.title("User Workspace")
        if st.sidebar.button("🚪 Logout", use_container_width=True):
            for key in defaults:
                st.session_state[key] = defaults[key]
            st.query_params.clear()
            st.rerun()
        st.sidebar.divider()
        if "user_page" not in st.session_state:
            st.session_state.user_page = "📚 My Classes"
        if st.sidebar.button("📚 My Classes", use_container_width=True,
                             type="primary" if st.session_state.user_page == "📚 My Classes" else "secondary"):
            st.session_state.user_page = "📚 My Classes"
            st.rerun()
        unread = get_unread_count(st.session_state.user_id)
        chat_label = f"💬 Group Chat  🔴 {unread}" if unread > 0 else "💬 Group Chat"
        if st.sidebar.button(chat_label, use_container_width=True,
                             type="primary" if st.session_state.user_page == "💬 Group Chat" else "secondary"):
            st.session_state.user_page = "💬 Group Chat"
            st.rerun()
        user_page = st.session_state.user_page
    else:
        st.info("👁️ ఇది Student Preview Mode — student కి కనపడే view చూస్తున్నారు.")
        user_page = "📚 My Classes"

    # Notification banner — top లో చూపించాలి
    if not preview_mode:
        show_notification_banner(st.session_state.user_id)

    if user_page == "💬 Group Chat":
        group_chat()
        return

    if not preview_mode:
        mark_today_attendance(st.session_state.user_id)
        render_attendance_grid(st.session_state.user_id)

    modules = supabase.table("modules").select("*").execute().data

    # completed_ids ని session_state లో cache చేయడం — rerun లేకుండా local update చేయడానికి
    if st.session_state.completed_ids is None:
        all_completions = supabase.table("class_completions").select("class_id") \
            .eq("user_id", st.session_state.user_id).execute().data
        st.session_state.completed_ids = {str(c["class_id"]) for c in all_completions}
    completed_ids = st.session_state.completed_ids
    for module in modules:
        # Module లో total classes count చేయడం
        module_submodules = supabase.table("submodules").select("id").eq("module_id", module["id"]).execute().data
        sub_ids = [s["id"] for s in module_submodules]
        module_total = 0
        module_done = 0
        for sid in sub_ids:
            cls_list = supabase.table("classes").select("id").eq("submodule_id", sid).execute().data
            module_total += len(cls_list)
            module_done += sum(1 for c in cls_list if str(c["id"]) in completed_ids)

        pct = int((module_done / module_total * 100)) if module_total > 0 else 0
        expander_label = f"{module['title']}  —  {module_done}/{module_total} classes  ({pct}%)"

        with st.expander(expander_label):
            if module_total > 0:
                st.progress(pct / 100, text=f"Module Progress: {pct}% complete")
            submodules = supabase.table("submodules").select("*").eq("module_id", module["id"]).execute().data
            for sub in submodules:
                # Submodule progress
                sub_classes = supabase.table("classes").select("id").eq("submodule_id", sub["id"]).execute().data
                sub_total = len(sub_classes)
                sub_done = sum(1 for c in sub_classes if str(c["id"]) in completed_ids)
                sub_pct = int((sub_done / sub_total * 100)) if sub_total > 0 else 0

                st.subheader(f"{sub['title']}  ✅ {sub_done}/{sub_total}")
                if sub_total > 0:
                    st.progress(sub_pct / 100)
                classes = supabase.table("classes").select("*").eq("submodule_id", sub["id"]).execute().data
                for cls in classes:
