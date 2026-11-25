"""MISA exporter, spec section 7. export(res) -> {"files": [(name, bytes)], "report": [dict], "bao_cao_csv": bytes, "n_rows": int}"""
import csv
import os
import io
import re
import functools
import unicodedata
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import openpyxl

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "tep_mau_nhap_khau.xlsx")
SHEET, FIRST, MAXROWS = "Tep nhap khau", 6, 4996
DEFAULT = {"phan_tram_cong_gia": 0, "lam_tron": 1, "gtgt": 1, "tncn": 0.5, "nganh_nghe": "101"}
E_TEXT = "Hàng hóa không có thuộc tính"
GOI_Y = {
    "MA_QUA_DAI": "Mã quá 50 ký tự", "THIEU_MA": "Thiếu mã: thêm mã rồi nhập tay", "GIA_TRONG": "Giá trống",
    "TIEN_TE_LA": "Tiền tệ khác VND: không đưa vào file MISA", "GIA_LIEN_HE": "Giá là Liên hệ: không có số để nhập",
    "TRUNG_MA_KHAC_GIA": "Cùng mã khác giá: cần xem lại", "TRUNG_DONG": "Dòng trùng trong file nguồn",
    "TRUNG_MA_EXPORT": "Trùng mã trong file xuất",
}


def nfc(s):
    return unicodedata.normalize("NFC", "" if s is None else str(s))


def price(don_gia, st):
    """J = round_half_up(don_gia * (1 + pct/100) / lam_tron) * lam_tron, Decimal only."""
    p = Decimal(str(don_gia)) * (1 + Decimal(str(st["phan_tram_cong_gia"])) / 100)
    k = Decimal(str(st["lam_tron"]))
    return int((p / k).quantize(Decimal(1), rounding=ROUND_HALF_UP) * k)


def _num(x):
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError):
        return None


def _why(r, codes):
    if r["trang_thai"] != "ok" and not codes:
        return "Dòng cần xem lại" if r["trang_thai"] == "can_xem" else "Dòng bị bỏ"
    for c in codes:
        if c in GOI_Y:
            return GOI_Y[c]
    if not r["ma_hang"]:
        return GOI_Y["THIEU_MA"]
    if r["tien_te"] != "VND":
        return GOI_Y["TIEN_TE_LA"]
    d = _num(r["don_gia"])
    if d is None:
        return GOI_Y["GIA_TRONG"]
    if d <= 0:
        return "Giá bằng 0 hoặc âm: MISA sẽ lưu giá bán 0"
    if len(nfc(r["ma_hang"]).strip()) > 50:
        return "Mã hàng dài quá 50 ký tự"
    return "Dòng chưa được duyệt hoặc cần xem lại"


def select(res, settings=None):
    st = {**DEFAULT, **(settings or {})}
    elig, report = [], []
    for r in res["rows"]:
        d = _num(r["don_gia"])
        code = nfc(r["ma_hang"]).strip()
        ok = (r["trang_thai"] == "ok" and code and "MA_QUA_DAI" not in r["ma_van_de"] and r["tien_te"] == "VND"
              and d is not None and d > 0 and len(code) <= 50)
        if ok:
            elig.append((r, code))
        else:
            report.append({"nguon": r["nguon"], "ten_hang": r["ten_hang"], "ma_van_de": ";".join(r["ma_van_de"]),
                           "goi_y": _why(r, r["ma_van_de"])})
    count = {}
    for r, c in elig:
        count[c.casefold()] = count.get(c.casefold(), 0) + 1
    rows = []
    for r, c in elig:
        if count[c.casefold()] > 1:
            report.append({"nguon": r["nguon"], "ten_hang": r["ten_hang"],
                           "ma_van_de": ";".join(r["ma_van_de"]), "goi_y": GOI_Y["TRUNG_MA_EXPORT"]})
        else:
            rows.append((r, c))
    # report keeps source order: sort by (sheet order of appearance, row)
    pos = {r["nguon"]: i for i, r in enumerate(res["rows"])}
    report.sort(key=lambda x: pos[x["nguon"]])
    if any(w.get("code") == "GIA_GOM_VAT" if isinstance(w, dict) else w == "GIA_GOM_VAT" for w in res.get("warnings", [])):
        report.insert(0, {"nguon": "", "ten_hang": "Giá trong file đã gồm VAT", "ma_van_de": "GIA_GOM_VAT", "goi_y": ""})
    return rows, report, st


def _fill(rows, st, nganh):
    wb = openpyxl.load_workbook(TEMPLATE)
    ws = wb[SHEET]
    for r in range(FIRST, 17):
        for c in ws[r]:
            c.value = None
    for i, (r, code) in enumerate(rows):
        n = FIRST + i
        ws[f"E{n}"] = E_TEXT
        ws[f"F{n}"] = code
        ws[f"I{n}"] = "".join(ch for ch in nfc(r["ten_hang"]) if ord(ch) <= 0xFFFF).strip()  # expected files trim what an emoji left behind
        ws[f"J{n}"] = price(r["don_gia"], st)
        if r["don_vi"]:
            ws[f"K{n}"] = nfc(r["don_vi"])
        ws[f"U{n}"] = st["gtgt"]
        ws[f"V{n}"] = st["tncn"]
        ws[f"X{n}"] = nganh
        for col in "FIK":
            c = ws[f"{col}{n}"]
            if isinstance(c.value, str) and c.value.startswith("="):
                c.data_type = "s"  # supplier text like "=..." stays text, never a live formula
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@functools.lru_cache(maxsize=None)
def _nganh(code):
    """Expected MISA files hold the full 'Mã-Tên' text in X (as the template example), not the bare code."""
    ws = openpyxl.load_workbook(TEMPLATE, read_only=True)[SHEET]
    for row in ws.iter_rows(min_row=FIRST, max_row=16, min_col=24, max_col=24, values_only=True):
        if row[0] and str(row[0]).startswith(str(code) + "-"):
            return row[0]
    return str(code)


def export(res, settings=None):
    rows, report, st = select(res, settings)
    nganh = _nganh(st["nganh_nghe"])
    chunks = [rows[i:i + MAXROWS] for i in range(0, len(rows), MAXROWS)] or [[]]
    stem = re.sub(r"\.[^.]*$", "", res.get("file") or "file")
    files = [(f"{stem}.misa_them_moi" + (f"_{i + 1}" if len(chunks) > 1 else "") + ".xlsx", _fill(c, st, nganh))
             for i, c in enumerate(chunks)]
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, ["nguon", "ten_hang", "ma_van_de", "goi_y"])
    w.writeheader()
    w.writerows(report)
    return {"files": files, "report": report, "bao_cao_csv": ("\ufeff" + buf.getvalue()).encode("utf-8"),
            "bao_cao_name": f"{stem}.bao_cao.csv", "n_rows": len(rows)}
