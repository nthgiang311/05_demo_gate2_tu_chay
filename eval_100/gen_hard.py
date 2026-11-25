"""Bộ khó: 11 loại x 3 biến thể, nhắm vào chỗ cần hiểu nghiệp vụ (nơi AI phải phán đoán).
Ra hard/files và hard/gold, cùng định dạng đáp án với gen.py.
Chạy: ..\\gate2_portable\\.venv\\Scripts\\python -X utf8 gen_hard.py
"""
import os
import random
import shutil
from decimal import Decimal

import gen
from gen import Book, TITLES, make_items, title_block, write_table

HERE = os.path.dirname(os.path.abspath(__file__))
gen.FILES = os.path.join(HERE, "hard", "files")
gen.GOLD = os.path.join(HERE, "hard", "gold")
GC = {"ma": "ma_hang", "ten": "ten_hang", "dv": "don_vi", "gia": "don_gia"}


def h01(bk, rnd, v):  # giá cũ / giá mới: phải lấy giá mới
    ws = bk.sheet("BG")
    top = title_block(ws, TITLES + ["Điều chỉnh giá từ ngày 01/12/2026", ""])
    items = make_items(rnd, rnd.randrange(20, 30))
    for it in items:
        it.gia_cu = int(it.gia * rnd.choice([0.9, 0.95, 1.0, 1.05]))
    names = [("Giá cũ", "Giá mới"), ("Giá trước điều chỉnh", "Giá sau điều chỉnh"), ("Đơn giá cũ", "Đơn giá mới (từ 01/12)")][v]
    write_table(bk, ws, top, ["stt", "ma", "ten", "dv", "gia_cu", "gia"], items,
                hdr_over={"gia_cu": names[0], "gia": names[1]})


def h02(bk, rnd, v):  # giá khuyến mãi đứng trước giá niêm yết: phải lấy niêm yết
    ws = bk.sheet("BG")
    top = title_block(ws, TITLES + ["Chương trình khuyến mãi tháng 12", ""])
    names = [("Giá KM", "Giá niêm yết"), ("Giá ưu đãi", "Giá gốc"), ("Đơn giá khuyến mại", "Đơn giá")][v]
    write_table(bk, ws, top, ["stt", "ma", "ten", "dv", "gia_km", "gia"], make_items(rnd, rnd.randrange(20, 30)),
                hdr_over={"gia_km": names[0], "gia": names[1]})


def h03(bk, rnd, v):  # giá theo bậc số lượng: lấy bậc đầu
    ws = bk.sheet("BG")
    top = title_block(ws, TITLES)
    items = make_items(rnd, rnd.randrange(20, 30))
    for it in items:
        it.gia_t2, it.gia_t3 = int(it.gia * 0.95), int(it.gia * 0.9)
    names = [("SL 1-9", "SL 10-49", "SL >= 50"), ("Mua lẻ", "Mua từ 10", "Mua từ 50"), ("Giá 1 hộp", "Giá 10 hộp+", "Giá thùng")][v]
    write_table(bk, ws, top, ["stt", "ma", "ten", "dv", "gia", "gia_t2", "gia_t3"], items,
                hdr_over={"gia": names[0], "gia_t2": names[1], "gia_t3": names[2]},
                two_level={"Đơn giá theo số lượng": ["gia", "gia_t2", "gia_t3"]})


def h04(bk, rnd, v):  # mã và tên chung một ô
    ws = bk.sheet("BG")
    top = title_block(ws, TITLES)
    items = make_items(rnd, rnd.randrange(20, 30))
    sep = [" - ", " | ", "  "][v]
    real = [(it.ma, it.ten) for it in items]
    for it in items:
        it.ten = f"{it.ma}{sep}{it.ten}" if v < 2 else f"[{it.ma}] {it.ten}"
    n0 = len(bk.gold["rows"])
    write_table(bk, ws, top, ["stt", "ten", "dv", "gia"], items, hdr_over={"ten": "Mã - Tên hàng"})
    for g, (ma, ten) in zip(bk.gold["rows"][n0:], real):
        g["ma_hang"], g["ten_hang"] = ma, ten


def h05(bk, rnd, v):  # ĐVT nằm trong tên, không có cột ĐVT
    ws = bk.sheet("BG")
    top = title_block(ws, TITLES)
    items = make_items(rnd, rnd.randrange(20, 30))
    real = [(it.ten, it.dv) for it in items]
    for it in items:
        it.ten = [f"{it.ten} ({it.dv})", f"{it.ten} - {it.dv}", f"{it.ten}/{it.dv.lower()}"][v]
    n0 = len(bk.gold["rows"])
    write_table(bk, ws, top, ["stt", "ma", "ten", "gia"], items)
    for g, (ten, dv) in zip(bk.gold["rows"][n0:], real):
        g["ten_hang"], g["don_vi"] = ten, dv


def h06(bk, rnd, v):  # giá theo Hộp và theo Vỉ: mỗi dòng là 2 mặt hàng bán
    ws = bk.sheet("BG")
    top = title_block(ws, TITLES)
    items = make_items(rnd, rnd.randrange(15, 25))
    for it in items:
        it.dv = "Hộp"
        it.gia_vi = int(it.gia / 10 * 1.05) // 100 * 100 + 100
    names = [("Giá/Hộp", "Giá/Vỉ"), ("Giá hộp", "Giá vỉ"), ("Đơn giá (Hộp)", "Đơn giá (Vỉ)")][v]
    n0 = len(bk.gold["rows"])
    write_table(bk, ws, top, ["stt", "ma", "ten", "gia", "gia_vi"], items, hdr_over={"gia": names[0], "gia_vi": names[1]},
                gold_cols={"ma": "ma_hang", "ten": "ten_hang", "gia": "don_gia"})
    for g, it in zip(list(bk.gold["rows"][n0:]), items):
        g["don_vi"] = "Hộp"
        bk.gold["rows"].append({**g, "don_vi": "Vỉ", "don_gia": str(it.gia_vi)})


