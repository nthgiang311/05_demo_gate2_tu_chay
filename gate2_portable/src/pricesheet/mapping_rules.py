"""Layer 5 (rules): header text -> field scores, extras keys, column->field assignment."""
import re
from contextvars import ContextVar
from functools import lru_cache
from difflib import SequenceMatcher

from .normalize import fold

FIELDS = ["ma_hang", "ten_hang", "don_vi", "don_gia", "tien_te", "hieu_luc_tu"]

# synonym (folded) -> weight. Matching is whole-token containment, exact match scores the full weight.
SYN = {
    "ma_hang": {"ma hang": 1, "ma hang hoa": 1, "ma vt": 1, "ma vat tu": 1, "ma sp": 1, "ma san pham": 1, "ma thuoc": 1,
                "ma": 0.9, "code": 0.9, "item code": 1, "product code": 1, "sku": 0.9, "mh": 0.8, "ma hh": 0.9,
                "ma so": 0.7, "danh diem": 1, "so hieu": 0.8, "ma ke khai": 1, "ma dinh danh": 0.9, "ma nvl": 0.9, "ma noi bo": 0.6, "part no": 0.8, "item no": 0.8, "ma tham chieu": 0.7},
    "ten_hang": {"ten hang": 1, "ten hang hoa": 1, "ten vat tu": 1, "ten san pham": 1, "ten thuoc": 1, "ten": 0.8,
                 "mo ta": 0.85, "description": 1, "item name": 1, "product name": 1, "name": 0.8, "dien giai": 0.85,
                 "ten sp": 1, "ten vt": 1, "ten hh": 1, "san pham": 0.8, "hang hoa": 0.8, "vat tu": 0.7,
                 "ten thuoc ham luong": 1, "ten thuoc hoat chat": 0.9, "item": 0.6, "ten thuong mai": 1, "ten gia": 0.7},
    "don_vi": {"dvt": 1, "don vi tinh": 1, "don vi": 0.9, "dv": 0.8, "uom": 1, "unit": 0.85, "dvt chuan": 1, "dv tinh": 1},
    "don_gia": {"don gia": 1, "gia ban": 0.95, "gia niem yet": 0.95, "gia": 0.8, "gia ban le": 0.85, "gia si": 0.8,
                "gia le": 0.8, "unit price": 1, "price": 0.9, "dg": 0.85, "list price": 0.95, "gia ban buon": 0.8,
                "gia chua vat": 1, "gia ban chua vat": 1, "don gia chua vat": 1, "gia bao": 0.9, "gia thanh": 0.7,
                "bac 1": 1.0, "gia tri": 0.4},
    "tien_te": {"tien te": 1, "currency": 1, "loai tien": 1, "ccy": 1, "don vi tien": 0.9, "don vi tien te": 1, "cur": 0.8},
    "hieu_luc_tu": {"hieu luc tu": 1, "hieu luc": 0.95, "ngay hieu luc": 1, "ngay ap dung": 1, "ap dung tu": 1,
                    "valid from": 1, "effective date": 1, "effective from": 1, "tu ngay": 0.8, "ngay bat dau": 0.8,
                    "hieu luc tu ngay": 1, "ngay hl": 0.9, "date": 0.5, "ngay": 0.6, "ap dung": 0.8, "valid": 0.7,
                    "ngay cap nhat gia": 0.5},
}

# ---- Luật v2: tắt mặc định (= luật v1). graph.normalize(rules="v2") bật cho một lần chạy. ----
# G1 thêm từ đồng nghĩa; G2 ghép tiêu đề viết tắt có dấu câu ('Đ/v' -> 'dv'); G3 nhận cột ĐVT theo nội dung.
RULES_V2 = ContextVar("pricesheet_rules_v2", default=False)
SYN_V2_EXTRA = {
    "ten_hang": {"mat hang": 1, "ten mat hang": 1, "t hang": 0.9},
    "don_vi": {"dvi": 0.9},
    "don_gia": {"price excl vat": 1, "net price": 0.95, "unit price excl vat": 1, "gia phan phoi": 0.9},
}
SYN_V2 = {f: {**syns, **SYN_V2_EXTRA.get(f, {})} for f, syns in SYN.items()}

