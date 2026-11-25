"""Layer 6+7: classify every row of the data region and build one output row per goods row."""
import re
from collections import Counter
from decimal import Decimal

from .grid import col_letter, col_index
from .mapping_rules import extras_key
from .normalize import (clean_text, date_vote, dec_str, eval_formula, extras_value, fold, norm_code,
                        cell_currency, norm_currency, norm_unit, parse_date, parse_price, sep_vote, unit_from_spec)
from .tables import row_cells

NOTE_RE = re.compile(r"^(ghi chu|luu y|chu thich|nguoi lap|ke toan|giam doc|tong giam doc|ben mua|ben ban|chu ky|ky ten|noi nhan|ghi chu|dieu khoan|note|xin cam on|trang \d+|page \d+)")
TOTAL_RE = re.compile(r"^(tổng|cộng|total|sum|subtotal)\b")   # accented: "Công ty" is not "Cộng"


def vmerge_map(sh):
    """(row, col) -> (top_row, col) for cells inside a vertical merge (excluding the top-left cell)."""
    m = {}
    for r1, c1, r2, c2 in sh.merges:
        if r2 > r1:
            for r in range(r1 + 1, r2 + 1):
                for c in range(c1, c2 + 1):
                    m[(r, c)] = (r1, c1)
    return m


def column_styles(sh, rows, price_col, date_col):
    """Column-level number-separator style and date order, from cells that prove it by themselves."""
    vn = us = 0
    for r in rows:
        x = sh.cells.get((r, price_col)) if price_col else None
        if x is not None and x.kind == "s":
            m = re.search(r"[-+]?\d[\d.,\s]*", clean_text(x.v))
            if m:
                v = sep_vote(m.group(0).strip().rstrip(".,"))
                core = m.group(0)
                vn += v == "vn" or (v == "amb" and "." in core)     # '65.000' leans Vietnamese thousands
                us += v == "us" or (v == "amb" and "," in core)     # '11,025' leans US thousands
    style = "us" if us > vn else "vn"
    dmy = mdy = 0
    for r in rows:
        x = sh.cells.get((r, date_col)) if date_col else None
        if x is not None and x.kind == "s":
            v = date_vote(x.v)
            dmy += v == "dmy"
            mdy += v == "mdy"
    order = "dmy" if dmy and not mdy else "mdy" if mdy and not dmy else (None if dmy and mdy else "dmy")
    return style, order


