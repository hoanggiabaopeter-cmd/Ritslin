from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import re
import secrets
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from threading import Lock
from typing import Any

import qrcode
from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "students.db"
JWT_SECRET = "change-me-in-production"
JWT_ALG = "HS256"
JWT_EXPIRE_HOURS = 12
STUDENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{2,30}$")
PHONE_PATTERN = re.compile(r"^[0-9+\-\s]{8,20}$")

app = Flask(__name__)
_db_lock = Lock()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso_now() -> str:
    return utc_now().isoformat()


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("utf-8"))


def create_jwt(payload: dict[str, Any]) -> str:
    header = {"alg": JWT_ALG, "typ": "JWT"}
    header_b64 = b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    signature = hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{b64url_encode(signature)}"


def decode_jwt(token: str) -> dict[str, Any] | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None

    header_b64, payload_b64, signature_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    expected_sig = hmac.new(JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    got_sig = b64url_decode(signature_b64)

    if not hmac.compare_digest(expected_sig, got_sig):
        return None

    payload_raw = b64url_decode(payload_b64)
    payload = json.loads(payload_raw)

    exp = int(payload.get("exp", 0))
    if utc_now().timestamp() > exp:
        return None

    return payload


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def auth_required(role: str | None = None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return jsonify({"error": "Thiếu token."}), 401

            token = auth_header.removeprefix("Bearer ").strip()
            payload = decode_jwt(token)
            if not payload:
                return jsonify({"error": "Token không hợp lệ hoặc hết hạn."}), 401

            if role and payload.get("role") != role:
                return jsonify({"error": "Không đủ quyền."}), 403

            request.user = payload
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def init_db() -> None:
    with _db_lock, get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'teacher')),
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS students (
                id TEXT PRIMARY KEY,
                full_name TEXT NOT NULL,
                avatar_base64 TEXT,
                date_of_birth TEXT,
                parent_name TEXT,
                parent_phone TEXT,
                class_id INTEGER,
                qr_token TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(class_id) REFERENCES classes(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS attendance_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id TEXT NOT NULL,
                class_id INTEGER NOT NULL,
                attendance_date TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE,
                FOREIGN KEY(class_id) REFERENCES classes(id) ON DELETE CASCADE,
                UNIQUE(student_id, class_id, attendance_date)
            );
            """
        )

        admin = conn.execute("SELECT id FROM users WHERE username = ?", ("admin",)).fetchone()
        if not admin:
            conn.execute(
                "INSERT INTO users(username, password_hash, role, created_at) VALUES(?, ?, ?, ?)",
                ("admin", generate_password_hash("admin123"), "admin", utc_iso_now()),
            )
        conn.commit()


def parse_limit(raw_limit: str, default: int = 100) -> int:
    try:
        value = int(raw_limit)
    except (TypeError, ValueError):
        value = default
    return max(1, min(500, value))


def parse_student_qr(raw_text: str) -> str | None:
    text = (raw_text or "").strip()
    if not text:
        return None

    try:
        payload = json.loads(text)
        if payload.get("type") == "student" and isinstance(payload.get("token"), str):
            return payload["token"].strip() or None
    except json.JSONDecodeError:
        pass

    return text


def validate_student_payload(data: dict[str, Any]) -> tuple[bool, str]:
    student_id = str(data.get("id", "")).strip()
    full_name = str(data.get("full_name", "")).strip()
    parent_phone = str(data.get("parent_phone", "")).strip()

    if not STUDENT_ID_PATTERN.match(student_id):
        return False, "Mã học sinh không hợp lệ (2-30 ký tự, chữ/số/_/-)."
    if not full_name:
        return False, "Họ tên không được để trống."
    if parent_phone and not PHONE_PATTERN.match(parent_phone):
        return False, "SĐT phụ huynh không hợp lệ."

    avatar_base64 = str(data.get("avatar_base64", "")).strip()
    if avatar_base64:
        try:
            base64.b64decode(avatar_base64, validate=True)
        except Exception:
            return False, "Ảnh base64 không hợp lệ."

    return True, ""


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify({"status": "ok", "time": utc_iso_now()})


@app.post("/api/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    with get_connection() as conn:
        user = conn.execute(
            "SELECT id, username, password_hash, role FROM users WHERE username = ?", (username,)
        ).fetchone()

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Sai tài khoản hoặc mật khẩu."}), 401

    exp = utc_now() + timedelta(hours=JWT_EXPIRE_HOURS)
    token = create_jwt(
        {
            "sub": user["username"],
            "role": user["role"],
            "uid": user["id"],
            "exp": int(exp.timestamp()),
            "jti": secrets.token_hex(8),
        }
    )

    return jsonify(
        {
            "token": token,
            "expires_at": exp.isoformat(),
            "user": {"username": user["username"], "role": user["role"]},
        }
    )


@app.post("/api/users")
@auth_required(role="admin")
def create_user():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    role = str(data.get("role", "")).strip()

    if not username or len(password) < 6 or role not in {"admin", "teacher"}:
        return jsonify({"error": "Thông tin user không hợp lệ."}), 400

    try:
        with _db_lock, get_connection() as conn:
            conn.execute(
                "INSERT INTO users(username, password_hash, role, created_at) VALUES(?, ?, ?, ?)",
                (username, generate_password_hash(password), role, utc_iso_now()),
            )
            conn.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username đã tồn tại."}), 409

    return jsonify({"message": "Tạo tài khoản thành công."}), 201


@app.get("/api/classes")
@auth_required()
def list_classes():
    with get_connection() as conn:
        rows = conn.execute("SELECT id, name, created_at FROM classes ORDER BY name").fetchall()
    return jsonify([dict(row) for row in rows])


@app.post("/api/classes")
@auth_required()
def create_class():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify({"error": "Tên lớp không được để trống."}), 400

    try:
        with _db_lock, get_connection() as conn:
            conn.execute("INSERT INTO classes(name, created_at) VALUES(?, ?)", (name, utc_iso_now()))
            conn.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "Tên lớp đã tồn tại."}), 409

    return jsonify({"message": "Tạo lớp thành công."}), 201


@app.put("/api/classes/<int:class_id>")
@auth_required()
def update_class(class_id: int):
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify({"error": "Tên lớp không được để trống."}), 400

    with _db_lock, get_connection() as conn:
        row = conn.execute("UPDATE classes SET name = ? WHERE id = ?", (name, class_id))
        conn.commit()

    if row.rowcount == 0:
        return jsonify({"error": "Không tìm thấy lớp."}), 404
    return jsonify({"message": "Cập nhật lớp thành công."})


@app.delete("/api/classes/<int:class_id>")
@auth_required()
def delete_class(class_id: int):
    with _db_lock, get_connection() as conn:
        row = conn.execute("DELETE FROM classes WHERE id = ?", (class_id,))
        conn.commit()

    if row.rowcount == 0:
        return jsonify({"error": "Không tìm thấy lớp."}), 404
    return jsonify({"message": "Xóa lớp thành công."})


@app.get("/api/classes/<int:class_id>/students")
@auth_required()
def class_students(class_id: int):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.full_name, s.date_of_birth, s.parent_name, s.parent_phone, s.qr_token
            FROM students s
            WHERE s.class_id = ?
            ORDER BY s.full_name
            """,
            (class_id,),
        ).fetchall()

    return jsonify([dict(row) for row in rows])


