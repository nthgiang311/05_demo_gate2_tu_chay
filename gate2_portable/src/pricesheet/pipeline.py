"""Layers 0-10 glued together: run(path) -> result dict (the X.out.json contract)."""
import os
import time
from decimal import Decimal

from . import context as ctxmod
from . import mapping_llm
from .checks import check_duplicates, check_totals
from .grid import col_index, col_letter, read_grid
from .mapping_rules import THRESHOLD, hard_check, header_scores, rule_map
from .normalize import MONTH_RE, clean_text, fold
from .profile import profile_columns
from .rows import build_rows
from .sniff import sniff
from .tables import find_tables, make_table, row_cells

MAX_BYTES, MAX_ROWS, MAX_SHEETS = 10 * 1024 * 1024, 50000, 20


def _err(res, code, detail=None):
    res.update(status="error", error_code=code, error_detail=detail, tables=res.get("tables", []), rows=[])
    return res


def run(path, mode="rule_first", use_llm=True, use_cache=True, override=None):
    t0 = time.time()
    res = {"file": os.path.basename(path), "status": "ok", "error_code": None, "error_detail": None, "mode": mode,
           "tables": [], "rows": [], "review_queue": [], "warnings": [],
           "llm": {"model": mapping_llm.MODEL, "calls": 0, "tokens_in": 0, "tokens_out": 0, "usd": 0.0,
                   "cache_hits": 0, "errors": 0}}
    try:
        _run(path, res, mode, use_llm, use_cache, override or {})
    except Exception as e:  # never crash on a bad file
        _err(res, "INTERNAL_ERROR", f"{type(e).__name__}: {str(e)[:200]}")
    res["llm"]["usd"] = round(res["llm"]["usd"], 6)
    res["seconds"] = round(time.time() - t0, 3)
    return res


def _run(path, res, mode, use_llm, use_cache, override):
    kind, code, detail = sniff(path)
    if code:
        return _err(res, code, detail)
    if os.path.getsize(path) > MAX_BYTES:
        return _err(res, "FILE_TOO_LARGE", "Hơn 10 MB")
    try:
        wb = read_grid(path, kind)
    except MemoryError:
        return _err(res, "TOO_MANY_ROWS", "Sheet quá lớn")
    except Exception as e:
        msg = str(e)
        if "encrypt" in msg.lower() or "password" in msg.lower():
            return _err(res, "FILE_ENCRYPTED", "File có mật khẩu")
        return _err(res, "FILE_CORRUPT", f"Không đọc được file: {type(e).__name__}")
    visible = [s for s in wb.sheets if not s.hidden]
    if len(visible) > MAX_SHEETS:
        return _err(res, "TOO_MANY_SHEETS", f"{len(visible)} sheet")
    if any(s.nrows > MAX_ROWS for s in visible):
        return _err(res, "TOO_MANY_ROWS", f"Hơn {MAX_ROWS} dòng một sheet")
    if not any(s.cells for s in wb.sheets):
        return _err(res, "FILE_EMPTY", "File không có ô nào")
    for s in wb.sheets:
        if s.hidden:
            res["warnings"].append({"code": "SHEET_AN_BO_QUA", "detail": s.name})

    found = []
    for s in visible:
        tabs = find_tables(s)
        if not tabs:
            if s.cells:
                res["warnings"].append({"code": "SHEET_KHONG_CO_BANG", "detail": s.name})
            continue
        found += [(s, t) for t in tabs]
    if not found and mode == "llm_all" and use_llm and visible:
        s = max(visible, key=lambda x: len(x.cells))
        t = _llm_header_table(s, res, use_cache)
        if t:
            found = [(s, t)]
    if not found:
        return _err(res, "NO_HEADER_FOUND", "Không tìm ra dòng tiêu đề")

    all_rows, tables_out, totals_warn, missing_price = [], [], [], 0
    table_sheets = {id(s) for s, _ in found}
    wb_date = ctxmod.workbook_date([sh for sh in wb.sheets if id(sh) not in table_sheets])
    for i, (s, t) in enumerate(found):
        t.id = f"t{i}"
        tj = _process_table(wb, s, t, res, mode, use_llm, use_cache, override, wb_date)
        tables_out.append(tj["table"])
        all_rows += tj["rows"]
        totals_warn += tj["warns"]
        missing_price += tj["no_price"]
    res["tables"] = tables_out
    res["warnings"] += totals_warn
    if not all_rows:
        if missing_price:
            horiz = any(w["code"] == "BANG_NGANG" for w in res["warnings"])
            return _err(res, "NO_PRICE_COLUMN", "Bảng giá dạng ngang (giá theo tháng) chưa hỗ trợ" if horiz else "Không có cột giá")
        return _err(res, "NO_DATA_ROWS", "Có tiêu đề nhưng không có dòng hàng")
    check_duplicates(all_rows)
    for r in all_rows:
        r.pop("_r", None)
        if r["trang_thai"] == "can_xem":
            res["review_queue"].append({"kind": "row", "table": None, "field": None, "nguon": r["nguon"],
                                        "reason": ";".join(r["ma_van_de"])})
    res["rows"] = all_rows
    if any(w["code"] in ("NO_PRICE_COLUMN", "TONG_LECH") for w in res["warnings"]) or res["review_queue"]:
        res["status"] = "needs_review"