# known extras columns: (regex on folded header, key). First match wins. Order matters.
EXTRAS = [
    (r"\bso dang ky\b|\bsdk\b|\bso dk\b|\bvisa\b|\bso dang ki\b|\bsodangky\b", "so_dang_ky"),
    (r"\bhoat chat\b|\bthanh phan\b", "hoat_chat"),
    (r"\bham luong\b|\bnong do\b", "ham_luong"),
    (r"\bdang bao che\b|\bbao che\b|\bbaoche\b", "dang_bao_che"),
    (r"\bhang sx\b|\bnha san xuat\b|\bnsx\b|\bhang san xuat\b|\bhang\b sx", "hang_sx"),
    (r"\bnuoc sx\b|\bxuat xu\b|\bnuoc san xuat\b", "nuoc_sx"),
    (r"\bquy cach\b|\bqc\b|\bquy cach dong goi\b", "quy_cach"),
    (r"\bso lo\b|^lo$", "so_lo"),
    (r"\bhan dung\b|\bhsd\b|\bhan su dung\b", "han_dung"),
    (r"\bma vach\b|\bbarcode\b|\bean\b", "ma_vach"),
    (r"\bkhuyen mai\b|\bgia km\b", "gia_khuyen_mai"),
    (r"\bchiet khau\b|%\s*ck\b|\bck\b", "chiet_khau"),
    (r"\bgia von\b|\bgia nhap\b|\bgia goc\b", "gia_von"),
    (r"\bbac (\d+)\b", "bac_N"),
]
VAT_INCL = re.compile(r"\bco vat\b|\bgom vat\b|\bsau vat\b|\bincl|\bda vat\b|\bgia vat\b|\bvat\b(?!.*chua)|\bco thue\b")
VAT_EXCL = re.compile(r"\bchua vat\b|\btruoc vat\b|\bchua thue\b|\bex vat\b|\bchua gom vat\b|\bkhong vat\b")
NOT_PRICE = re.compile(r"\bthanh tien\b|\bso luong\b|\bsl\b|\btong\b|\btien thue\b|\bton kho\b|\bton\b|\bstt\b|\bkhuyen mai\b|\bchiet khau\b|\bgia von\b|\bgia nhap\b|%")


def extras_key(header):
    """Known extras key for a header, else the original header text cleaned (NFC, trim, newline->space)."""
    f = fold(header)
    if VAT_INCL.search(f) and "gia" in f and not VAT_EXCL.search(f):
        return "gia_co_vat"
    for rx, key in EXTRAS:
        m = re.search(rx, f)
        if m:
            if key == "bac_N":
                n = int(m.group(1))
                return None if n == 1 else f"bac_{n}"
            return key
    return None


def header_scores(header):
    """{field: score 0..1} for one header text (cached by folded text)."""
    v2 = RULES_V2.get()
    f = fold(header)
    out = dict(_scores(f, v2))
    compact = f.replace(" ", "")
    if v2 and " " in f and len(compact) <= 4:   # G2: 'd v' -> 'dv', 'd vi' -> 'dvi'; <= 4 so 't hang' never becomes 'thang'
        for fld, sc in _scores(compact, v2).items():
            out[fld] = max(out.get(fld, 0), sc)
    if " / " in str(header):     # multi-tier header: the leaf label alone also counts (group text must not dilute it)
        for fld, sc in _scores(fold(str(header).rsplit(" / ", 1)[1]), v2).items():
            if sc >= 0.8:
                out[fld] = max(out.get(fld, 0), sc)
    return out


@lru_cache(maxsize=4096)
def _scores(f, v2=False):
    out = {}
    if not f or len(f) > 80:     # long cells are data, not headers
        return out
    toks = f.split()
    for field, syns in (SYN_V2 if v2 else SYN).items():
        best = 0.0
        for s, w in syns.items():
            st = s.split()
            if f == s:
                sc = w
            elif len(st) == 1 and len(toks) <= 4 and s in toks and w >= 0.8:
                sc = w * (0.9 if len(toks) <= 2 else 0.7)
            elif len(st) > 1 and re.search(r"\b" + re.escape(s) + r"\b", f):
                sc = w * 0.9
            elif len(st) == 1 and s in toks:
                sc = w * 0.5
            elif len(f) >= 4 and abs(len(f) - len(s)) <= 3 and SequenceMatcher(None, f, s).ratio() >= 0.86:
                sc = w * 0.85
            else:
                continue
            best = max(best, sc)
        if field == "don_gia" and "gia" in toks and len(toks) <= 6:
            best = max(best, 0.9)       # a price word in the header is strong evidence
        if best:
            out[field] = best
    return out


def price_adjust(header, context_fold=""):
    """Score modifier for don_gia candidates (None = not a price)."""
    f = fold(header)
    if NOT_PRICE.search(f) and not re.search(r"\bbac 1\b", f):
        return None
    k = extras_key(header)
    if k in ("gia_co_vat",) or (k and k.startswith("bac_")):
        return -0.45
    adj = 0.0
    if VAT_EXCL.search(f):
        adj += 0.1
    # distinctive word of the header (e.g. 'si') present in the title text => it is the file's main price
    for w in f.split():
        if w in ("si", "le", "buon") and re.search(r"\bgia " + w + r"\b|\b" + w + r"\b", context_fold):
            adj += 0.15
    return adj


