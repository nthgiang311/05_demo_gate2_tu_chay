"""Sinh 100 file bảng giá lỗi (20 loại x 5 biến thể) + đáp án gold/<file>.json.
Đáp án viết từ ý đồ khi sinh file, không dựa vào luật của tool.
Chạy: ..\\gate2_portable\\.venv\\Scripts\\python -X utf8 gen.py
"""
import json
import os
import random
import shutil
import zipfile
from decimal import Decimal

import openpyxl
from openpyxl.utils import get_column_letter as L

HERE = os.path.dirname(os.path.abspath(__file__))
FILES, GOLD = os.path.join(HERE, "files"), os.path.join(HERE, "gold")

DRUGS = [
    ("Paracetamol", "500mg", "Viên"), ("Amoxicillin", "500mg", "Viên"), ("Cefuroxim", "250mg", "Viên"),
    ("Azithromycin", "250mg", "Viên"), ("Ibuprofen", "400mg", "Viên"), ("Omeprazol", "20mg", "Viên"),
    ("Metformin", "850mg", "Viên"), ("Amlodipin", "5mg", "Viên"), ("Losartan", "50mg", "Viên"),
    ("Vitamin C", "1000mg", "Tuýp"), ("Berberin", "100mg", "Lọ"), ("Oresol", "4,1g", "Gói"),
    ("Smecta", "3g", "Gói"), ("Siro ho Prospan", "100ml", "Chai"), ("Natri clorid 0,9%", "500ml", "Chai"),
    ("Povidon iod 10%", "90ml", "Chai"), ("Salonpas", "10 miếng", "Hộp"), ("Gạc y tế", "10x10cm", "Gói"),
    ("Bông y tế", "100g", "Gói"), ("Khẩu trang y tế 4 lớp", "50 cái", "Hộp"), ("Bơm tiêm 5ml", "25G", "Cái"),
    ("Kim luồn tĩnh mạch", "22G", "Cái"), ("Dexamethason", "4mg/ml", "Ống"), ("Vitamin B1", "100mg/ml", "Ống"),
    ("Clorpheniramin", "4mg", "Viên"), ("Loratadin", "10mg", "Viên"), ("Cetirizin", "10mg", "Viên"),
    ("Domperidon", "10mg", "Viên"), ("Alverin", "40mg", "Viên"), ("Acetylcystein", "200mg", "Gói"),
    ("Ambroxol", "30mg", "Viên"), ("Eugica", "100 viên", "Lọ"), ("Kem Acyclovir", "5g", "Tuýp"),
    ("Thuốc nhỏ mắt V.Rohto", "13ml", "Lọ"), ("Nhiệt kế điện tử", "", "Cái"), ("Máy đo huyết áp Omron", "HEM-7120", "Cái"),
    ("Que thử thai", "", "Hộp"), ("Băng cá nhân", "100 miếng", "Hộp"), ("Cồn 70 độ", "500ml", "Chai"),
    ("Glucosamin", "1500mg", "Lọ"), ("Canxi D3", "", "Hộp"), ("Sắt Ferrovit", "", "Hộp"), ("Magne B6", "", "Hộp"),
    ("Nước muối sinh lý", "10ml", "Ống"), ("Men vi sinh Enterogermina", "5ml", "Ống"), ("Hapacol 250", "", "Gói"),
    ("Efferalgan", "500mg", "Viên"), ("Panadol Extra", "", "Vỉ"), ("Decolgen", "", "Vỉ"), ("Tiffy", "", "Vỉ"),
    ("Strepsils", "24 viên", "Hộp"), ("Gaviscon", "10ml", "Gói"), ("Kim tiêm insulin", "31G", "Cái"),
    ("Găng tay y tế", "100 cái", "Hộp"), ("Dầu gió Trường Sơn", "3ml", "Chai"), ("Cao xoa Sao Vàng", "", "Hộp"),
    ("Spironolacton", "25mg", "Viên"), ("Atorvastatin", "20mg", "Viên"), ("Clopidogrel", "75mg", "Viên"),
    ("Prednisolon", "5mg", "Viên"),
]
UNITS_EXTRA = ["Hộp", "Vỉ", "Chai", "Lọ", "Tuýp", "Gói", "Viên", "Ống", "Cái"]
HOAT_CHAT = ["Paracetamol", "Amoxicillin", "Cefuroxim", "Ibuprofen", "Metformin", "Losartan", "Acid ascorbic"]
NUOC = ["Việt Nam", "Pháp", "Ấn Độ", "Hàn Quốc", "Đức", "Thái Lan"]

