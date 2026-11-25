# Báo cáo kiểm thử AI agent trong PriceSheet Normalizer

Ngày chạy: 25/11/2026. Mô hình AI: gpt-4o-mini.

## Tóm tắt

- **AI giúp được ở những tiêu đề cột mơ hồ.** Khi tiêu đề không rõ nghĩa nhưng dữ liệu trong cột thì rõ, AI đoán đúng ý nghĩa của cột, còn luật thì không.
- **Phần lớn lợi ích đó viết lại được thành luật.** Sau khi cải tiến luật theo đúng cách AI suy luận (gọi là "luật v2"), bộ 100 file đạt kết quả bằng cách chạy dùng AI cho mọi file, mà không cần gọi AI lần nào.
- **Rủi ro lớn nhất còn lại là lỗi sai mà không báo.** Ở bộ khó, kể cả khi dùng AI cho mọi file, vẫn còn 290 dòng sai được coi là bình thường, trong đó 81 dòng sai giá. Phần lớn số này cần tool cảnh báo tốt hơn, chứ không cần AI giỏi hơn.

## Cách kiểm thử

**Hai bộ dữ liệu:**
- **Bộ 100 file:** 20 loại lỗi thường gặp, mỗi loại 5 biến thể, tổng 3.193 dòng hàng. Gồm: tiêu đề nằm sâu, tiêu đề lặp mỗi trang, ô gộp, dòng nhóm và dòng tổng, dòng ẩn, giá ghi bằng chữ ("65.000đ"), giá theo nghìn đồng, giá "Liên hệ", mã trùng, tên cột lạ, tiêu đề tiếng Anh, bố cục lạ, giá USD, và 5 file hỏng. Có 61 dòng "bẫy" mà tool phải chặn lại.
- **Bộ khó 33 file:** 11 loại, mỗi loại 3 biến thể, tổng 865 dòng hàng. Đây là các tình huống phải hiểu nghiệp vụ mới chọn đúng: giá cũ và giá mới, giá khuyến mãi, giá theo số lượng mua, mã và tên chung một ô, đơn vị tính nằm trong tên hàng, giá theo hộp và theo vỉ, tiêu đề tiếng Trung/Hàn/Nhật…

Đáp án của từng file được ghi ngay khi tạo file, độc lập với kết quả của tool. Mỗi dòng được chấm 5 thông tin: mã hàng, tên hàng, đơn vị tính, đơn giá, tiền tệ. Một dòng chỉ tính là đúng khi cả 5 thông tin đều đúng.

**Các cách chạy được so sánh:**
- **Chỉ luật:** không dùng AI.
- **Luật trước:** cách chạy mặc định của tool. Luật xử lý trước, chỉ gọi AI khi luật không chắc.
- **AI cho mọi file:** gọi AI cho tất cả các bảng.
- **Luật v2** và **Luật v2 + AI khi cần:** luật đã được cải tiến dựa trên những gì học được từ AI (xem phần 2).

## Kết quả tổng

| | Chỉ luật | Luật trước | AI cho mọi file | Luật v2 | Luật v2 + AI khi cần |
|---|---|---|---|---|---|
| Bộ 100: file đúng hoàn toàn | 94 | 96 | 97 | **97** | 97 |
| Bộ 100: dòng đúng hoàn toàn | 94,5% | 96,6% | 97,6% | **97,6%** | 97,6% |
| Bộ 100: dòng sai mà không báo | 99 | 33 | 0 | **0** | 0 |
| Bộ 100: file phải chờ người duyệt | 20 | 15 | 16 | 13 | 13 |
| Bộ 100: số lần gọi AI | 0 | 10 | 106 | **0** | 3 |
| Bộ 100: chi phí AI | 0 | 0,0026 USD | 0,0247 USD | 0 | 0,0008 USD |
| Bộ 100: tổng thời gian xử lý | 12 giây | 83 giây | 299 giây | 7 giây | 43 giây |
| Bộ khó: file đúng hoàn toàn | 5/33 | 10/33 | 10/33 | 5/33 | 10/33 |
| Bộ khó: dòng đúng hoàn toàn | 20,2% | 37,5% | 40,0% | 22,8% | 40,0% |
| Bộ khó: dòng sai mà không báo | 312 | 312 | 290 | 290 | 290 |
| Bộ khó: số lần gọi AI | 0 | 13 | 33 | 0 | 13 |

