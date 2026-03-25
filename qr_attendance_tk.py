"""Ứng dụng điểm danh học sinh bằng quét QR (OpenCV + pyzbar + Tkinter).

Định dạng QR khuyến nghị:
    MaHS,Ten,Lop
Ví dụ:
    HS001,Nguyen Van A,10A1
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tkinter import Tk, Button, Label, messagebox

import cv2
import pandas as pd
from pyzbar.pyzbar import decode

CSV_COLUMNS = ["MaHS", "Ten", "Lop", "ThoiGian"]
CSV_PATH = Path("diemdanh.csv")


def ensure_csv_exists() -> None:
    """Tạo file CSV với đúng cột nếu file chưa tồn tại."""
    if not CSV_PATH.exists():
        pd.DataFrame(columns=CSV_COLUMNS).to_csv(CSV_PATH, index=False)


def load_attendance_df() -> pd.DataFrame:
    """Đọc dữ liệu điểm danh và tự sửa nếu file/cột lỗi."""
    ensure_csv_exists()
    df = pd.read_csv(CSV_PATH)

    missing_columns = [col for col in CSV_COLUMNS if col not in df.columns]
    if missing_columns:
        df = pd.DataFrame(columns=CSV_COLUMNS)
        df.to_csv(CSV_PATH, index=False)

    return df


def parse_qr_data(raw_data: str) -> tuple[str, str, str]:
    """Parse QR theo format MaHS,Ten,Lop.

    Raises:
        ValueError: nếu dữ liệu không hợp lệ.
    """
    parts = [part.strip() for part in raw_data.split(",")]
    if len(parts) != 3 or not all(parts):
        raise ValueError("QR phải có định dạng: MaHS,Ten,Lop")

    ma_hs, ten, lop = parts
    return ma_hs, ten, lop


def already_marked_today(df: pd.DataFrame, ma_hs: str, day_str: str) -> bool:
    """Kiểm tra học sinh đã điểm danh trong ngày chưa."""
    if df.empty:
        return False

    same_student = df["MaHS"].astype(str) == ma_hs
    same_day = df["ThoiGian"].astype(str).str.startswith(day_str)
    return bool((same_student & same_day).any())


def append_attendance(ma_hs: str, ten: str, lop: str) -> str:
    """Ghi điểm danh mới nếu chưa điểm danh trong ngày."""
    now = datetime.now()
    timestamp = now.strftime("%d-%m-%Y %H:%M:%S")
    day_str = now.strftime("%d-%m-%Y")

    df = load_attendance_df()
    if already_marked_today(df, ma_hs, day_str):
        raise RuntimeError("Học sinh đã điểm danh hôm nay!")

    new_row = pd.DataFrame(
        [{"MaHS": ma_hs, "Ten": ten, "Lop": lop, "ThoiGian": timestamp}]
    )
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(CSV_PATH, index=False)
    return timestamp


def scan_qr_once() -> None:
    """Mở camera, quét 1 mã QR và lưu điểm danh."""
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        messagebox.showerror("Lỗi", "Không mở được camera.")
        return

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                messagebox.showerror("Lỗi", "Không đọc được dữ liệu từ camera.")
                break

            decoded_items = decode(frame)
            for barcode in decoded_items:
                raw_data = barcode.data.decode("utf-8").strip()
                try:
                    ma_hs, ten, lop = parse_qr_data(raw_data)
                    append_attendance(ma_hs, ten, lop)
                    messagebox.showinfo("Thành công", f"Đã điểm danh: {ten} ({ma_hs})")
                except ValueError as exc:
                    messagebox.showerror("QR không hợp lệ", str(exc))
                except RuntimeError as exc:
                    messagebox.showwarning("Thông báo", str(exc))
                except Exception as exc:
                    messagebox.showerror("Lỗi", f"Không thể lưu điểm danh: {exc}")
                finally:
                    return

            cv2.imshow("Quet QR - Nhan Q de thoat", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


def build_ui() -> Tk:
    root = Tk()
    root.title("Quan Ly Hoc Sinh - Quet QR")
    root.geometry("420x260")

    label = Label(root, text="HE THONG DIEM DANH HOC SINH", font=("Arial", 14, "bold"))
    label.pack(pady=24)

    btn_scan = Button(root, text="Quet QR", command=scan_qr_once, height=2, width=22)
    btn_scan.pack(pady=12)

    btn_exit = Button(root, text="Thoat", command=root.quit, height=2, width=22)
    btn_exit.pack(pady=8)

    return root


def main() -> None:
    ensure_csv_exists()
    app = build_ui()
    app.mainloop()


if __name__ == "__main__":
    main()