# header text cho từng khoá cột; nhóm "vn" là cách ghi phổ biến
HDR = {
    "vn": {"stt": "STT", "ma": "Mã hàng", "ten": "Tên hàng", "dv": "ĐVT", "gia": "Đơn giá", "gia_vat": "Giá có VAT",
           "so_luong": "Số lượng", "thanh_tien": "Thành tiền", "hoat_chat": "Hoạt chất", "sdk": "SĐK", "nuoc": "Nước SX",
           "han": "Hạn dùng", "quy_cach": "Quy cách", "tien_te": "Tiền tệ", "gia_km": "Giá khuyến mãi", "ghi_chu": "Ghi chú"},
    "syn": {"stt": "TT", "ma": "Mã SP", "ten": "Mặt hàng", "dv": "Đơn vị tính", "gia": "Giá bán sỉ", "gia_vat": "Giá sau thuế",
            "so_luong": "SL", "thanh_tien": "Tổng tiền", "hoat_chat": "Thành phần", "sdk": "Số đăng ký", "nuoc": "Xuất xứ",
            "han": "HSD", "quy_cach": "Quy cách đóng gói", "tien_te": "Loại tiền", "gia_km": "Giá KM", "ghi_chu": "Lưu ý"},
    "en": {"stt": "No.", "ma": "Item code", "ten": "Description", "dv": "UOM", "gia": "Unit price", "gia_vat": "Price incl. VAT",
           "so_luong": "Qty", "thanh_tien": "Amount", "hoat_chat": "Active ingredient", "sdk": "Reg. No.", "nuoc": "Origin",
           "han": "Expiry", "quy_cach": "Packing", "tien_te": "Currency", "gia_km": "Promo price", "ghi_chu": "Remark"},
    "noacc": {"stt": "Stt", "ma": "Ma hang", "ten": "Ten hang hoa", "dv": "Dvt", "gia": "Don gia", "gia_vat": "Gia VAT",
              "so_luong": "So luong", "thanh_tien": "Thanh tien", "hoat_chat": "Hoat chat", "sdk": "SDK", "nuoc": "Nuoc SX",
              "han": "Han dung", "quy_cach": "Quy cach", "tien_te": "Tien te", "gia_km": "Gia KM", "ghi_chu": "Ghi chu"},
    "abbr": {"stt": "#", "ma": "MH", "ten": "T.Hàng", "dv": "Đ/v", "gia": "Đ.Giá", "gia_vat": "ĐG+VAT", "so_luong": "SL",
             "thanh_tien": "T.Tiền", "hoat_chat": "HC", "sdk": "SĐK", "nuoc": "NSX", "han": "HD", "quy_cach": "QC",
             "tien_te": "TT", "gia_km": "KM", "ghi_chu": "GC"},
}


class Item:
    def __init__(self, rnd, i, code_style):
        d = rnd.choice(DRUGS)
        self.ten = (d[0] + " " + d[1]).strip()
        self.dv = d[2] if rnd.random() < 0.8 else rnd.choice(UNITS_EXTRA)
        self.gia = rnd.choice([rnd.randrange(15, 300) * 100, rnd.randrange(30, 2500) * 100, rnd.randrange(10, 250) * 1000])
        if code_style == "prefix":
            self.ma = f"{rnd.choice(['TH', 'SP', 'YT', 'DP'])}{1000 + i:04d}"
        elif code_style == "zero":
            self.ma = f"{i + 1:06d}"
        else:
            self.ma = f"{rnd.choice(['A', 'B', 'C'])}-{i + 100}"
        self.vat = rnd.choice([5, 8, 10])
        self.so_luong = rnd.randrange(1, 50)
        self.hoat_chat = rnd.choice(HOAT_CHAT)
        self.sdk = f"VD-{rnd.randrange(10000, 99999)}-{rnd.randrange(18, 25)}"
        self.nuoc = rnd.choice(NUOC)
        self.han = f"{rnd.randrange(1, 13):02d}/{rnd.randrange(2027, 2030)}"
        self.quy_cach = rnd.choice(["Hộp 10 vỉ x 10 viên", "Hộp 3 vỉ x 10 viên", "Chai 100ml", "Hộp 20 gói", "Lọ 100 viên"])
        self.tien_te = "VND"
        self.trap = None          # lý do dòng này KHÔNG được tự động 'ok'
        self.gia_cell = None      # ghi đè ô giá (chữ, "Liên hệ"...)
        self.gia_gold = Decimal(self.gia)