"Dòng sai mà không báo": dòng tool coi là bình thường (sẽ được đưa vào file MISA) nhưng sai ít nhất một thông tin, hoặc lẽ ra phải bị chặn. Đây là loại lỗi nguy hiểm nhất, vì không ai được báo để kiểm tra lại.

Ở bộ 100 file, phần cốt lõi đã ổn định ngay từ luật. Với cả 5 cách chạy:
- mọi dòng tool đọc được đều đúng mã, tên, đơn giá và tiền tệ;
- tool không lấy nhầm dòng nhóm hay dòng tổng;
- chặn đủ 61/61 dòng bẫy;
- báo đúng cả 5/5 file hỏng.

Các cách chạy chỉ khác nhau ở đơn vị tính. Khi được gọi, AI đề xuất đúng 415/419 lần.

---

## Phần 1. Những trường hợp luật sai mà AI đúng

### 1A. Bộ 100 file: 3 file, 99 dòng, cùng một nguyên nhân

Cả 3 file đều có cột đơn vị tính với tiêu đề viết tắt kèm dấu câu.

| File | Tiêu đề cột đơn vị tính | Chỉ luật | Có AI | Cách chạy AI sửa được |
|---|---|---|---|---|
| C17_2 | "Đ/v" (file có thêm cột Quy cách) | Mọi dòng ghi "Hộp", sai 30/35 dòng | Viên, Ống, Chai, Vỉ… đúng 35/35 | Luật trước, AI cho mọi file |
| C17_5 | "Đ/v" | Đơn vị tính trống, sai 36/36 dòng | Đúng 36/36 | Luật trước, AI cho mọi file |
| C15_5 | "Đ.vị" | Đơn vị tính trống ở 33/33 dòng, file vẫn báo bình thường | Đúng 33/33 | **Chỉ AI cho mọi file** |

**Vì sao luật sai:**
1. Luật không nhận ra "Đ/v" và "Đ.vị" là đơn vị tính, vì dấu gạch chéo và dấu chấm làm chữ viết tắt không khớp với các cách viết luật đã biết ("ĐVT", "Đơn vị tính", "ĐV").
2. Không thấy cột đơn vị tính, luật lấy chữ đầu của cột Quy cách làm đơn vị tính ("**Hộp** 3 vỉ x 10 viên"). Cách này chỉ đúng khi file thật sự không có cột đơn vị tính.
3. Tool không cảnh báo gì về đơn vị tính. Nó chỉ chuyển cho người duyệt khi cột *tên hàng* không chắc chắn.

**Vì sao AI đúng:** AI được xem cả tiêu đề lẫn vài dòng dữ liệu mẫu. Nó thấy cột có tiêu đề "Đ/v" chứa toàn những chữ ngắn như Viên, Hộp, Ống, Chai, lặp đi lặp lại, nên suy ra đây là cột đơn vị tính. Tool vẫn chuyển kết quả này cho người duyệt, vì đây là đề xuất của AI chứ luật không tự tìm ra.

**AI được gọi ở C17_2 là nhờ may.** Tool gọi AI vì cột tên hàng ("T.Hàng") không chắc chắn, chứ không phải vì phát hiện thiếu cột đơn vị tính. File C15_5 có cùng lỗi, nhưng cột tên đủ chắc chắn, nên AI không được gọi và 33 dòng thiếu đơn vị tính vẫn đi thẳng vào kết quả.

### 1B. Bộ 100 file: 5 file AI chỉ xác nhận lại

| File | Tiêu đề gây nghi ngờ | Tình trạng |
|---|---|---|
| C15_1, C15_2, C15_4, C18_4 | "Mặt hàng" | Luật không biết đây là tên hàng, nên đoán bằng cột chữ dài nhất. Đoán đúng nhưng không chắc chắn |
| C16_5 | "Price excl. VAT" | Luật chỉ nhận ra một phần, nên chưa đủ chắc chắn |

