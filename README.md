# 🎉 Ứng dụng quản lý học sinh bằng QR - MVP

Dự án này nâng cấp từ bản cũ, giữ nền Flask hiện tại nhưng đã bổ sung các chức năng MVP theo mô tả:

## ✅ Tính năng đã triển khai

### 1) Xác thực & phân quyền
- Đăng nhập theo tài khoản `admin` / `teacher`.
- JWT authentication (token HS256 tự ký).
- Admin tạo được tài khoản mới.
- Seed tài khoản mặc định: `admin / admin123`.

### 2) Quản lý học sinh
- Thêm / Sửa / Xóa học sinh.
- Lưu ảnh học sinh dạng base64.
- Thông tin: họ tên, ngày sinh, phụ huynh, SĐT phụ huynh.
- Mỗi học sinh có QR token unique.
- Sinh ảnh QR để in/chia sẻ.
- Gán học sinh vào lớp.

### 3) Quản lý lớp học
- Tạo / Sửa / Xóa lớp.
- Xem danh sách học sinh theo lớp.
- Có endpoint thống kê điểm danh real-time theo lớp/ngày.

### 4) Điểm danh QR
- Quét bằng camera trên web.
- Chọn lớp trước khi quét.
- Chống trùng: mỗi học sinh chỉ 1 lần / ngày / lớp.
- Thông báo kết quả điểm danh.

### 5) Theo dõi real-time
- Thống kê có mặt / vắng / tỷ lệ % theo lớp và ngày.

---

## Công nghệ
- Backend: Flask + SQLite
- Frontend: HTML/CSS/JS
- QR: `qrcode` + `html5-qrcode`

> Lưu ý: bản này làm **trên nền code hiện tại** theo yêu cầu, chưa chuyển sang FastAPI/MongoDB/Expo.

## Cài đặt

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Chạy

```bash
python3 app.py
```

Mở: `http://localhost:5000`

## API chính

### Auth/User
- `POST /api/auth/login`
- `POST /api/users` (admin)

### Classes
- `GET /api/classes`
- `POST /api/classes`
- `PUT /api/classes/<class_id>`
- `DELETE /api/classes/<class_id>`
- `GET /api/classes/<class_id>/students`

### Students
- `GET /api/students`
- `POST /api/students`
- `PUT /api/students/<student_id>`
- `DELETE /api/students/<student_id>`
- `GET /api/students/<student_id>/qrcode`

### Attendance
- `POST /api/attendance/scan`
- `GET /api/attendance`
- `DELETE /api/attendance`
- `GET /api/attendance/stats`

## Script desktop quét QR (tùy chọn)

File: `qr_attendance_tk.py`

```bash
pip install -r requirements_qr_tk.txt
python3 qr_attendance_tk.py
```