def h07(bk, rnd, v):  # ĐVT nằm trong tiêu đề giá
    ws = bk.sheet("BG")
    top = title_block(ws, TITLES)
    unit = ["Viên", "Hộp", "Chai"][v]
    items = make_items(rnd, rnd.randrange(20, 30))
    for it in items:
        it.dv = unit
    n0 = len(bk.gold["rows"])
    write_table(bk, ws, top, ["stt", "ma", "ten", "gia"], items,
                hdr_over={"gia": [f"Đơn giá (đ/{unit.lower()})", f"Giá 1 {unit.lower()}", f"Giá bán/{unit.lower()}"][v]})
    for g in bk.gold["rows"][n0:]:
        g["don_vi"] = unit


def h08(bk, rnd, v):  # không có cột mã, chỉ có số đăng ký / mã vạch: mã phải để trống
    ws = bk.sheet("BG")
    top = title_block(ws, TITLES)
    items = make_items(rnd, rnd.randrange(20, 30))
    extra = ["sdk", "sdk", "barcode"][v]
    for it in items:
        it.barcode = f"893{rnd.randrange(10**9, 10**10)}"
    n0 = len(bk.gold["rows"])
    write_table(bk, ws, top, ["stt", extra, "ten", "dv", "gia"], items, hdr_over={"barcode": "Mã vạch"})
    for g in bk.gold["rows"][n0:]:
        g["ma_hang"] = ""


def h09(bk, rnd, v):  # cột giá không có tiêu đề rõ
    ws = bk.sheet("BG")
    top = title_block(ws, TITLES + ["Đơn vị tiền: VNĐ", ""])
    write_table(bk, ws, top, ["stt", "ma", "ten", "dv", "gia"], make_items(rnd, rnd.randrange(20, 30)),
                hdr_over={"gia": ["", "VNĐ", "(5)"][v]})


def h10(bk, rnd, v):  # tiêu đề tiếng Trung / Hàn / Nhật
    ws = bk.sheet("BG")
    top = title_block(ws, ["Imported goods price list", ""])
    hdr = [{"stt": "序号", "ma": "编码", "ten": "品名", "dv": "单位", "gia": "单价"},
           {"stt": "번호", "ma": "코드", "ten": "품명", "dv": "단위", "gia": "단가"},
           {"stt": "No", "ma": "コード", "ten": "品名", "dv": "単位", "gia": "単価"}][v]
    write_table(bk, ws, top, ["stt", "ma", "ten", "dv", "gia"], make_items(rnd, rnd.randrange(20, 30)), hdr_over=hdr)


def h11(bk, rnd, v):  # tiêu đề tách 2 dòng nhưng không gộp ô
    ws = bk.sheet("BG")
    top = title_block(ws, TITLES)
    first = [{"ma": "Mã", "ten": "Tên", "dv": "Đơn", "gia": "Đơn"}, {"ma": "Mã", "ten": "Tên hàng", "dv": "Đơn vị", "gia": "Giá"},
             {"ma": "Mã số", "ten": "Tên", "dv": "Đ.vị", "gia": "Giá bán"}][v]
    second = [{"ma": "hàng", "ten": "hàng", "dv": "vị", "gia": "giá"}, {"ma": "SP", "ten": "(hoạt chất)", "dv": "tính", "gia": "(VNĐ)"},
              {"ma": "", "ten": "sản phẩm", "dv": "", "gia": "chưa VAT"}][v]
    cols = ["stt", "ma", "ten", "dv", "gia"]
    for i, k in enumerate(cols):
        if k in first:
            ws.cell(top, 1 + i, first[k])
    write_table(bk, ws, top + 1, cols, make_items(rnd, rnd.randrange(20, 30)), hdr_over={**second, "stt": "STT"})


CATS = [
    (1, "Giá cũ / giá mới: phải lấy giá mới", h01), (2, "Giá khuyến mãi đứng trước giá niêm yết", h02),
    (3, "Giá theo bậc số lượng (lấy bậc đầu)", h03), (4, "Mã và tên chung một ô", h04),
    (5, "ĐVT nằm trong tên, không có cột ĐVT", h05), (6, "Hai cột giá theo Hộp và Vỉ", h06),
    (7, "ĐVT nằm trong tiêu đề cột giá", h07), (8, "Không có cột mã, chỉ có SĐK / mã vạch", h08),
    (9, "Cột giá không có tiêu đề rõ", h09), (10, "Tiêu đề tiếng Trung / Hàn / Nhật", h10),
    (11, "Tiêu đề tách 2 dòng, không gộp ô", h11),
]


def main():
    for d in (gen.FILES, gen.GOLD):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
    for cat, desc, fn in CATS:
        for v in range(3):
            rnd = random.Random(9000 + cat * 10 + v)
            bk = Book(f"H{cat:02d}_{v + 1}.xlsx", cat, desc, v + 1)
            fn(bk, rnd, v)
            bk.save()
    print("files:", len(os.listdir(gen.FILES)))


if __name__ == "__main__":
    main()