Luật vốn đã chọn đúng. AI xác nhận lại, nên người dùng không phải duyệt tay những file này.

### 1C. Bộ khó: AI sửa đúng 4 tình huống mà luật làm hỏng

| File | Tình huống | Chỉ luật | Có AI |
|---|---|---|---|
| H03 (3 file) | Giá chia theo số lượng mua: "SL 1-9 / SL 10-49 / SL từ 50" | Báo lỗi không tìm thấy cột giá, vì luật coi mọi cột giá theo số lượng là cột phụ | Chọn đúng giá mua lẻ, 76/76 dòng |
| H09_2, H09_3 | Cột giá có tiêu đề "VNĐ" hoặc "(5)" | Báo lỗi không tìm thấy cột giá | AI nhận ra cột giá vì toàn là số tiền, 45/45 dòng |
| H11_1 | Tiêu đề viết trên 2 dòng, không gộp ô ("Đơn" ở dòng trên, "giá" ở dòng dưới) | Báo lỗi không tìm thấy cột giá | Đúng 28/28 dòng |
| H11_3 | Tiêu đề 2 dòng, cột đơn vị tính ghi "Đ.vị" | Đơn vị tính trống, 22 dòng sai mà không báo | Đúng 22/22 dòng |

**Điểm chung:** AI làm tốt hơn khi **tiêu đề không rõ nghĩa nhưng dữ liệu thì rõ**, chẳng hạn cột toàn số tiền, hay cột toàn chữ đơn vị. Luật chỉ đọc chữ ở tiêu đề; AI đọc được cả tiêu đề, dữ liệu và ngữ cảnh xung quanh.

---

## Phần 2. Luật v2: viết lại cách AI suy luận thành luật

### Ba cải tiến

1. **Bổ sung các cách gọi tên cột còn thiếu:** "Mặt hàng", "T.Hàng" cho tên hàng; "Price excl. VAT", "Net price", "Giá phân phối" cho đơn giá; "Đ.vị" cho đơn vị tính.
2. **Hiểu tiêu đề viết tắt có dấu câu:** "Đ/v", "Đ.vị" được hiểu là đơn vị tính.
3. **Nhận cột đơn vị tính qua nội dung:** nếu tiêu đề không rõ nhưng cột toàn những chữ như Viên, Hộp, Chai, Ống, thì đó là cột đơn vị tính. Đây chính là cách AI đã suy luận.

### Kết quả đo được

- Bộ 100 file, **chỉ dùng luật v2, không gọi AI**: 97/100 file đúng hoàn toàn, 0 dòng sai mà không báo. Bằng đúng cách chạy dùng AI cho mọi file.
- Không file nào bị kém đi so với luật cũ, kể cả 17 file mẫu có sẵn trong demo.
- Ở cách chạy mặc định, số lần gọi AI giảm từ **10 xuống 3**. 3 lần còn lại không làm thay đổi kết quả.
- Số file phải chờ người duyệt giảm từ 20 xuống 13.
- Ở bộ khó, luật v2 sửa thêm được 22 dòng. Các tình huống còn lại vẫn cần AI hoặc cần cách xử lý mới (phần 3).
- Luật v2 đã được đưa vào bản demo thành một lựa chọn riêng, đặt cạnh cách chạy mặc định để so sánh trực tiếp.

### Các cải tiến tiếp theo (chưa thử)

| Cải tiến | Tình huống liên quan | Hiệu quả dự kiến |
|---|---|---|
| Không gọi AI khi hai cột giá là cặp "chưa VAT / có VAT" rõ ràng; luật đã chọn đúng giá chưa VAT | C05_2, C05_3 | Bớt 2 lần gọi AI |
| Nhận ra hai bảng giống nhau đặt cạnh nhau trên một sheet và tách làm hai | C18_3 | Bớt 1 lần gọi AI, lấy lại 18 dòng bị mất |
| Hiểu tiêu đề giá theo số lượng mua ("SL 1-9", "Mua lẻ") và tiêu đề viết trên 2 dòng | H03, H11 | Luật tự xử lý, không cần AI |