def assign(cands, order):
    """cands: {(col, field): score}. Greedy: each field gets <=1 col, each col <=1 field. Returns {field: (col, score)}."""
    out, used = {}, set()
    for (col, field), sc in sorted(cands.items(), key=lambda kv: (-kv[1], kv[0][0])):
        if field in out or col in used or sc <= 0:
            continue
        out[field] = (col, sc)
        used.add(col)
    return out


THRESHOLD = {"ma_hang": 0.85, "ten_hang": 0.85, "don_vi": 0.85, "don_gia": 0.85, "tien_te": 0.75, "hieu_luc_tu": 0.75}


def hard_check(field, p):
    """Design layer 5 hard checks; p is the column profile. True = column may be used for the field."""
    if not p or not p.get("n"):
        return False
    if field == "don_gia":
        return p["num_ratio"] >= 0.6
    if field == "ten_hang":
        return p["text_ratio"] >= 0.6 and p["avg_len"] >= 4
    if field == "don_vi":
        return p["avg_len"] < 12 and p["num_ratio"] < 0.6
    if field == "hieu_luc_tu":
        return p["date_ratio"] >= 0.5
    if field == "tien_te":
        return p["avg_len"] <= 6 and p["num_ratio"] < 0.5 and p.get("cur_ratio", 0) >= 0.6
    if field == "ma_hang":
        return not (p["top_freq"] > 0.2 and p["distinct"] < 0.5)
    return True


def rule_map(table, prof, context_fold=""):
    """Return (mapping {field: {col, conf, source, score}}, n_price_cands)."""
    cands, price_cands = {}, 0
    for col, name in table.names.items():
        key = extras_key(name)
        known_extra = key is not None and key not in ("gia_co_vat",) and not key.startswith("bac_")
        for fld, sc in header_scores(name).items():
            if known_extra and fld != "ten_hang":
                continue
            if fld == "hieu_luc_tu" and not re.search(r"hieu luc|ap dung", fold(name)) \
                    and re.search(r"\b(nhap|han|san xuat|sx|lap|tao|dat hang|giao|ky)\b", fold(name)):
                continue      # 'Ngày nhập', 'Hạn dùng' are not the effective date
            if fld == "don_gia":
                adj = price_adjust(name, context_fold)
                if adj is None:
                    continue
                sc += adj
                if sc >= 0.7:
                    price_cands += 1
            p = prof.get(col)
            if not hard_check(fld, p):
                sc *= 0.3
            if fld == "ten_hang" and re.search(r"doanh nghiệp|công ty|nhà sản xuất|hãng|nước|nhà cung|xuất xứ", name.lower()):
                sc *= 0.3           # company/manufacturer/country columns are not the item name
            if fld == "ma_hang" and p and p.get("n"):
                sc *= 1 - 0.8 * p["empty"]      # a sparse code column loses to a dense unique one
                if p["empty"] < 0.02 and p["distinct"] > 0.95:
                    sc += 0.1
            cands[(col, fld)] = sc
    mapping = {}
    for fld, (col, sc) in assign({k: v for k, v in cands.items() if v >= 0.2}, None).items():
        ok = hard_check(fld, prof.get(col))
        conf = (0.9 if sc >= 0.78 else 0.8 if sc >= 0.6 else 0.6) if ok else 0.3
        mapping[fld] = {"col": col, "conf": conf, "source": "rule", "score": sc}
    # fallback: no price header -> a VAT-inclusive/tier column is better than nothing
    if "don_gia" not in mapping:
        for col, name in table.names.items():
            k = extras_key(name)
            if (k == "gia_co_vat") and hard_check("don_gia", prof.get(col)) and col not in {m["col"] for m in mapping.values()}:
                mapping["don_gia"] = {"col": col, "conf": 0.6, "source": "rule", "score": 0.5}
                break
    # fallback: the longest text column is the name
    if "ten_hang" not in mapping:
        used = {m["col"] for m in mapping.values()}
        txt = [(p["avg_len"], c) for c, p in prof.items() if p.get("n") and c not in used and hard_check("ten_hang", p)
               and extras_key(table.names[c]) is None]
        if txt:
            mapping["ten_hang"] = {"col": max(txt)[1], "conf": 0.6, "source": "rule", "score": 0.4}
    # G3 (v2): no unit header matched -> a short text column whose values are known units is the unit column
    if RULES_V2.get() and "don_vi" not in mapping:
        used = {m["col"] for m in mapping.values()}
        for c, p in sorted(prof.items()):
            if c not in used and p.get("n") and p.get("unit_ratio", 0) >= 0.8 and hard_check("don_vi", p):
                mapping["don_vi"] = {"col": c, "conf": 0.9, "source": "rule", "score": 0.85}
                break
    return mapping, price_cands