def _llm_header_table(s, res, use_cache):
    """No rule-based table: ask the model for header rows on the first 20 rows of the busiest sheet."""
    t = make_table(s, [1], first_data=2, last_data=s.nrows)
    t.names = {c: "" for c in range(1, s.ncols + 1)}
    prof = profile_columns(s, t)
    prop = mapping_llm.call(mapping_llm.build_prompt(s, t, prof, []), res["llm"], use_cache)
    if not prop:
        return None
    hdr, maps = mapping_llm.validate(prop, s, t, prof)
    # a real header row names at least one field; a data row proposed as header is refused
    hdr = [r for r in hdr if any(header_scores(x.v) for x in row_cells(s, r).values() if x.kind == "s")]
    if not hdr or "don_gia" not in maps and "ten_hang" not in maps:
        return None
    return make_table(s, hdr)


def _merge(mode, rule, llm, prof):
    """Resolve all fields jointly, one column per field and one field per column.
    Rule columns are placed first; a model proposal can only fill a field the rules left open (or whose rule column
    failed the hard checks) and can never take a column that a rule already uses."""
    out, used = {}, set()
    reserved = {r["col"] for r in rule.values() if r["conf"] > 0.3}      # columns the rules assigned to some field
    order = sorted(rule, key=lambda f: -rule[f]["conf"])
    for f in order:
        r, m = rule[f], llm.get(f)
        m_ok = m is not None and hard_check(f, prof.get(m)) and m not in used and (m == r["col"] or m not in reserved)
        r_ok = r["conf"] > 0.3
        if r["col"] in used:
            continue
        if m_ok and m == r["col"]:
            out[f] = {"col": m, "conf": 0.95, "source": "both"}
        elif m_ok and not r_ok:
            out[f] = {"col": m, "conf": 0.8, "source": "llm"}
        elif m_ok and mode == "llm_all" and f != "don_gia":      # price choice between columns stays with the spec rules
            out[f] = {"col": m, "conf": 0.5, "source": "llm"}
        elif m_ok:
            out[f] = {"col": r["col"], "conf": 0.5, "source": "rule"}
        else:
            out[f] = {"col": r["col"], "conf": min(r["conf"], 0.9), "source": "rule"}
        used.add(out[f]["col"])
    for f, m in llm.items():
        if f not in out and m not in used and hard_check(f, prof.get(m)):
            out[f] = {"col": m, "conf": 0.8, "source": "llm"}
            used.add(m)
    return out