def vn(n):  # 65000 -> "65.000"
    return f"{int(n):,}".replace(",", ".")


def make_items(rnd, n, code_style="prefix"):
    items, seen = [], set()
    while len(items) < n:
        it = Item(rnd, len(items), code_style)
        if it.ten in seen and rnd.random() < 0.7:
            continue
        seen.add(it.ten)
        items.append(it)
    return items


def cell_value(it, key, opts):
    if key == "stt":
        return opts["_stt"]
    if key == "ma":
        return it.ma
    if key == "ten":
        return opts.get("ten_fn", lambda x: x)(it.ten)
    if key == "dv":
        return opts.get("dv_fn", lambda x: x)(it.dv)
    if key == "gia":
        if it.gia_cell is not None:
            return it.gia_cell
        return opts.get("gia_fn", lambda x: x)(it.gia)
    if key == "gia_vat":
        return round(it.gia * (100 + it.vat) / 100)
    if key == "so_luong":
        return it.so_luong
    if key == "thanh_tien":
        return it.gia * it.so_luong
    if key == "gia_km":
        return int(it.gia * 0.9)
    return getattr(it, key, "")


class Book:
    def __init__(self, name, cat, desc, variant):
        self.wb = openpyxl.Workbook()
        self.wb.remove(self.wb.active)
        self.name, self.gold = name, {"file": name, "category": cat, "category_desc": desc, "variant": variant,
                                      "expect_error": None, "tables": [], "rows": [], "hieu_luc_tu": None}

    def sheet(self, title):
        return self.wb.create_sheet(title)

    def save(self):
        self.wb.save(os.path.join(FILES, self.name))
        with open(os.path.join(GOLD, self.name + ".json"), "w", encoding="utf-8") as f:
            json.dump(self.gold, f, ensure_ascii=False, indent=1)