@app.get("/api/students")
@auth_required()
def list_students():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.full_name, s.avatar_base64, s.date_of_birth, s.parent_name, s.parent_phone,
                   s.class_id, c.name AS class_name, s.qr_token, s.created_at
            FROM students s
            LEFT JOIN classes c ON c.id = s.class_id
            ORDER BY s.created_at DESC
            """
        ).fetchall()

    return jsonify([dict(row) for row in rows])


@app.post("/api/students")
@auth_required()
def create_student():
    data = request.get_json(silent=True) or {}
    ok, message = validate_student_payload(data)
    if not ok:
        return jsonify({"error": message}), 400

    student_id = str(data.get("id", "")).strip()
    class_id = data.get("class_id")
    class_id = int(class_id) if class_id not in (None, "") else None

    try:
        with _db_lock, get_connection() as conn:
            conn.execute(
                """
                INSERT INTO students(
                    id, full_name, avatar_base64, date_of_birth, parent_name, parent_phone, class_id, qr_token, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    student_id,
                    str(data.get("full_name", "")).strip(),
                    str(data.get("avatar_base64", "")).strip() or None,
                    str(data.get("date_of_birth", "")).strip() or None,
                    str(data.get("parent_name", "")).strip() or None,
                    str(data.get("parent_phone", "")).strip() or None,
                    class_id,
                    uuid.uuid4().hex,
                    utc_iso_now(),
                ),
            )
            conn.commit()
    except sqlite3.IntegrityError as exc:
        return jsonify({"error": f"Không thể tạo học sinh: {exc}"}), 409

    return jsonify({"message": "Tạo học sinh thành công."}), 201


@app.put("/api/students/<student_id>")
@auth_required()
def update_student(student_id: str):
    data = request.get_json(silent=True) or {}
    data["id"] = student_id
    ok, message = validate_student_payload(data)
    if not ok:
        return jsonify({"error": message}), 400

    class_id = data.get("class_id")
    class_id = int(class_id) if class_id not in (None, "") else None

    with _db_lock, get_connection() as conn:
        row = conn.execute(
            """
            UPDATE students
            SET full_name = ?, avatar_base64 = ?, date_of_birth = ?, parent_name = ?, parent_phone = ?, class_id = ?
            WHERE id = ?
            """,
            (
                str(data.get("full_name", "")).strip(),
                str(data.get("avatar_base64", "")).strip() or None,
                str(data.get("date_of_birth", "")).strip() or None,
                str(data.get("parent_name", "")).strip() or None,
                str(data.get("parent_phone", "")).strip() or None,
                class_id,
                student_id,
            ),
        )
        conn.commit()

    if row.rowcount == 0:
        return jsonify({"error": "Không tìm thấy học sinh."}), 404
    return jsonify({"message": "Cập nhật học sinh thành công."})


