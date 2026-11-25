# Kịch bản quay demo 3 phút: PriceSheet Normalizer

**Luồng chính:** chủ nhà thuốc hoặc cửa hàng nhận file báo giá Excel lộn xộn từ nhà cung cấp → ra bảng chuẩn → duyệt → có file nhập khẩu MISA eShop dùng được ngay.

## Chuẩn bị trước khi bấm quay

1. Server chạy ở http://127.0.0.1:8765 (bấm đúp `gate2_portable\run.bat` nếu chưa chạy).
2. Mở sẵn trang và **chạy thử L08 một lần** cho nóng (tab File MISA lần đầu mất khoảng 3 giây).
3. Mở sẵn file `samples\P13_Bao_gia_mau_gop_nhieu_bay.xlsx` trong Excel ở một cửa sổ khác (dùng cho cảnh 1).
4. Mở sẵn trang MISA eShop (hoặc ảnh chụp màn hình lỗi "Tệp nhập khẩu không hợp lệ") nếu có.
5. Phóng to trình duyệt cỡ 110–125% để chữ đọc được trên video. Tắt thông báo Windows.
6. Thư mục Downloads trống cho dễ thấy file vừa tải.

---

## Cảnh 0: Pain point (0:00 – 0:25)

**Màn hình:** file P13 trong Excel (tiêu đề lặp, dòng nhóm, giá "65.000", dòng ẩn), rồi ảnh lỗi MISA.

**Lời thoại:**
> "Mỗi tháng nhà thuốc nhận hàng chục bảng giá Excel, mỗi nhà cung cấp một kiểu: tiêu đề lặp mỗi trang, dòng nhóm, giá ghi chữ kiểu '65.000'. MISA eShop từ chối cả file nếu không đúng mẫu 61 cột. Tệ hơn, nếu gõ '65.000' vào mẫu thì MISA hiểu thành 65 đồng mà không báo lỗi. Hiện tại phải gõ lại bằng tay."

## Cảnh 1: Input thật, xử lý thật (0:25 – 1:05)

**Thao tác:**
1. Bấm **Tải file lên**, chọn `P13_Bao_gia_mau_gop_nhieu_bay.xlsx` *(dùng upload thay vì danh sách mẫu để cho thấy hệ thống nhận file của người dùng)*.
2. Panel "File Excel đầu vào" hiện file gốc: chỉ chuột vào dòng nhóm, tiêu đề lặp, giá chữ.
3. Chế độ **Luật trước (mặc định)** → bấm **Chạy**.
4. Tab **Bảng chuẩn**: 6 trường (mã, tên, ĐVT, đơn giá, tiền tệ, hiệu lực). Bấm một dòng để thấy nó tô sáng ô gốc bên trái.

**Lời thoại:**
> "Tôi tải chính file đó lên. Hệ thống tự tìm dòng tiêu đề, ánh xạ cột, bỏ dòng nhóm và dòng ẩn, đổi '65.000' và giá nghìn đồng thành số. 226 dòng, 216 dòng hợp lệ, 10 dòng bị bỏ có lý do. Bấm vào dòng nào cũng truy được về ô gốc."

## Cảnh 2: Hàng đợi duyệt, con người quyết (1:05 – 1:55)

**Thao tác:**
1. Chọn mẫu **L08: Dòng nhóm, dòng tổng, giá Liên hệ, mã trùng** → **Chạy**.
2. Trạng thái `needs_review`: 274 ok, 30 cần xem, 11 bỏ.
3. Tab **Hàng đợi duyệt**: chỉ vào lý do `TRUNG_MA_KHAC_GIA` (cùng mã, khác giá).
4. Bấm **Giữ** một dòng, **Bỏ** một dòng → bảng chạy lại ngay (0 lần gọi mô hình).
5. (Tuỳ chọn) đổi cột giá trong ô **Chọn cột** để cho thấy người dùng sửa được ánh xạ.
6. Bấm **Duyệt**.

**Lời thoại:**
> "Với file có mã trùng khác giá, hệ thống không tự đoán mà đưa vào hàng đợi duyệt. Người xử lý chọn Giữ hoặc Bỏ, đổi cột giá nếu cần. Sửa xong chạy lại tức thì và không tốn lần gọi mô hình nào. Chỉ khi không còn mục chặn thì mới duyệt được."

## Cảnh 3: Output giải quyết pain point (1:55 – 2:30)

**Thao tác:**
1. Tab **File MISA**: xem trước tệp mẫu MISA đã điền.
2. Bấm **Tải ...misa_them_moi.xlsx** và **Tải báo cáo**.
3. Mở file vừa tải trong Excel: cột giá là ô số, đúng mẫu MISA.
4. *(Nếu có)* cắt 5 giây cảnh tải file này lên MISA eShop → bước Kiểm tra báo hợp lệ.

**Lời thoại:**
> "Kết quả là tệp nhập khẩu đúng mẫu MISA: giá ghi bằng ô số nên không bị hiểu sai 1.000 lần, dòng không mã hoặc giá 0 không lọt vào. Kèm báo cáo các dòng đã bỏ và lý do. File này đã qua bước Kiểm tra trên MISA eShop."

## Cảnh 4: Agent, ca lỗi, số đo (2:30 – 2:55)

**Thao tác (nhanh):**
1. Chọn **L04** → bỏ tick **Dùng cache** (để gọi mô hình thật, không lấy kết quả cũ) → **Chạy** → chỉ vào thông tin gọi mô hình (gpt-4o-mini, 1 lần gọi, khoảng $0.0003).
2. Chọn **B06** (PDF đổi đuôi) → Chạy → mã lỗi `WRONG_FORMAT_PDF`.
3. Mở panel **Số đo**: 55 file, tiêu đề 54/55, ánh xạ 262/266, giá trị ô 120.924/122.364.

**Lời thoại:**
> "Khi luật không chắc, agent mới gọi mô hình, nhưng mô hình chỉ đề xuất, người duyệt mới quyết. File sai định dạng bị báo lỗi rõ ràng. Trên 55 file kiểm thử, ánh xạ cột đúng 262 trên 266."

## Kết (2:55 – 3:00)

> "PriceSheet Normalizer: từ bảng giá lộn xộn đến file MISA trong dưới một phút, con người giữ quyền duyệt."

---

## Mẹo quay

- Dùng OBS hoặc Xbox Game Bar (`Win + G`) để quay. Thu tiếng riêng rồi ghép nếu nói vấp.
- Quay từng cảnh riêng rồi ghép, đừng cố quay một lần 3 phút.
- Nếu L04 gọi mô hình bị lỗi mạng thì hệ thống tự chuyển về luật và hiện `LLM_UNAVAILABLE`. Khi đó cắt cảnh này hoặc nói rõ là đang chạy bằng luật.
- Đừng quay màn hình có file `.env` hoặc khóa API.
