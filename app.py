

from datetime import datetime, date

import pandas as pd
import streamlit as st


# ============================================================
# CONFIG
# ============================================================

st.set_page_config(
    page_title="Hotel Manager",
    page_icon="🏨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# MySQL / Aiven Cloud
DB_CONFIG = {
    "host": "mysql-3aSef2bc-binhquytoc.a.aivencloud.com",
    "port": 14483,
    "user": "avnadmin",
    "password": "AVNS_TX20BXmTGGjXba6p7j1",
    "database": "hotel_management",
    "autocommit": False,
    "connection_timeout": 15,
    "ssl_disabled": False,
}


# ============================================================
# DATABASE
# ============================================================

def get_connection():
    """Create a new MySQL connection to Aiven."""
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except Error as e:
        st.error(f"Không thể kết nối MySQL/Aiven: {e}")
        raise


def init_database():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rooms (
                id INT PRIMARY KEY AUTO_INCREMENT,
                room_number VARCHAR(50) UNIQUE NOT NULL,
                room_type VARCHAR(100) NOT NULL,
                price DECIMAL(15,2) NOT NULL DEFAULT 0,
                floor INT DEFAULT 1,
                status VARCHAR(100) NOT NULL DEFAULT 'Trống',
                note VARCHAR(500) DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id INT PRIMARY KEY AUTO_INCREMENT,
                full_name VARCHAR(100) NOT NULL,
                phone VARCHAR(50),
                email VARCHAR(255),
                id_number VARCHAR(100),
                address VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INT PRIMARY KEY AUTO_INCREMENT,
                customer_id INT NOT NULL,
                room_id INT NOT NULL,
                check_in DATE NOT NULL,
                check_out DATE NOT NULL,
                actual_check_in DATETIME,
                actual_check_out DATETIME,
                adults INT DEFAULT 1,
                children INT DEFAULT 0,
                total_amount DECIMAL(15,2) DEFAULT 0,
                status VARCHAR(30) DEFAULT 'Đã đặt',
                note VARCHAR(500) DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(customer_id) REFERENCES customers(id),
                FOREIGN KEY(room_id) REFERENCES rooms(id)
            )
        """)

        conn.commit()

        # Seed dữ liệu mẫu nếu chưa có phòng
        cursor.execute("SELECT COUNT(*) AS count FROM rooms")
        room_count = cursor.fetchone()["count"]

        if room_count == 0:
            sample_rooms = [
                ("101", "Standard", 500000, 1, "Trống", ""),
                ("102", "Standard", 500000, 1, "Trống", ""),
                ("103", "Deluxe", 750000, 1, "Trống", ""),
                ("201", "Deluxe", 750000, 2, "Trống", ""),
                ("202", "Deluxe", 750000, 2, "Trống", ""),
                ("203", "Suite", 1200000, 2, "Trống", ""),
                ("301", "Suite", 1500000, 3, "Trống", ""),
                ("302", "VIP", 2500000, 3, "Trống", ""),
            ]

            cursor.executemany("""
                INSERT INTO rooms
                (room_number, room_type, price, floor, status, note)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, sample_rooms)

            conn.commit()

    finally:
        cursor.close()
        conn.close()


# ============================================================
# UTILS
# ============================================================

def money(value):
    if value is None:
        value = 0
    return f"{value:,.0f} ₫"


def parse_date(value):
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def calculate_nights(check_in, check_out):
    days = (check_out - check_in).days
    return max(days, 1)


def execute_query(query, params=(), fetch=False, many=False):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        if many:
            cursor.executemany(query, params)
        else:
            cursor.execute(query, params)

        if fetch:
            return cursor.fetchall()

        conn.commit()
        return cursor.lastrowid

    except Exception:
        conn.rollback()
        raise

    finally:
        cursor.close()
        conn.close()


def query_df(query, params=()):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(query, params)
        rows = cursor.fetchall()
        columns = [column[0] for column in cursor.description] if cursor.description else []
        return pd.DataFrame(rows, columns=columns)

    finally:
        cursor.close()
        conn.close()


def set_room_status(room_id, status):
    execute_query(
        "UPDATE rooms SET status = %s WHERE id = %s",
        (status, room_id)
    )