def _process_table(wb, s, t, res, mode, use_llm, use_cache, override, wb_date=None):
    prof = profile_columns(s, t)
    ctx = ctxmod.scan(s, t)
    rules, n_price = rule_map(t, prof, ctx["text_fold"])
    rule_cols = {f: m for f, m in rules.items()}
    llm_cols, eff_cell = {}, None
    need = (mode == "llm_all" or "ten_hang" not in rules or "don_gia" not in rules or n_price >= 2
            or any(m["conf"] < THRESHOLD[f] for f, m in rules.items()))
    if use_llm and need:
        prop = mapping_llm.call(mapping_llm.build_prompt(s, t, prof, ctx), res["llm"], use_cache)
        if prop:
            hdr, llm_cols = mapping_llm.validate(prop, s, t, prof)
            eff_cell = prop.effective_date_cell
        elif mode == "rule_first":
            res["warnings"].append({"code": "LLM_UNAVAILABLE", "detail": f"{s.name}: dùng luật"})
    month_cols = {c for c, n in t.names.items() if MONTH_RE.search(n)}
    if len(month_cols) >= 2:   # prices per month as columns (horizontal table): not supported, never pick one month silently
        rule_cols = {f: m for f, m in rule_cols.items() if m["col"] not in month_cols}
        llm_cols = {f: c for f, c in llm_cols.items() if c not in month_cols}
        res["warnings"].append({"code": "BANG_NGANG", "detail": f"{t.id} ({s.name}): giá theo tháng dạng cột, chưa hỗ trợ"})
    merged = _merge(mode, rule_cols, llm_cols, prof)
    for f, colname in override.get(t.id, {}).items():
        merged[f] = {"col": col_index(colname), "conf": 1.0, "source": "override"}
    price_header = t.names.get(merged["don_gia"]["col"], "") if "don_gia" in merged else ""
    ctx = ctxmod.scan(s, t, price_header)
    if not ctx["hieu_luc_tu"] and eff_cell:
        try:
            c = s.cells.get((int("".join(ch for ch in eff_cell if ch.isdigit())), col_index("".join(ch for ch in eff_cell if ch.isalpha()).upper())))
            d = ctxmod.find_date(c.v.strftime("%d/%m/%Y") if c is not None and c.kind == "d" else clean_text(c.v)) if c is not None and c.v is not None else None
            if d:
                ctx["hieu_luc_tu"] = {"value": d, "cell": eff_cell.upper()}
        except Exception:
            pass
    if not ctx["hieu_luc_tu"] and "hieu_luc_tu" not in merged and wb_date:
        ctx["hieu_luc_tu"] = wb_date       # one effective-date statement elsewhere in the workbook applies to every table
    tj = {"id": t.id, "sheet": s.name, "header_rows": t.header_rows, "data_rows": [t.first_data, t.last_data],
          "repeat_header_rows": [], "mapping": {}, "context": {}, "totals": []}
    for f, m in merged.items():
        ev = [f"{col_letter(m['col'])}{r}" for r in t.header_rows if (r, m["col"]) in s.cells]
        review = m["conf"] < THRESHOLD[f]
        tj["mapping"][f] = {"col": col_letter(m["col"]), "confidence": m["conf"], "source": m["source"],
                            "evidence": ev, "review": review}
        if review:
            res["review_queue"].append({"kind": "mapping", "table": t.id, "field": f, "nguon": None,
                                        "reason": f"độ tin cậy {m['conf']} dưới ngưỡng {THRESHOLD[f]} ({m['source']})"})
    out = {"table": tj, "rows": [], "warns": [], "no_price": 0}
    if "don_gia" not in merged:
        res["warnings"].append({"code": "NO_PRICE_COLUMN", "detail": f"{t.id} ({s.name}) không có cột giá"})
        out["no_price"] = 1
        return out
    if "ten_hang" not in merged and "ma_hang" not in merged:
        res["warnings"].append({"code": "NO_NAME_OR_CODE", "detail": f"{t.id} ({s.name})"})
        return out
    mapping = {f: {"col": m["col"]} for f, m in merged.items()}
    rows, totals, skipped = build_rows(wb, s, t, mapping, ctx, prof)
    tj["repeat_header_rows"] = t.repeat_header_rows
    tj["context"] = {
        "hieu_luc_tu": ctx["hieu_luc_tu"], "tien_te": ctx["tien_te"],
        "multiplier": {"value": int(ctx["multiplier"]["value"]) if ctx["multiplier"] else 1,
                       "cell": ctx["multiplier"]["cell"] if ctx["multiplier"] else None}}
    tj["ledger"] = skipped      # rows of the table region by kind; data+hidden+blank+group+total+note+repeat == region
    tj["ledger"]["reconciled"] = sum(v for k, v in skipped.items() if k not in ("region", "reconciled")) == skipped["region"]
    tj["totals"], out["warns"] = check_totals(totals)
    out["rows"] = rows
    if not rows:
        res["warnings"].append({"code": "NO_DATA_ROWS", "detail": f"{t.id} ({s.name})"})
    return out