def write_table(bk, ws, top, cols, items, *, left=1, hdr="vn", hdr_over=None, two_level=None, opts=None,
                group_every=0, groups=None, subtotal=False, total=False, repeat_every=0, hidden=(),
                blank_every=0, dup_exact=(), no_header=False, gold_cols=None):
    """Ghi một bảng; trả về dòng cuối đã dùng. Thêm đáp án bảng + dòng vào bk.gold."""
    opts = dict(opts or {})
    names = {k: (hdr_over or {}).get(k, HDR[hdr].get(k, k)) for k in cols}
    colnum = {k: left + i for i, k in enumerate(cols)}
    r = top
    header_rows = []
    if not no_header:
        if two_level:  # two_level = {"Giá": ["gia", "gia_vat"]}
            for k in cols:
                ws.cell(r, colnum[k], names[k])
            for top_name, keys in two_level.items():
                c0, c1 = colnum[keys[0]], colnum[keys[-1]]
                ws.cell(r, c0, top_name)
                for k in keys:
                    ws.cell(r + 1, colnum[k], names[k])
                ws.merge_cells(start_row=r, start_column=c0, end_row=r, end_column=c1)
            for k in cols:
                if not any(k in v for v in two_level.values()):
                    ws.merge_cells(start_row=r, start_column=colnum[k], end_row=r + 1, end_column=colnum[k])
            header_rows = [r, r + 1]
            r += 2
        else:
            for k in cols:
                ws.cell(r, colnum[k], names[k])
            header_rows = [r]
            r += 1
    data_first = r
    stt = 0
    grp_names = groups or ["NHÓM THUỐC KÊ ĐƠN", "NHÓM THUỐC KHÔNG KÊ ĐƠN", "NHÓM VẬT TƯ Y TẾ", "NHÓM THỰC PHẨM CHỨC NĂNG"]
    gi, grp_start, grp_rows = 0, None, []
    hidden = set(hidden)
    for idx, it in enumerate(items):
        if group_every and idx % group_every == 0:
            if subtotal and grp_rows:
                ws.cell(r, colnum["ten"], "Cộng nhóm")
                if "thanh_tien" in colnum:
                    ws.cell(r, colnum["thanh_tien"], f"=SUM({L(colnum['thanh_tien'])}{grp_rows[0]}:{L(colnum['thanh_tien'])}{grp_rows[-1]})")
                r += 1
            ws.cell(r, left, grp_names[gi % len(grp_names)])
            gi += 1
            r += 1
            grp_rows = []
        if repeat_every and idx and idx % repeat_every == 0 and header_rows:
            for hr in header_rows:
                for c in range(left, left + len(cols)):
                    v = ws.cell(hr, c).value
                    if v is not None:
                        ws.cell(r, c, v)
                r += 1
        if blank_every and idx and idx % blank_every == 0:
            r += 1
        stt += 1
        opts["_stt"] = stt
        for k in cols:
            v = cell_value(it, k, opts)
            if v is not None and v != "":
                ws.cell(r, colnum[k], v)
        if idx in hidden:
            ws.row_dimensions[r].hidden = True
        else:
            bk.gold["rows"].append({
                "nguon": f"{ws.title}!{r}", "ma_hang": it.ma if "ma" in cols else "", "ten_hang": it.ten,
                "don_vi": it.dv if "dv" in cols else "",
                "don_gia": None if it.gia_gold is None else str(it.gia_gold),
                "tien_te": it.tien_te, "expect_ok": it.trap is None, "trap": it.trap})
            grp_rows.append(r)
        r += 1
        if idx in dup_exact:   # dòng trùng y hệt ngay sau
            for k in cols:
                v = cell_value(it, k, opts)
                if v is not None and v != "":
                    ws.cell(r, colnum[k], v)
            bk.gold["rows"].append({**bk.gold["rows"][-1], "nguon": f"{ws.title}!{r}", "expect_ok": False,
                                    "trap": "trung_y_het"})
            r += 1
    if subtotal and grp_rows:
        ws.cell(r, colnum["ten"], "Cộng nhóm")
        r += 1
    if total:
        ws.cell(r, colnum["ten"], "TỔNG CỘNG")
        if "thanh_tien" in colnum:
            ws.cell(r, colnum["thanh_tien"], f"=SUM({L(colnum['thanh_tien'])}{data_first}:{L(colnum['thanh_tien'])}{r - 1})")
        r += 1
    gc = gold_cols or {"ma": "ma_hang", "ten": "ten_hang", "dv": "don_vi", "gia": "don_gia", "tien_te": "tien_te"}
    bk.gold["tables"].append({"sheet": ws.title, "header_rows": header_rows, "data_first": data_first, "data_last": r - 1,
                              "mapping": {f: L(colnum[k]) for k, f in gc.items() if k in colnum}})
    return r


def title_block(ws, lines, left=1):
    for i, t in enumerate(lines):
        ws.cell(1 + i, left, t)
    return len(lines) + 1


TITLES = ["CÔNG TY TNHH DƯỢC PHẨM AN KHANG", "Địa chỉ: 12 Nguyễn Trãi, Q.1, TP.HCM - ĐT: 028 3822 0000", "",
          "BẢNG BÁO GIÁ THUỐC VÀ VẬT TƯ Y TẾ"]


def base_cols(rnd, extra=()):
    cols = ["stt", "ma", "ten", "dv", "gia"]
    return cols + list(extra)


# ---------------------------------------------------------------- 20 loại
def c01(bk, rnd, v):  # sạch
    ws = bk.sheet("Bao gia")
    write_table(bk, ws, 1, base_cols(rnd), make_items(rnd, rnd.randrange(15, 40)))


def c02(bk, rnd, v):  # tiêu đề sâu + ngày hiệu lực
    ws = bk.sheet("BG")
    lines = TITLES + [f"Áp dụng từ ngày 0{v + 1}/12/2026", ""] + [""] * v
    top = title_block(ws, lines)
    bk.gold["hieu_luc_tu"] = f"2026-12-0{v + 1}"
    write_table(bk, ws, top, base_cols(rnd, ["quy_cach"]), make_items(rnd, rnd.randrange(20, 50)))