def sync_room_status():
    """
    Đồng bộ trạng thái phòng dựa trên booking đang hoạt động.
    """
    today = date.today().isoformat()

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("SELECT id, status FROM rooms")
        rooms = cursor.fetchall()

        for room in rooms:
            cursor.execute("""
                SELECT id, status
                FROM bookings
                WHERE room_id = %s
                  AND status IN ('Đã đặt', 'Đang ở')
                  AND check_in <= %s
                  AND check_out > %s
                ORDER BY id DESC
                LIMIT 1
            """, (room["id"], today, today))

            active_booking = cursor.fetchone()

            if active_booking:
                if active_booking["status"] == "Đang ở":
                    new_status = "Đang ở"
                else:
                    new_status = "Đã đặt"

                cursor.execute(
                    "UPDATE rooms SET status = %s WHERE id = %s",
                    (new_status, room["id"])
                )

            else:
                # Không tự đổi phòng Đang dọn
                if room["status"] in ("Đã đặt", "Đang ở"):
                    cursor.execute(
                        "UPDATE rooms SET status = 'Trống' WHERE id = %s",
                        (room["id"],)
                    )

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        cursor.close()
        conn.close()


# ============================================================
# SIDEBAR
# ============================================================

def sidebar():
    st.sidebar.title("🏨 Hotel Manager")
    st.sidebar.caption("Hệ thống quản lý khách sạn")

    menu = st.sidebar.radio(
        "MENU",
        [
            "📊 Dashboard",
            "🛏️ Quản lý phòng",
            "📅 Đặt phòng",
            "👤 Khách hàng",
            "🧾 Lịch sử đặt phòng",
        ],
    )

    st.sidebar.divider()

    st.sidebar.info(
        "💡 Dữ liệu được lưu tự động trên MySQL/Aiven Cloud."
    )

    return menu


# ============================================================
# DASHBOARD
# ============================================================

