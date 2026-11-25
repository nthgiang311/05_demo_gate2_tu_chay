"""Layer 8: cross-row checks (duplicates, totals)."""
import json
from decimal import Decimal

from .normalize import dec_str


SEQ_KEYS = {"stt", "tt", "no", "no.", "số thứ tự", "so thu tu", "#"}


def check_duplicates(rows):
    """Exact duplicate -> later row 'bo' (TRUNG_DONG); same code, other price -> both can_xem; same name, other code -> note."""
    seen, by_code, by_name = {}, {}, {}
    for r in rows:
        code = r["ma_hang"].casefold()
        if not code and r["ten_hang"]:   # no code: duplicate = identical in every mapped field and extras
            key = ("", r["ten_hang"], r["don_vi"], r["don_gia"], r["hieu_luc_tu"], json.dumps({k: v for k, v in r["extras"].items() if k.lower() not in SEQ_KEYS}, sort_keys=True, default=str))
            if key in seen:
                r["ma_van_de"].append("TRUNG_DONG")
                r["trang_thai"] = "bo"
                continue
            seen[key] = r
        if code:
            key = (code, r["ten_hang"], r["don_vi"], r["don_gia"])
            if key in seen and r["trang_thai"] != "bo":
                code_note = "TRUNG_DONG" if seen[key]["ma_hang"] == r["ma_hang"] else "MA_HOA_THUONG"
                r["ma_van_de"].append(code_note)
                r["trang_thai"] = "bo"
                continue
            seen.setdefault(key, r)
            by_code.setdefault(code, []).append(r)
        if r["ten_hang"]:
            by_name.setdefault(r["ten_hang"], []).append(r)
    for code, rs in by_code.items():
        live = [r for r in rs if r["trang_thai"] != "bo" or r["don_gia"]]
        prices = {r["don_gia"] for r in live if r["trang_thai"] != "bo"}
        if len({r["nguon"] for r in rs}) > 1 and len(prices) > 1:
            for r in rs:
                if r["trang_thai"] == "ok":
                    r["trang_thai"] = "can_xem"
                if "TRUNG_MA_KHAC_GIA" not in r["ma_van_de"]:
                    r["ma_van_de"].append("TRUNG_MA_KHAC_GIA")
    for name, rs in by_name.items():
        codes = {r["ma_hang"] for r in rs}
        if len(rs) > 1 and len(codes) > 1:
            for r in rs:
                r["ma_van_de"].append("TRUNG_TEN_KHAC_MA")


def check_totals(totals):
    """Compare printed totals with the sum of the data rows above; returns (table_totals, warnings)."""
    out, warns = [], []
    for t in totals:
        if t["printed"] is None:
            continue
        grand = "tổng" in t["label"].lower()
        computed = t["sum_all"] if grand and not t["group_total"] else t["sum_grp"]
        match = abs(t["printed"] - computed) <= Decimal("0.5") or abs(t["printed"] - t["sum_all"]) <= Decimal("0.5")
        out.append({"row": t["row"], "printed": dec_str(t["printed"]), "computed": dec_str(computed), "match": match})
        if not match:
            warns.append({"code": "TONG_LECH", "detail": f"dòng {t['row']}: ghi {dec_str(t['printed'])}, cộng được {dec_str(computed)}"})
    return out, warns