### Về chi phí

Tiền AI vốn rất nhỏ, khoảng 0,00025 USD mỗi file. Lợi ích thật của việc giảm gọi AI là:
- **Tốc độ:** với bộ 100 file, luật v2 chạy hết 7 giây, cách mặc định 83 giây, dùng AI cho mọi file 299 giây.
- **Ổn định:** không phụ thuộc kết nối mạng, và chạy lại luôn cho cùng kết quả.

**Cách làm nên giữ:** mỗi khi thấy AI làm đúng mà luật sai, hãy viết lại cách AI suy luận thành luật. AI chỉ nên dành cho những trường hợp thật sự mơ hồ.

---

## Phần 3. Những trường hợp AI vẫn sai

Nhóm đã xem lại từng trường hợp, so sánh câu trả lời của AI với kết quả cuối cùng của tool. Kết quả cho thấy có 3 nhóm nguyên nhân khác nhau.

### Nhóm 1: AI chọn sai

| File | Tình huống | AI chọn | Hậu quả |
|---|---|---|---|
| H01 (3 file) | Có hai cột "Giá cũ" và "Giá mới", kèm dòng ghi chú "Điều chỉnh giá từ 01/12/2026" | **Giá cũ** (luật cũng chọn giá cũ) | **60 dòng sai giá, tool không cảnh báo gì** |
| H06 (3 file) | Hai cột giá: một theo hộp, một theo vỉ | Trả lời lộn xộn, gán một cột cho nhiều thông tin; tool đã tự loại câu trả lời này | Mất giá theo vỉ, đơn vị tính bị trống |

AI chỉ được hướng dẫn chọn giá trước thuế, không chọn giá khuyến mãi; hướng dẫn không nói gì về giá cũ và giá mới. Trong trường hợp này, AI chọn cột giá đứng trước.

**Hướng xử lý:**
1. Bổ sung luật: khi có cột "cũ / trước điều chỉnh" và cột "mới / sau điều chỉnh", ưu tiên cột mới.
2. Hướng dẫn rõ cho AI: nếu có giá cũ và giá mới thì chọn giá mới.
3. **Quan trọng nhất:** khi có từ 2 cột giá trở lên mà không phải cặp "chưa VAT / có VAT", luôn chuyển cho người duyệt chọn và hiện cả hai cột. Sai giá là lỗi gây thiệt hại lớn nhất, nên tool không được tự chọn mà không báo.

### Nhóm 2: AI trả lời đúng, nhưng tool không dùng

| File | Tình huống | Vì sao câu trả lời đúng bị bỏ | Hướng xử lý |
|---|---|---|---|
| H02_2 | Cột "Giá ưu đãi" đứng trước cột "Giá gốc". AI chọn **Giá gốc**, là đáp án đúng | Luật hiểu "giá gốc" là **giá vốn** (giá nhập), nên loại cột này và loại luôn câu trả lời của AI. Luật cũng không biết "ưu đãi" là khuyến mãi, nên chọn cột Giá ưu đãi. Kết quả: **21 dòng sai giá, không cảnh báo**. Ở file cùng loại H02_3 (tiêu đề "Đơn giá khuyến mại" và "Đơn giá"), tool chọn đúng vì nhận ra chữ "khuyến mại" | Bổ sung "ưu đãi", "giảm giá" vào nhóm giá khuyến mãi. Chỉ hiểu "giá gốc" là giá vốn khi bên cạnh không có cột khuyến mãi. Khi tool bỏ câu trả lời của AI về cột giá thì phải chuyển cho người duyệt |
| H09_1 | Cột giá không có tiêu đề. AI chọn đúng cột giá | Tool chỉ xét những cột có tiêu đề, nên coi cột giá là "nằm ngoài bảng" và bỏ qua | Xét cả những cột liền kề có dữ liệu, dù tiêu đề trống |
| H10 (3 file) | Tiêu đề tiếng Trung, Hàn, Nhật | Tool chỉ nhận dòng tiêu đề có tên cột tiếng Việt hoặc tiếng Anh, nên báo không tìm thấy tiêu đề, dù đã hỏi AI | Bổ sung các cách gọi tên cột bằng các thứ tiếng này. Chấp nhận dòng tiêu đề do AI chỉ ra nếu dữ liệu khớp |