def c03(bk, rnd, v):  # ghi chú, chữ ký ở cuối
    ws = bk.sheet("Sheet1")
    top = title_block(ws, TITLES[:2] + [""])
    end = write_table(bk, ws, top, base_cols(rnd), make_items(rnd, rnd.randrange(20, 45)))
    notes = ["Ghi chú:", "- Giá trên chưa bao gồm VAT.", "- Báo giá có hiệu lực 30 ngày.", "",
             "Người lập biểu", "Kế toán trưởng", "Giám đốc", "(Ký, họ tên)"]
    for i, t in enumerate(notes[: 4 + v]):
        ws.cell(end + 1 + i, 2 + (i % 3 if i >= 4 else 0), t)


def c04(bk, rnd, v):  # tiêu đề lặp mỗi trang
    ws = bk.sheet("In")
    top = title_block(ws, TITLES)
    write_table(bk, ws, top, base_cols(rnd), make_items(rnd, rnd.randrange(60, 120)), repeat_every=rnd.choice([20, 25, 30]))


def c05(bk, rnd, v):  # tiêu đề 2 tầng, ô gộp, giá trước/sau VAT
    ws = bk.sheet("Gia")
    top = title_block(ws, TITLES)
    cols = ["stt", "ma", "ten", "dv", "gia", "gia_vat"]
    hdr_over = {"gia": rnd.choice(["Chưa VAT", "Trước thuế", "Chưa thuế GTGT"]), "gia_vat": rnd.choice(["Có VAT", "Sau thuế", "Đã gồm VAT"])}
    write_table(bk, ws, top, cols, make_items(rnd, rnd.randrange(20, 40)), hdr_over=hdr_over,
                two_level={rnd.choice(["Đơn giá (VNĐ)", "Giá bán", "Đơn giá"]): ["gia", "gia_vat"]})


def c06(bk, rnd, v):  # dòng nhóm + cộng nhóm + tổng
    ws = bk.sheet("BaoGia")
    top = title_block(ws, TITLES)
    cols = ["stt", "ma", "ten", "dv", "gia", "so_luong", "thanh_tien"]
    write_table(bk, ws, top, cols, make_items(rnd, rnd.randrange(30, 60)), group_every=rnd.choice([8, 10, 12]),
                subtotal=v % 2 == 0, total=True)


def c07(bk, rnd, v):  # dòng ẩn + sheet ẩn
    ws = bk.sheet("Bang gia")
    top = title_block(ws, TITLES)
    items = make_items(rnd, rnd.randrange(30, 50))
    hid = set(rnd.sample(range(len(items)), k=3 + v))
    write_table(bk, ws, top, base_cols(rnd), items, hidden=hid)
    old = bk.sheet("Gia cu")
    write_table(Book("_", 0, "", 0), old, 1, base_cols(rnd), make_items(rnd, 10))   # không vào đáp án
    old.sheet_state = "hidden"


def c08(bk, rnd, v):  # nhiều sheet hiện
    for i, nm in enumerate(["Thuoc", "Vat tu", "TPCN", "My pham"][: 2 + v % 3]):
        ws = bk.sheet(nm)
        top = title_block(ws, [f"BẢNG GIÁ {nm.upper()}", ""])
        write_table(bk, ws, top, base_cols(rnd), make_items(rnd, rnd.randrange(10, 25)))


def c09(bk, rnd, v):  # giá dạng chữ kiểu Việt
    ws = bk.sheet("BG")
    top = title_block(ws, TITLES)
    fmts = [lambda g: vn(g), lambda g: vn(g) + "đ", lambda g: vn(g) + " VNĐ", lambda g: vn(g) + " đồng",
            lambda g: rnd.choice([vn(g), vn(g) + "đ", g, vn(g) + ",00"])]
    write_table(bk, ws, top, base_cols(rnd), make_items(rnd, rnd.randrange(20, 40)), opts={"gia_fn": fmts[v]})