def page_dashboard():
    st.title("📊 Dashboard")
    st.caption("Tổng quan hoạt động khách sạn")

    sync_room_status()

    rooms = query_df("""
        SELECT *
        FROM rooms
        ORDER BY CAST(room_number AS UNSIGNED)
    """)

    bookings = query_df("""
        SELECT
            b.*,
            r.room_number,
            r.room_type,
            c.full_name,
            c.phone
        FROM bookings b
        JOIN rooms r ON r.id = b.room_id
        JOIN customers c ON c.id = b.customer_id
        ORDER BY b.id DESC
    """)

    total_rooms = len(rooms)
    available = len(rooms[rooms["status"] == "Trống"])
    reserved = len(rooms[rooms["status"] == "Đã đặt"])
    occupied = len(rooms[rooms["status"] == "Đang ở"])
    cleaning = len(rooms[rooms["status"] == "Đang dọn"])

    today = date.today()

    today_bookings = (
        bookings[bookings["check_in"].apply(parse_date) == today]
        if not bookings.empty else pd.DataFrame()
    )

    today_checkouts = (
        bookings[bookings["check_out"].apply(parse_date) == today]
        if not bookings.empty else pd.DataFrame()
    )

    revenue = 0

    if not bookings.empty:
        completed = bookings[
            bookings["status"].isin(["Đã trả phòng", "Đã hoàn tất"])
        ]
        revenue = completed["total_amount"].fillna(0).sum()

    # KPI
    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("🏨 Tổng phòng", total_rooms)
    col2.metric("🟢 Phòng trống", available)
    col3.metric("🔵 Đang ở", occupied)
    col4.metric("🟠 Đã đặt", reserved)
    col5.metric("💰 Doanh thu", money(revenue))

    st.divider()

    left, right = st.columns([1.3, 1])

    with left:
        st.subheader("🛏️ Trạng thái phòng")

        if total_rooms > 0:
            status_df = pd.DataFrame({
                "Trạng thái": [
                    "Trống",
                    "Đã đặt",
                    "Đang ở",
                    "Đang dọn",
                ],
                "Số phòng": [
                    available,
                    reserved,
                    occupied,
                    cleaning,
                ],
            })

            st.bar_chart(
                status_df.set_index("Trạng thái")
            )

    with right:
        st.subheader("📅 Hoạt động hôm nay")

        st.metric(
            "Check-in hôm nay",
            len(today_bookings)
        )

        st.metric(
            "Check-out hôm nay",
            len(today_checkouts)
        )

    st.divider()

    st.subheader("📋 Booking gần đây")

    if bookings.empty:
        st.info("Chưa có booking.")
    else:
        display = bookings.head(10).copy()

        display = display[
            [
                "id",
                "room_number",
                "full_name",
                "phone",
                "check_in",
                "check_out",
                "status",
                "total_amount",
            ]
        ]

        display.columns = [
            "Mã",
            "Phòng",
            "Khách hàng",
            "Điện thoại",
            "Check-in",
            "Check-out",
            "Trạng thái",
            "Tổng tiền",
        ]

        display["Tổng tiền"] = display["Tổng tiền"].apply(money)

        st.dataframe(
            display,
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# ROOM MANAGEMENT
# ============================================================

def page_rooms():
    st.title("🛏️ Quản lý phòng")

    sync_room_status()

    rooms = query_df("""
        SELECT *
        FROM rooms
        ORDER BY floor, room_number
    """)

    # Filter
    col1, col2, col3 = st.columns(3)

    with col1:
        search = st.text_input(
            "🔍 Tìm phòng",
            placeholder="Ví dụ: 101"
        )

    with col2:
        type_filter = st.selectbox(
            "Loại phòng",
            ["Tất cả"] +
            sorted(rooms["room_type"].unique().tolist())
            if not rooms.empty else ["Tất cả"]
        )

    with col3:
        status_filter = st.selectbox(
            "Trạng thái",
            ["Tất cả", "Trống", "Đã đặt", "Đang ở", "Đang dọn"]
        )

    filtered = rooms.copy()

    if search:
        filtered = filtered[
            filtered["room_number"].astype(str).str.contains(
                search,
                case=False,
                na=False
            )
        ]

    if type_filter != "Tất cả":
        filtered = filtered[
            filtered["room_type"] == type_filter
        ]

    if status_filter != "Tất cả":
        filtered = filtered[
            filtered["status"] == status_filter
        ]

    # Add room
    with st.expander("➕ Thêm phòng mới"):
        with st.form("add_room_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)

            room_number = c1.text_input("Số phòng *")

            room_type = c2.selectbox(
                "Loại phòng",
                ["Standard", "Deluxe", "Suite", "VIP"]
            )

            price = c3.number_input(
                "Giá phòng / đêm",
                min_value=0,
                value=500000,
                step=50000,
            )

            c4, c5 = st.columns(2)

            floor = c4.number_input(
                "Tầng",
                min_value=1,
                max_value=100,
                value=1
            )

            note = c5.text_input("Ghi chú")

            submitted = st.form_submit_button(
                "💾 Thêm phòng",
                use_container_width=True
            )

            if submitted:
                if not room_number.strip():
                    st.error("Vui lòng nhập số phòng.")

                else:
                    try:
                        execute_query("""
                            INSERT INTO rooms
                            (room_number, room_type, price, floor, status, note)
                            VALUES (%s, %s, %s, %s, 'Trống', %s)
                        """, (
                            room_number.strip(),
                            room_type,
                            price,
                            floor,
                            note,
                        ))

                        st.success(
                            f"Đã thêm phòng {room_number}."
                        )

                        st.rerun()

                    except IntegrityError:
                        st.error(
                            "Số phòng đã tồn tại."
                        )

    st.divider()

    st.subheader(
        f"📋 Danh sách phòng ({len(filtered)})"
    )

    if filtered.empty:
        st.info("Không tìm thấy phòng.")
        return

    # Room cards
    cols = st.columns(4)

    status_icon = {
        "Trống": "🟢",
        "Đã đặt": "🟠",
        "Đang ở": "🔵",
        "Đang dọn": "🟡",
    }

    for index, room in filtered.iterrows():
        col = cols[index % 4]

        with col:
            st.markdown(
                f"""
                <div style="
                    border:1px solid #ddd;
                    border-radius:12px;
                    padding:16px;
                    margin-bottom:12px;
                    background:#ffffff;
                ">
                    <h3>🚪 Phòng {room['room_number']}</h3>
                    <p><b>Loại:</b> {room['room_type']}</p>
                    <p><b>Tầng:</b> {room['floor']}</p>
                    <p><b>Giá:</b> {money(room['price'])}/đêm</p>
                    <p><b>Trạng thái:</b>
                    {status_icon.get(room['status'], '⚪')}
                    {room['status']}
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            new_status = st.selectbox(
                "Trạng thái",
                [
                    "Trống",
                    "Đã đặt",
                    "Đang ở",
                    "Đang dọn",
                ],
                index=[
                    "Trống",
                    "Đã đặt",
                    "Đang ở",
                    "Đang dọn",
                ].index(room["status"]),
                key=f"status_{room['id']}",
            )

            if st.button(
                "Cập nhật",
                key=f"update_room_{room['id']}",
                use_container_width=True,
            ):
                set_room_status(
                    room["id"],
                    new_status
                )

                st.success("Đã cập nhật.")
                st.rerun()

            if st.button(
                "🗑️ Xóa",
                key=f"delete_room_{room['id']}",
                use_container_width=True,
            ):
                # Không cho xóa nếu có booking
                booking_count = execute_query(
                    """
                    SELECT COUNT(*) AS count
                    FROM bookings
                    WHERE room_id = %s
                    """,
                    (room["id"],),
                    fetch=True
                )[0]["count"]

                if booking_count > 0:
                    st.error(
                        "Không thể xóa vì phòng đã có lịch sử booking."
                    )

                else:
                    execute_query(
                        "DELETE FROM rooms WHERE id = %s",
                        (room["id"],)
                    )

                    st.success("Đã xóa phòng.")
                    st.rerun()


# ============================================================
# BOOKING
# ============================================================

def page_booking():
    st.title("📅 Đặt phòng / Check-in")

    rooms = query_df("""
        SELECT *
        FROM rooms
        WHERE status IN ('Trống', 'Đang dọn')
        ORDER BY room_number
    """)

    customers = query_df("""
        SELECT *
        FROM customers
        ORDER BY full_name
    """)

    if rooms.empty:
        st.warning(
            "Hiện không có phòng ở trạng thái Trống hoặc Đang dọn."
        )

    tab1, tab2 = st.tabs(
        ["➕ Tạo booking", "🔄 Check-in / Check-out"]
    )

    with tab1:

        with st.form("booking_form"):

            st.subheader("Thông tin khách hàng")

            c1, c2 = st.columns(2)

            full_name = c1.text_input(
                "Họ và tên *"
            )

            phone = c2.text_input(
                "Số điện thoại"
            )

            c3, c4 = st.columns(2)

            id_number = c3.text_input(
                "CCCD / Passport"
            )

            email = c4.text_input(
                "Email"
            )

            address = st.text_input(
                "Địa chỉ"
            )

            st.divider()

            st.subheader("Thông tin phòng")

            if not rooms.empty:
                room_options = {
                    f"{r.room_number} - {r.room_type} - {money(r.price)}/đêm":
                    int(r.id)
                    for _, r in rooms.iterrows()
                }

                selected_room_label = st.selectbox(
                    "Chọn phòng *",
                    list(room_options.keys())
                )

                selected_room_id = room_options[
                    selected_room_label
                ]

            else:
                selected_room_id = None

            c5, c6 = st.columns(2)

            check_in = c5.date_input(
                "Ngày check-in",
                value=date.today()
            )

            check_out = c6.date_input(
                "Ngày check-out",
                value=date.today()
            )

            c7, c8 = st.columns(2)

            adults = c7.number_input(
                "Người lớn",
                min_value=1,
                value=1
            )

            children = c8.number_input(
                "Trẻ em",
                min_value=0,
                value=0
            )

            note = st.text_area(
                "Ghi chú"
            )

            submitted = st.form_submit_button(
                "🏨 Tạo booking",
                use_container_width=True
            )

            if submitted:

                if not full_name.strip():
                    st.error(
                        "Vui lòng nhập tên khách hàng."
                    )

                elif selected_room_id is None:
                    st.error(
                        "Vui lòng chọn phòng."
                    )

                elif check_out <= check_in:
                    st.error(
                        "Ngày check-out phải sau ngày check-in."
                    )

                else:
                    # Tìm / tạo customer
                    existing = execute_query(
                        """
                        SELECT id
                        FROM customers
                        WHERE phone = %s
                          AND phone != ''
                        LIMIT 1
                        """,
                        (phone.strip(),),
                        fetch=True
                    )

                    if existing:
                        customer_id = existing[0]["id"]

                        execute_query("""
                            UPDATE customers
                            SET full_name = %s,
                                email = %s,
                                id_number = %s,
                                address = %s
                            WHERE id = %s
                        """, (
                            full_name.strip(),
                            email.strip(),
                            id_number.strip(),
                            address.strip(),
                            customer_id
                        ))

                    else:
                        customer_id = execute_query("""
                            INSERT INTO customers
                            (full_name, phone, email, id_number, address)
                            VALUES (%s, %s, %s, %s, %s)
                        """, (
                            full_name.strip(),
                            phone.strip(),
                            email.strip(),
                            id_number.strip(),
                            address.strip(),
                        ))

                    room = execute_query(
                        """
                        SELECT *
                        FROM rooms
                        WHERE id = %s
                        """,
                        (selected_room_id,),
                        fetch=True
                    )[0]

                    nights = calculate_nights(
                        check_in,
                        check_out
                    )

                    total = nights * room["price"]

                    execute_query("""
                        INSERT INTO bookings
                        (
                            customer_id,
                            room_id,
                            check_in,
                            check_out,
                            adults,
                            children,
                            total_amount,
                            status,
                            note
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        customer_id,
                        selected_room_id,
                        check_in.isoformat(),
                        check_out.isoformat(),
                        adults,
                        children,
                        total,
                        "Đã đặt",
                        note,
                    ))

                    set_room_status(
                        selected_room_id,
                        "Đã đặt"
                    )

                    st.success(
                        f"Đã tạo booking. Tổng tiền dự kiến: {money(total)}"
                    )

    with tab2:

        bookings = query_df("""
            SELECT
                b.id,
                b.status,
                b.check_in,
                b.check_out,
                b.actual_check_in,
                b.actual_check_out,
                b.adults,
                b.children,
                b.total_amount,
                b.note,
                r.id AS room_id,
                r.room_number,
                r.room_type,
                r.price,
                c.full_name,
                c.phone
            FROM bookings b
            JOIN rooms r ON r.id = b.room_id
            JOIN customers c ON c.id = b.customer_id
            WHERE b.status IN ('Đã đặt', 'Đang ở')
            ORDER BY b.check_in
        """)

        if bookings.empty:
            st.info(
                "Không có booking đang hoạt động."
            )

        else:

            for _, booking in bookings.iterrows():

                with st.container(border=True):

                    c1, c2, c3, c4 = st.columns(
                        [1, 2, 2, 1]
                    )

                    c1.markdown(
                        f"### 🚪 {booking['room_number']}"
                    )

                    c2.markdown(
                        f"""
                        **Khách:** {booking['full_name']}  
                        **SĐT:** {booking['phone'] or '-'}
                        """
                    )

                    c3.markdown(
                        f"""
                        **Check-in:** {booking['check_in']}  
                        **Check-out:** {booking['check_out']}  
                        **Trạng thái:** {booking['status']}
                        """
                    )

                    if booking["status"] == "Đã đặt":

                        if c4.button(
                            "🔑 Check-in",
                            key=f"checkin_{booking['id']}",
                            use_container_width=True,
                        ):
                            execute_query("""
                                UPDATE bookings
                                SET status = 'Đang ở',
                                    actual_check_in = %s
                                WHERE id = %s
                            """, (
                                datetime.now(),
                                booking["id"],
                            ))

                            set_room_status(
                                booking["room_id"],
                                "Đang ở"
                            )

                            st.success(
                                "Đã check-in khách."
                            )

                            st.rerun()

                    elif booking["status"] == "Đang ở":

                        if c4.button(
                            "🚪 Check-out",
                            key=f"checkout_{booking['id']}",
                            use_container_width=True,
                        ):
                            execute_query("""
                                UPDATE bookings
                                SET status = 'Đã trả phòng',
                                    actual_check_out = %s
                                WHERE id = %s
                            """, (
                                datetime.now(),
                                booking["id"],
                            ))

                            set_room_status(
                                booking["room_id"],
                                "Đang dọn"
                            )

                            st.success(
                                "Đã check-out. Phòng chuyển sang trạng thái Đang dọn."
                            )

                            st.rerun()


# ============================================================
# CUSTOMERS
# ============================================================

def page_customers():
    st.title("👤 Quản lý khách hàng")

    tab1, tab2 = st.tabs(
        ["📋 Danh sách khách hàng", "➕ Thêm khách hàng"]
    )

    with tab2:

        with st.form(
            "customer_form",
            clear_on_submit=True
        ):

            c1, c2 = st.columns(2)

            full_name = c1.text_input(
                "Họ và tên *"
            )

            phone = c2.text_input(
                "Số điện thoại"
            )

            c3, c4 = st.columns(2)

            id_number = c3.text_input(
                "CCCD / Passport"
            )

            email = c4.text_input(
                "Email"
            )

            address = st.text_area(
                "Địa chỉ"
            )

            submit = st.form_submit_button(
                "💾 Lưu khách hàng",
                use_container_width=True
            )

            if submit:

                if not full_name.strip():
                    st.error(
                        "Vui lòng nhập họ tên."
                    )

                else:
                    execute_query("""
                        INSERT INTO customers
                        (full_name, phone, email, id_number, address)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (
                        full_name.strip(),
                        phone.strip(),
                        email.strip(),
                        id_number.strip(),
                        address.strip(),
                    ))

                    st.success(
                        "Đã thêm khách hàng."
                    )

    with tab1:

        search = st.text_input(
            "🔍 Tìm kiếm khách hàng",
            placeholder="Tên hoặc số điện thoại"
        )

        customers = query_df("""
            SELECT *
            FROM customers
            ORDER BY id DESC
        """)

        if search:
            customers = customers[
                customers["full_name"].astype(str).str.contains(
                    search,
                    case=False,
                    na=False
                )
                |
                customers["phone"].astype(str).str.contains(
                    search,
                    case=False,
                    na=False
                )
            ]

        if customers.empty:
            st.info("Chưa có khách hàng.")

        else:
            display = customers[
                [
                    "id",
                    "full_name",
                    "phone",
                    "email",
                    "id_number",
                    "address",
                ]
            ].copy()

            display.columns = [
                "ID",
                "Họ tên",
                "Điện thoại",
                "Email",
                "CCCD/Passport",
                "Địa chỉ",
            ]

            st.dataframe(
                display,
                use_container_width=True,
                hide_index=True,
            )


# ============================================================
# BOOKING HISTORY
# ============================================================

def page_history():
    st.title("🧾 Lịch sử đặt phòng")

    bookings = query_df("""
        SELECT
            b.id,
            r.room_number,
            r.room_type,
            c.full_name,
            c.phone,
            b.check_in,
            b.check_out,
            b.actual_check_in,
            b.actual_check_out,
            b.adults,
            b.children,
            b.total_amount,
            b.status,
            b.note,
            b.created_at
        FROM bookings b
        JOIN rooms r ON r.id = b.room_id
        JOIN customers c ON c.id = b.customer_id
        ORDER BY b.id DESC
    """)

    if bookings.empty:
        st.info("Chưa có lịch sử booking.")
        return

    c1, c2 = st.columns(2)

    with c1:
        search = st.text_input(
            "🔍 Tìm khách/phòng"
        )

    with c2:
        status = st.selectbox(
            "Trạng thái",
            [
                "Tất cả",
                "Đã đặt",
                "Đang ở",
                "Đã trả phòng",
                "Đã hoàn tất",
            ]
        )

    filtered = bookings.copy()

    if search:
        mask = (
            filtered["full_name"]
            .astype(str)
            .str.contains(
                search,
                case=False,
                na=False
            )
            |
            filtered["room_number"]
            .astype(str)
            .str.contains(
                search,
                case=False,
                na=False
            )
            |
            filtered["phone"]
            .astype(str)
            .str.contains(
                search,
                case=False,
                na=False
            )
        )

        filtered = filtered[mask]

    if status != "Tất cả":
        filtered = filtered[
            filtered["status"] == status
        ]

    st.metric(
        "Số booking",
        len(filtered)
    )

    display = filtered[
        [
            "id",
            "room_number",
            "full_name",
            "phone",
            "check_in",
            "check_out",
            "adults",
            "children",
            "total_amount",
            "status",
        ]
    ].copy()

    display.columns = [
        "Mã booking",
        "Phòng",
        "Khách hàng",
        "Điện thoại",
        "Check-in",
        "Check-out",
        "Người lớn",
        "Trẻ em",
        "Tổng tiền",
        "Trạng thái",
    ]

    display["Tổng tiền"] = display["Tổng tiền"].apply(
        money
    )

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    st.subheader("💰 Thống kê doanh thu")

    completed = filtered[
        filtered["status"].isin(
            ["Đã trả phòng", "Đã hoàn tất"]
        )
    ]

    revenue = completed[
        "total_amount"
    ].fillna(0).sum()

    col1, col2 = st.columns(2)

    col1.metric(
        "Doanh thu từ kết quả lọc",
        money(revenue)
    )

    col2.metric(
        "Booking đã hoàn tất",
        len(completed)
    )


# ============================================================
# MAIN
# ============================================================

def main():

    try:
        init_database()
    except Error as e:
        st.error(
            "Không thể khởi tạo cơ sở dữ liệu MySQL/Aiven. "
            f"Chi tiết: {e}"
        )
        st.stop()

    menu = sidebar()

    if menu == "📊 Dashboard":
        page_dashboard()

    elif menu == "🛏️ Quản lý phòng":
        page_rooms()

    elif menu == "📅 Đặt phòng":
        page_booking()

    elif menu == "👤 Khách hàng":
        page_customers()

    elif menu == "🧾 Lịch sử đặt phòng":
        page_history()


if __name__ == "__main__":
    main()

