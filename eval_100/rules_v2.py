"""Bản thử nghiệm sửa luật (vá lúc chạy, KHÔNG sửa code tool). import rules_v2; rules_v2.apply() trước khi gọi normalize.
G1  thêm từ đồng nghĩa còn thiếu: 'mat hang', 't hang', 'price excl vat', 'net price', 'dvi'
G2  tiêu đề viết tắt có dấu câu: 'Đ/v' -> 'd v' -> ghép thành 'dv' khi tổng độ dài <= 4
G3  nhận cột ĐVT theo nội dung khi tiêu đề không khớp: cột chữ ngắn, >= 80% giá trị là đơn vị đã biết
"""
from src.pricesheet import mapping_rules as mr
from src.pricesheet import normalize as nz
from src.pricesheet import pipeline as pl


def apply():
    mr.SYN["ten_hang"].update({"mat hang": 1, "ten mat hang": 1, "t hang": 0.9, "ten sp": 1})
    mr.SYN["don_gia"].update({"price excl vat": 1, "net price": 0.95, "unit price excl vat": 1, "gia phan phoi": 0.9})
    mr.SYN["don_vi"].update({"dvi": 0.9})
    mr._scores.cache_clear()

    orig_hs = mr.header_scores

    def header_scores(h):
        out = orig_hs(h)
        f = nz.fold(h)
        compact = f.replace(" ", "")
        if " " in f and len(compact) <= 4:          # 'd v' -> 'dv', 'd vi' -> 'dvi'
            for fld, sc in mr._scores(compact).items():
                out[fld] = max(out.get(fld, 0), sc)
        return out
    mr.header_scores = header_scores
    pl.header_scores = header_scores

    orig_rm = mr.rule_map

    def rule_map(table, prof, context_fold=""):
        mapping, n = orig_rm(table, prof, context_fold)
        if "don_vi" not in mapping:
            used = {m["col"] for m in mapping.values()}
            for c, p in prof.items():
                if c in used or not p.get("n") or not mr.hard_check("don_vi", p):
                    continue
                vals = p.get("_vals")
                if vals and sum(1 for v in vals if nz.fold(v) in nz.UNIT_CANON) >= 0.8 * len(vals):
                    mapping["don_vi"] = {"col": c, "conf": 0.9, "source": "rule", "score": 0.85}
                    break
        return mapping, n
    mr.rule_map = rule_map
    pl.rule_map = rule_map

    from src.pricesheet import profile as pf
    orig_pc = pf.profile_columns

    def profile_columns(sh, t):
        prof = orig_pc(sh, t)
        from src.pricesheet.tables import row_cells
        for c in prof:
            vals = []
            for r in range(t.first_data, min(t.last_data, t.first_data + 60) + 1):
                x = row_cells(sh, r).get(c)
                if x is not None and x.kind == "s" and str(x.v).strip():
                    vals.append(str(x.v).strip())
            prof[c]["_vals"] = vals
        return prof
    pl.profile_columns = profile_columns