### Nhóm 3: vượt ngoài phạm vi thiết kế hiện tại

Hiện tại AI chỉ được chỉ ra "cột nào là thông tin gì", không được sửa hay tách nội dung trong ô. Đây là thiết kế đúng về an toàn, vì AI không thể bịa ra giá. Nhưng vì vậy, các trường hợp sau không xử lý được:

| File | Tình huống | Kết quả với mọi cách chạy |
|---|---|---|
| H04 (3 file) | Mã và tên viết chung một ô: "TH1000 - Ibuprofen 400mg" | Mã hàng trống, tên hàng lẫn cả mã (tool có chuyển cho người duyệt) |
| H05 (3 file) | Đơn vị tính nằm trong tên: "Bông y tế 100g (Gói)" | Đơn vị tính trống, **69 dòng không cảnh báo** |
| H07 (3 file) | Đơn vị tính nằm trong tiêu đề giá: "Đơn giá (đ/viên)" | Đơn vị tính trống, **71 dòng không cảnh báo** |
| H06 (3 file) | Giá theo hộp và theo vỉ trên cùng một dòng | Mất giá theo vỉ |
| C18_3 | Hai bảng đặt cạnh nhau trên cùng một sheet | Mất 18 dòng của bảng bên phải, **không cảnh báo** |
| C17_3, C18_1 | Tiêu đề là "Cột 1, Cột 2…", hoặc không có tiêu đề | Tool báo lỗi rõ ràng (an toàn) |

**Hướng xử lý:** chuẩn bị sẵn một số cách tách dữ liệu đáng tin cậy:
- tách mã hàng ra khỏi tên hàng;
- lấy đơn vị tính từ đuôi tên hàng, ví dụ "(Hộp)";
- lấy đơn vị tính từ tiêu đề giá, ví dụ "đ/viên";
- tách giá theo hộp và giá theo vỉ thành hai dòng hàng.

Khi chắc chắn, luật tự áp dụng. Khi không chắc, AI chỉ được chọn cách tách phù hợp, không được tự viết ra giá trị. Như vậy vẫn giữ được nguyên tắc an toàn hiện tại.

---

## Đề xuất, theo thứ tự ưu tiên

1. **Ưu tiên cao nhất: chặn các lỗi sai mà không báo.** Việc này không cần AI, chỉ cần tool cảnh báo tốt hơn. Chuyển cho người duyệt khi:
   - đơn vị tính bị trống ở hơn một nửa số dòng (bắt được H05, H07);
   - trên sheet còn một bảng khác nằm ngoài vùng tool đã đọc (bắt được C18_3);
   - có từ 2 cột giá trở lên mà không phải cặp "chưa VAT / có VAT", hoặc AI và luật chọn khác cột giá (bắt được H01, H02_2).
2. **Dùng luật v2 làm mặc định** sau khi nhóm xem xét. Kết quả đo được: bộ 100 file đạt mức như dùng AI cho mọi file, mà không cần gọi AI.
3. **Sửa những chỗ tool đang bỏ qua câu trả lời đúng của AI** (nhóm 2): cách hiểu "giá gốc", cột giá không có tiêu đề, tiêu đề tiếng nước ngoài.
4. **Bổ sung các cách tách dữ liệu có sẵn, để AI chọn** (nhóm 3).
5. **Bỏ nốt những lần gọi AI không cần thiết:** khi hai cột giá là cặp "chưa VAT / có VAT" rõ ràng, và khi một sheet có hai bảng giống nhau đặt cạnh nhau.
6. **Giữ nguyên cách làm "luật trước, AI khi cần".** AI nên dành cho những trường hợp thật sự mơ hồ.
