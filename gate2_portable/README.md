# Demo Gate 2: PriceSheet Normalizer (bản chạy riêng)

Web demo chạy trên máy bạn: nạp file báo giá Excel lộn xộn, ra bảng chuẩn 6 trường, hàng đợi duyệt, rồi file nhập khẩu MISA. Mọi thứ nằm trong thư mục này, không cần repo nào khác.

## Yêu cầu

- Python 3.12 hoặc 3.13
- Kết nối mạng ở lần chạy đầu để cài thư viện

## Chạy (3 bước)

1. Giải nén zip.
2. Windows: bấm đúp `run.bat` (tự tạo `.venv`, cài thư viện, mở trình duyệt).
3. Mở http://127.0.0.1:8765 nếu trình duyệt chưa tự mở.

Mac/Linux:

```bash
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -X utf8 server.py
```

Kiểm nhanh (server không cần chạy): `.venv\Scripts\python -X utf8 smoke.py` (Mac/Linux: `.venv/bin/python -X utf8 smoke.py`).

## Khóa OpenAI

Không bắt buộc. Không có khóa, demo vẫn chạy bằng luật (cảnh báo `LLM_UNAVAILABLE` khi chọn dùng mô hình). Muốn gọi mô hình: sao chép `.env.example` thành `.env` và điền `OPENAI_API_KEY=...`. Chỉ biến này được đọc; không đưa `.env` cho người khác.

## File mẫu (thư mục `samples`)

Tên có `cong_khai` là file công khai; `Bao_gia_mau` là file mẫu do nhóm tự tạo (một số dùng dữ liệu giá thuốc công khai làm nền, nhưng bố cục là tự dựng).

- P01: tiêu đề ở dòng 7, ghi chú ở cuối
- P02: tiêu đề lặp lại ở mỗi trang
- P03: tiêu đề 2 tầng, ô gộp, 2 cột giá
- P04: đơn vị nghìn đồng ghi trong tiêu đề
- P05: nhiều sheet, có sheet ẩn
- P06: dòng nhóm và cộng nhóm bằng công thức
- P07: giá dạng chữ kiểu Việt
- P11: file .xls cũ (97-2003)
- P12: 565 dòng, có dòng trùng y hệt
- P13: gộp nhiều bẫy (nhóm, tiêu đề lặp, giá nghìn, dòng ẩn)
- P14: tổng nhóm gõ sẵn, một nhóm lệch 1.000 đ
- P20 (công khai): kê khai giá thiết bị y tế (bơm tiêm), file gốc không sửa
- P21 (công khai): bảng giá thuốc của một bệnh viện, dán từ PDF
- L04: luật chưa chắc, gọi mô hình ở chế độ Luật trước
- L08: dòng nhóm, dòng tổng, giá Liên hệ, mã trùng
- F03: hai cột giá trước và sau VAT
- B06: PDF đổi đuôi thành .xlsx, phải báo mã lỗi `WRONG_FORMAT_PDF`

Có thể tải file riêng lên trang (tối đa 10 MB).

## Giới hạn

- Gọi mô hình cần khóa OpenAI và mạng. Một số máy Windows chặn DLL của thư viện `openai` (jiter); khi đó demo tự chuyển về luật.
- Lần mở tab File MISA đầu tiên mất khoảng 3 giây (nạp mẫu 5.001 dòng).
- Trạng thái nằm trong bộ nhớ, một người dùng, tắt server là mất.
- Đã thử file MISA tới bước Kiểm tra trên MISA eShop, chưa thử bước Nhập khẩu.