def c10(bk, rnd, v):  # đơn vị nghìn đồng
    ws = bk.sheet("BG")
    lines = TITLES + (["(Đơn vị tính: 1.000 đồng)"] if v in (2, 3) else [])
    top = title_block(ws, lines)
    hdr = {0: "Đơn giá (nghìn đồng)", 1: "Giá (1.000đ)", 2: "Đơn giá", 3: "Đơn giá", 4: "Đơn giá (x1000 VNĐ)"}[v]
    items = make_items(rnd, rnd.randrange(20, 40))
    write_table(bk, ws, top, base_cols(rnd), items, hdr_over={"gia": hdr},
                opts={"gia_fn": lambda g: (g // 1000 if g % 1000 == 0 else g / 1000)})


def c11(bk, rnd, v):  # Liên hệ / trống / 0 / khoảng giá
    ws = bk.sheet("BG")
    top = title_block(ws, TITLES)
    items = make_items(rnd, rnd.randrange(25, 40))
    for it in rnd.sample(items, k=4 + v):
        kind = rnd.choice(["lien_he", "gia_trong", "gia_0", "khoang_gia", "gach"])
        it.trap, it.gia_gold = kind, None
        it.gia_cell = {"lien_he": rnd.choice(["Liên hệ", "LH", "Call"]), "gia_trong": "", "gia_0": 0,
                       "khoang_gia": f"{vn(it.gia)}-{vn(it.gia + 2000)}", "gach": "-"}[kind]
        if kind == "gia_0":
            it.gia_gold = Decimal(0)
    write_table(bk, ws, top, base_cols(rnd), items)


def c12(bk, rnd, v):  # mã trùng khác giá + dòng trùng y hệt
    ws = bk.sheet("BG")
    top = title_block(ws, TITLES)
    items = make_items(rnd, rnd.randrange(25, 40))
    k = 2 + v % 3
    for a in rnd.sample(range(len(items) - 1), k=k):
        b = rnd.randrange(len(items))
        if a == b or items[a].trap or items[b].trap:
            continue
        items[b].ma = items[a].ma
        items[a].trap = items[b].trap = "trung_ma_khac_gia"
    dups = set(rnd.sample(range(len(items)), k=1 + v % 2))
    dups = {d for d in dups if not items[d].trap}
    write_table(bk, ws, top, base_cols(rnd), items, dup_exact=dups)


def c13(bk, rnd, v):  # chữ bẩn: khoảng trắng, NBSP, hoa thường, mã số 0 đầu, xuống dòng
    ws = bk.sheet("BG")
    top = title_block(ws, TITLES)
    items = make_items(rnd, rnd.randrange(20, 40), code_style="zero" if v % 2 == 0 else "prefix")
    ten_fns = [lambda t: "  " + t + "   ", lambda t: t.replace(" ", " ", 1), lambda t: t.replace(" ", "  "),
               lambda t: t.replace(" ", "\n", 1), lambda t: " " + t.upper()]
    dv_fns = [lambda d: d.upper(), lambda d: d.lower(), lambda d: " " + d + " ", lambda d: d, lambda d: d.lower()]
    gia_fn = (lambda g: f" {g:,} ".replace(",", " ")) if v == 4 else (lambda g: str(g)) if v == 3 else (lambda g: g)
    if v == 4:   # tên viết hoa: đáp án so sánh không phân biệt hoa thường
        pass
    write_table(bk, ws, top, base_cols(rnd), items, opts={"ten_fn": ten_fns[v], "dv_fn": dv_fns[v], "gia_fn": gia_fn})


def c14(bk, rnd, v):  # cột xáo trộn + nhiều cột thừa
    ws = bk.sheet("Data")
    top = title_block(ws, TITLES)
    extra = ["hoat_chat", "sdk", "nuoc", "han", "quy_cach", "so_luong", "thanh_tien", "ghi_chu"]
    cols = ["ma", "ten", "dv", "gia"] + rnd.sample(extra, k=3 + v)
    rnd.shuffle(cols)
    write_table(bk, ws, top, cols, make_items(rnd, rnd.randrange(20, 40)))


def c15(bk, rnd, v):  # tên cột đồng nghĩa
    ws = bk.sheet("BG")
    top = title_block(ws, TITLES)
    extras = [[], ["quy_cach"], ["hoat_chat", "nuoc"], ["quy_cach", "so_luong", "thanh_tien"], ["sdk", "han"]][v]
    over = [{}, {"gia": "Giá bán"}, {"ten": "Tên sản phẩm", "gia": "Giá niêm yết"}, {"ma": "Code", "gia": "Giá phân phối"},
            {"ten": "Sản phẩm", "dv": "Đ.vị", "gia": "Giá"}][v]
    write_table(bk, ws, top, base_cols(rnd, extras), make_items(rnd, rnd.randrange(20, 40)), hdr="syn", hdr_over=over)


def c16(bk, rnd, v):  # tiêu đề tiếng Anh
    ws = bk.sheet("Price list")
    top = title_block(ws, ["ABC PHARMA DISTRIBUTION CO., LTD", "PRICE LIST - DECEMBER 2026", ""])
    extras = [[], ["packing"], ["hoat_chat", "nuoc"], ["so_luong", "thanh_tien"], ["gia_vat"]][v]
    extras = ["quy_cach" if e == "packing" else e for e in extras]
    over = [{}, {"gia": "Price"}, {"ten": "Product name", "dv": "Unit"}, {"ma": "SKU", "gia": "Net price"},
            {"gia": "Price excl. VAT"}][v]
    write_table(bk, ws, top, base_cols(rnd, extras), make_items(rnd, rnd.randrange(20, 40)), hdr="en", hdr_over=over)


def c17(bk, rnd, v):  # tiêu đề viết tắt / không dấu / vô nghĩa
    ws = bk.sheet("Sheet1")
    top = title_block(ws, TITLES)
    cols = base_cols(rnd, [[], ["quy_cach"], [], ["so_luong"], ["nuoc"]][v])
    if v in (0, 3):
        write_table(bk, ws, top, cols, make_items(rnd, rnd.randrange(20, 40)), hdr="noacc")
    elif v in (1, 4):
        write_table(bk, ws, top, cols, make_items(rnd, rnd.randrange(20, 40)), hdr="abbr")
    else:  # "Cột 1..n": chỉ suy được từ dữ liệu
        write_table(bk, ws, top, cols, make_items(rnd, rnd.randrange(20, 40)),
                    hdr_over={k: f"Cột {i + 1}" for i, k in enumerate(cols)})


def c18(bk, rnd, v):  # bố cục lạ
    ws = bk.sheet("BG")
    if v == 0:   # không có dòng tiêu đề
        top = title_block(ws, TITLES)
        write_table(bk, ws, top, base_cols(rnd), make_items(rnd, rnd.randrange(20, 35)), no_header=True)
    elif v == 1:  # bảng bắt đầu ở cột D, dòng 12
        title_block(ws, TITLES, left=4)
        write_table(bk, ws, 12, base_cols(rnd), make_items(rnd, rnd.randrange(20, 35)), left=4)
    elif v == 2:  # hai bảng cạnh nhau
        title_block(ws, TITLES)
        write_table(bk, ws, 6, ["ma", "ten", "dv", "gia"], make_items(rnd, 20), left=1)
        write_table(bk, ws, 6, ["ma", "ten", "dv", "gia"], make_items(rnd, 18, "dash"), left=7)
    elif v == 3:  # hai bảng chồng dọc, tiêu đề khác nhau
        top = title_block(ws, ["I. THUỐC", ""])
        end = write_table(bk, ws, top, base_cols(rnd), make_items(rnd, 15))
        ws.cell(end + 1, 1, "II. VẬT TƯ Y TẾ")
        write_table(bk, ws, end + 3, ["stt", "ten", "ma", "gia", "dv"], make_items(rnd, 12, "dash"), hdr="syn")
    else:  # cột trống xen giữa và dòng trống rải rác
        top = title_block(ws, TITLES)
        write_table(bk, ws, top, ["stt", "ma", "ghi_chu", "ten", "dv", "gia"], make_items(rnd, rnd.randrange(20, 35)),
                    blank_every=5, opts={}, hdr_over={"ghi_chu": ""})


def c19(bk, rnd, v):  # tiền USD / cột tiền tệ
    ws = bk.sheet("BG")
    top = title_block(ws, ["IMPORTED MEDICAL DEVICES - QUOTATION", ""])
    items = make_items(rnd, rnd.randrange(15, 30))
    for it in items:
        if v < 3 or rnd.random() < 0.5:
            usd = Decimal(rnd.randrange(50, 50000)) / 100
            it.gia, it.gia_gold, it.tien_te = usd, usd, "USD"
    if v == 0:
        write_table(bk, ws, top, base_cols(rnd), items, hdr_over={"gia": "Đơn giá (USD)"},
                    opts={"gia_fn": lambda g: float(g)})
    elif v == 1:
        write_table(bk, ws, top, base_cols(rnd), items, opts={"gia_fn": lambda g: f"{g} USD"})
    elif v == 2:
        write_table(bk, ws, top, base_cols(rnd), items, opts={"gia_fn": lambda g: f"${g}"})
    else:
        write_table(bk, ws, top, base_cols(rnd, ["tien_te"]), items, opts={"gia_fn": lambda g: float(g) if isinstance(g, Decimal) else g})


def c20(bk, rnd, v):  # file hỏng: không ghi workbook bình thường
    raise NotImplementedError


CATS = [
    (1, "Sạch, tiêu đề ở dòng 1", c01), (2, "Tiêu đề sâu + khối thông tin công ty + ngày hiệu lực", c02),
    (3, "Ghi chú, chữ ký ở cuối bảng", c03), (4, "Tiêu đề lặp lại mỗi trang in", c04),
    (5, "Tiêu đề 2 tầng, ô gộp, giá trước/sau VAT", c05), (6, "Dòng nhóm, cộng nhóm, tổng cộng (công thức)", c06),
    (7, "Dòng ẩn + sheet ẩn", c07), (8, "Nhiều sheet hiện", c08), (9, "Giá dạng chữ kiểu Việt (65.000đ, VNĐ)", c09),
    (10, "Đơn vị nghìn đồng (trong tiêu đề hoặc dòng ghi chú)", c10), (11, "Giá Liên hệ / trống / 0 / khoảng giá", c11),
    (12, "Mã trùng khác giá, dòng trùng y hệt", c12), (13, "Chữ bẩn: khoảng trắng, NBSP, hoa thường, mã có số 0 đầu", c13),
    (14, "Cột xáo trộn + nhiều cột thừa", c14), (15, "Tên cột đồng nghĩa (Mặt hàng, Giá bán sỉ...)", c15),
    (16, "Tiêu đề tiếng Anh", c16), (17, "Tiêu đề viết tắt / không dấu / 'Cột 1..n'", c17),
    (18, "Bố cục lạ: không tiêu đề, lệch cột, 2 bảng 1 sheet, cột trống", c18), (19, "Tiền USD / cột tiền tệ", c19),
    (20, "File hỏng / sai định dạng", c20),
]


def broken(v, name):
    p = os.path.join(FILES, name)
    exp = None
    if v == 0:
        with open(p, "wb") as f:
            f.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n")
        exp = "WRONG_FORMAT_PDF"
    elif v == 1:
        open(p, "wb").close()
        exp = "FILE_EMPTY"
    elif v == 2:
        with open(p, "w", encoding="utf-8") as f:
            f.write("Ma hang,Ten hang,DVT,Don gia\nTH1001,Paracetamol 500mg,Vien,1500\n")
        exp = "UNSUPPORTED_FORMAT"
    elif v == 3:
        wb = openpyxl.Workbook()
        wb.active.append(["Mã hàng", "Tên hàng", "ĐVT", "Đơn giá"])
        tmp = p + ".tmp"
        wb.save(tmp)
        data = open(tmp, "rb").read()
        os.remove(tmp)
        with open(p, "wb") as f:
            f.write(data[: len(data) // 2])
        exp = "FILE_CORRUPT"
    else:
        with open(p, "w", encoding="utf-8") as f:
            f.write("<html><body><table><tr><td>Mã hàng</td><td>Đơn giá</td></tr></table></body></html>")
        exp = "UNSUPPORTED_FORMAT"
    return exp


def main():
    for d in (FILES, GOLD):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
    n = 0
    for cat, desc, fn in CATS:
        for v in range(5):
            rnd = random.Random(cat * 100 + v)
            name = f"C{cat:02d}_{v + 1}.xlsx"
            if cat == 20:
                exp = broken(v, name)
                g = {"file": name, "category": cat, "category_desc": desc, "variant": v + 1, "expect_error": exp,
                     "tables": [], "rows": [], "hieu_luc_tu": None}
                with open(os.path.join(GOLD, name + ".json"), "w", encoding="utf-8") as f:
                    json.dump(g, f, ensure_ascii=False, indent=1)
            else:
                bk = Book(name, cat, desc, v + 1)
                fn(bk, rnd, v)
                bk.save()
            n += 1
    print("files:", n)


if __name__ == "__main__":
    main()