@app.delete("/api/students/<student_id>")
@auth_required()
def delete_student(student_id: str):
    with _db_lock, get_connection() as conn:
        row = conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
        conn.commit()

    if row.rowcount == 0:
        return jsonify({"error": "Không tìm thấy học sinh."}), 404
    return jsonify({"message": "Đã xóa học sinh."})


@app.get("/api/students/<student_id>/qrcode")
@auth_required()
def get_student_qr(student_id: str):
    with get_connection() as conn:
        student = conn.execute(
            "SELECT id, qr_token FROM students WHERE id = ?", (student_id,)
        ).fetchone()

    if not student:
        return jsonify({"error": "Không tìm thấy học sinh."}), 404

    payload = json.dumps(
        {"type": "student", "token": student["qr_token"], "id": student["id"]}, ensure_ascii=False
    )
    qr_image = qrcode.make(payload)
    buffer = io.BytesIO()
    qr_image.save(buffer, format="PNG")
    buffer.seek(0)
    return send_file(buffer, mimetype="image/png")


@app.post("/api/attendance/scan")
@auth_required()
def mark_attendance():
    data = request.get_json(silent=True) or {}
    qr_token = parse_student_qr(str(data.get("raw_text", "")))
    class_id = data.get("class_id")

    if not qr_token:
        return jsonify({"error": "Mã QR không hợp lệ."}), 400
    if class_id in (None, ""):
        return jsonify({"error": "Vui lòng chọn lớp trước khi điểm danh."}), 400

    class_id = int(class_id)
    attendance_date = str(data.get("attendance_date", "")).strip() or date.today().isoformat()

    with _db_lock, get_connection() as conn:
        student = conn.execute(
            "SELECT id, full_name, class_id FROM students WHERE qr_token = ?", (qr_token,)
        ).fetchone()
        if not student:
            return jsonify({"error": "Không tìm thấy học sinh theo QR."}), 404

        if student["class_id"] != class_id:
            return jsonify({"error": "Học sinh không thuộc lớp đã chọn."}), 409

        try:
            conn.execute(
                """
                INSERT INTO attendance_logs(student_id, class_id, attendance_date, timestamp)
                VALUES(?, ?, ?, ?)
                """,
                (student["id"], class_id, attendance_date, utc_iso_now()),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            return jsonify({"error": "Học sinh đã điểm danh hôm nay cho lớp này."}), 409

    return jsonify({"message": f"Điểm danh thành công: {student['full_name']}"})


@app.get("/api/attendance")
@auth_required()
def list_attendance():
    limit = parse_limit(request.args.get("limit", "100"))
    class_id = request.args.get("class_id")
    attendance_date = request.args.get("attendance_date")

    query = """
        SELECT l.id, l.student_id, s.full_name AS student_name, c.name AS class_name,
               l.class_id, l.attendance_date, l.timestamp
        FROM attendance_logs l
        JOIN students s ON s.id = l.student_id
        JOIN classes c ON c.id = l.class_id
    """
    where: list[str] = []
    params: list[Any] = []

    if class_id not in (None, ""):
        where.append("l.class_id = ?")
        params.append(int(class_id))
    if attendance_date:
        where.append("l.attendance_date = ?")
        params.append(attendance_date)

    if where:
        query += " WHERE " + " AND ".join(where)

    query += " ORDER BY l.timestamp DESC LIMIT ?"
    params.append(limit)

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return jsonify([dict(row) for row in rows])


@app.get("/api/attendance/stats")
@auth_required()
def attendance_stats():
    class_id = request.args.get("class_id")
    if class_id in (None, ""):
        return jsonify({"error": "Thiếu class_id."}), 400

    class_id = int(class_id)
    attendance_date = request.args.get("attendance_date") or date.today().isoformat()

    with get_connection() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM students WHERE class_id = ?", (class_id,)
        ).fetchone()[0]
        present = conn.execute(
            """
            SELECT COUNT(*)
            FROM attendance_logs
            WHERE class_id = ? AND attendance_date = ?
            """,
            (class_id, attendance_date),
        ).fetchone()[0]

    absent = max(total - present, 0)
    rate = round((present / total) * 100, 2) if total else 0.0

    return jsonify(
        {
            "class_id": class_id,
            "attendance_date": attendance_date,
            "total": total,
            "present": present,
            "absent": absent,
            "rate": rate,
        }
    )


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