def build_rows(wb, sh, table, mapping, ctx, profile_cols):
    """Return (rows, totals, skipped) for one table."""
    col = {f: m["col"] for f, m in mapping.items()}
    vm = vmerge_map(sh)
    rows_idx = [r for r in range(table.first_data, table.last_data + 1)
                if r not in sh.hidden_rows and r not in table.repeat_header_rows]
    mult = Decimal(ctx["multiplier"]["value"]) if ctx.get("multiplier") else Decimal(1)
    style, order = column_styles(sh, rows_idx, col.get("don_gia"), col.get("hieu_luc_tu"))
    if col.get("hieu_luc_tu"):
        hf = fold(table.names.get(col["hieu_luc_tu"], ""))
        if "mm dd" in hf or "mdy" in hf:
            order = "mdy"
        elif "dd mm" in hf:
            order = "dmy"
    mapped_cols = set(col.values())
    spec_col = next((c for c, n in table.names.items() if extras_key(n) == "quy_cach"), None)
    extras_cols = [c for c in table.cols if c not in mapped_cols and c not in sh.hidden_cols]
    ekeys = {}
    for c in extras_cols:
        ekeys[c] = extras_key(table.names[c]) or clean_text(table.names[c])
    ctx_cur = ctx.get("tien_te", {}).get("value") if ctx.get("tien_te") else None

    def val(r, c):
        x = sh.cells.get((r, c))
        if x is None and (r, c) in vm:
            x = sh.cells.get(vm[(r, c)])
        return x

    def numeric(c_letters, r):
        x = sh.cells.get((r, col_index(c_letters)))
        if x is None:
            return None
        if x.kind == "n":
            return Decimal(str(x.v))
        if x.v is None and x.f:
            return formula_val(x, r, depth=1)
        return None

    def formula_val(x, r, depth=0):
        return eval_formula(x.f, lambda cl, rr: numeric(cl, rr) if rr == r and depth < 2 else None)

    out, totals, skipped = [], [], {"hidden": len([r for r in range(table.first_data, table.last_data + 1) if r in sh.hidden_rows]),
                                    "blank": 0, "group": 0, "total": 0, "note": 0, "repeat": len(table.repeat_header_rows)}
    group = None
    run_sum = {"all": Decimal(0), "grp": Decimal(0)}
    pending_groups = []   # (index in skipped list) not needed; groups attach to following rows
    has_ma = "ma_hang" in col
    narrow = len(table.cols) <= 2 or sum(1 for p in profile_cols.values() if p.get("n")) <= 2   # name+price only: no group lines
    for r in rows_idx:
        cells = row_cells(sh, r)
        if not cells:
            skipped["blank"] += 1
            continue
        texts = [clean_text(x.v) for x in cells.values() if x.kind == "s"]
        ntext = len(texts)
        ft = fold(texts[0]) if texts else ""
        # "(1) (2) (3)" column-number row
        if all(x.kind in ("s", "n") and re.fullmatch(r"\(?\d{1,2}\)?", clean_text(x.v)) for x in cells.values()) and len(cells) >= 3:
            skipped["note"] += 1
            continue
        ma_x, ten_x = val(r, col["ma_hang"]) if has_ma else None, val(r, col["ten_hang"]) if "ten_hang" in col else None
        ma_empty = ma_x is None or ma_x.v is None
        ten_empty = ten_x is None or ten_x.v is None
        price_x = sh.cells.get((r, col["don_gia"])) if "don_gia" in col else None
        # total row: label text, no code, a number somewhere in the price column
        if ma_empty and any(TOTAL_RE.match(t.lower()) for t in texts):
            pv = None     # only a total printed in the price column can be checked against the prices
            if price_x is not None and price_x.v is not None and price_x.kind in ("n", "s"):
                pv = parse_price(price_x.v, price_x.kind, style, mult)[0]
            lab = " ".join(texts)
            totals.append({"row": r, "printed": pv, "label": lab, "group_total": "nhom" in fold(lab),
                           "sum_all": run_sum["all"], "sum_grp": run_sum["grp"]})
            run_sum["grp"] = Decimal(0)
            skipped["total"] += 1
            continue
        price_blank = price_x is None or price_x.v is None
        if (ma_empty and ten_empty and price_blank) or (len(cells) < 2 and not narrow):
            # group header or note (single-cell / merged line)
            if texts and len(texts) == len(cells) and len(cells) == 1 and not NOTE_RE.match(fold(texts[0])):
                group = texts[0]
                skipped["group"] += 1
            else:
                skipped["note"] += 1
            continue
        if price_blank and any(NOTE_RE.match(fold(t)) for t in texts):
            skipped["note"] += 1
            continue
        if ten_empty and ma_x is not None and (" " in clean_text(ma_x.v) or not any(ch.isdigit() for ch in clean_text(ma_x.v))):
            skipped["note"] += 1      # words in the code column and nothing else: signature/note line
            continue
        row = {"nguon": f"{sh.name}!{r}", "ma_hang": "", "ten_hang": "", "don_vi": "", "don_gia": "", "tien_te": "VND",
               "hieu_luc_tu": "", "extras": {}, "trang_thai": "ok", "ma_van_de": [], "src": {}, "_r": r}
        issues, status_bo, status_review = [], False, False
        # --- code
        if has_ma:
            if not ma_empty:
                code, iss, rev = norm_code(ma_x.v, ma_x.kind, ma_x.fmt)
                row["ma_hang"] = code
                issues += iss
                status_review |= rev
                row["src"]["ma_hang"] = f"{col_letter(col['ma_hang'])}{r}"
            else:
                issues.append("THIEU_MA")
                status_review = True
        else:
            issues.append("THIEU_MA")
            status_review = True
        # --- name
        if not ten_empty:
            row["ten_hang"] = clean_text(ten_x.v) if ten_x.kind == "s" else str(ten_x.v)
            row["src"]["ten_hang"] = f"{col_letter(col['ten_hang'])}{r}"
        # --- unit
        if "don_vi" in col:
            ux = val(r, col["don_vi"])
            if ux is not None and ux.v is not None:
                u, iss = norm_unit(ux.v)
                row["don_vi"] = u
                issues += iss
                status_review |= "DVT_NHIEU_KIEU" in iss and len(u) == 1
                row["src"]["don_vi"] = f"{col_letter(col['don_vi'])}{r}"
        else:
            issues.append("THIEU_DVT")
        if not row["don_vi"] and spec_col:
            sx = val(r, spec_col)
            if sx is not None and sx.v is not None and "don_vi" not in col:
                row["don_vi"] = unit_from_spec(sx.v)
        # --- price
        if "don_gia" in col:
            row["src"]["don_gia"] = f"{col_letter(col['don_gia'])}{r}"
            if price_x is None:
                d, iss, reason = None, ["GIA_TRONG"], "empty"
            elif price_x.v is None and price_x.f:
                d = formula_val(price_x, r)
                if d is None:
                    d, iss, reason = None, ["FORMULA_NOT_CACHED"], "formula"
                else:
                    d, iss, reason = parse_price(d, "n", style, mult)[0], ["GIA_CONG_THUC"], None
            else:
                d, iss, reason = parse_price(price_x.v, price_x.kind, style, mult)
                if price_x.f and price_x.v is not None:
                    iss = iss + ["GIA_CONG_THUC"]
            issues += iss
            if d is not None:
                row["don_gia"] = dec_str(d)
            if reason in ("empty", "text", "error", "zero"):
                status_bo = True
            elif reason in ("range", "formula"):
                status_review = True
            if mult != 1:
                issues.append("GIA_NGHIN")
        # --- currency
        tx = val(r, col["tien_te"]) if "tien_te" in col else None
        if tx is not None and tx.v is not None:
            row["tien_te"] = norm_currency(tx.v) or "VND"
            row["src"]["tien_te"] = f"{col_letter(col['tien_te'])}{r}"
        elif price_x is not None and cell_currency(price_x.v):
            row["tien_te"] = cell_currency(price_x.v)
            row["src"]["tien_te"] = row["src"].get("don_gia", "")
        elif ctx_cur:
            row["tien_te"] = ctx_cur
            row["src"]["tien_te"] = ctx["tien_te"]["cell"] or ""
        else:
            issues.append("THIEU_TIEN_TE")
        if row["tien_te"] != "VND":
            issues.append("TIEN_TE_LA")
            status_bo = True
        # --- date
        dx = val(r, col["hieu_luc_tu"]) if "hieu_luc_tu" in col else None
        if dx is not None and dx.v is not None:
            iso, iss, amb = parse_date(dx.v, dx.kind, order, wb.epoch1904)
            issues += iss
            if iso:
                row["hieu_luc_tu"] = iso
                row["src"]["hieu_luc_tu"] = f"{col_letter(col['hieu_luc_tu'])}{r}"
            if amb or "HIEU_LUC_THU_HOI" in iss:
                status_review = True
        if not row["hieu_luc_tu"]:
            if ctx.get("hieu_luc_tu") and not (dx is not None and dx.v is not None and ("NGAY_MY" in issues or "HIEU_LUC_THU_HOI" in issues)):
                row["hieu_luc_tu"] = ctx["hieu_luc_tu"]["value"]
                row["src"]["hieu_luc_tu"] = ctx["hieu_luc_tu"]["cell"] or ""
            elif "hieu_luc_tu" not in col:
                issues.append("THIEU_NGAY")
        # --- extras
        ex = {}
        if group:
            ex["nhom"] = group
        for c in extras_cols:
            v = extras_value(val(r, c))
            if v is None and (r, c) in sh.empty_str:
                v = ""
            if v is not None:
                ex[ekeys[c]] = v
        if "quy_cach" in ex and spec_col is not None and "don_vi" not in col:
            pass
        row["extras"] = ex
        row["ma_van_de"] = list(dict.fromkeys(issues))
        row["trang_thai"] = "bo" if status_bo else "can_xem" if status_review else "ok"
        if row["don_gia"] and not status_bo:
            run_sum["all"] += Decimal(row["don_gia"])
            run_sum["grp"] += Decimal(row["don_gia"])
        out.append(row)
    skipped["data"] = len(out)
    skipped["region"] = table.last_data - table.first_data + 1
    return out, totals, skipped
