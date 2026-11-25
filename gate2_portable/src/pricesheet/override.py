"""Spec 2.4 override adapter + out.json enrichment (schema_version, file_sha256, queue ids/blocking, row table).

Core (pipeline.run) only takes {table_id: {field: column_letter}}. Everything else of the spec format is validated
here against the re-run result and applied as post-processing; what the core cannot honour is rejected as
OVERRIDE_INVALID (null mapping, multiplier different from the computed one, a column already used by another field,
a table whose header_rows/data_rows differ from the re-found one).
"""
import hashlib
import os
import re

from .grid import col_index, read_grid
from .mapping_rules import THRESHOLD
from .pipeline import run
from .sniff import sniff

FIELDS = tuple(THRESHOLD)
HTTP = {"OVERRIDE_STALE": 409, "OVERRIDE_INVALID": 422}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _tag_rows(res):
    """Core rows carry no table id: derive it from sheet + row number against each table's data_rows."""
    for r in res["rows"]:
        if "table" in r:
            continue
        sheet, _, n = r["nguon"].rpartition("!")
        r["table"] = next((t["id"] for t in res["tables"]
                           if t["sheet"] == sheet and t["data_rows"][0] <= int(n) <= t["data_rows"][1]), None)
    by_nguon = {r["nguon"]: r["table"] for r in res["rows"]}
    for q in res["review_queue"]:
        if q["kind"] == "row":
            q["table"] = by_nguon.get(q["nguon"])


def enrich(res, path):
    """Additive spec 2.3 keys the core does not emit. Never changes an existing value."""
    out = {"schema_version": 1, "file_sha256": sha256(path) if os.path.isfile(path) else None}
    out.update(res)
    _tag_rows(out)
    for i, q in enumerate(out["review_queue"]):
        q["id"] = f"q{i}"
        q["blocking"] = q["kind"] in ("price_choice", "context") or (q["kind"] == "mapping" and q["field"] == "don_gia")
    out["review_queue"] = [{k: q[k] for k in ("id", "kind", "table", "field", "nguon", "reason", "blocking")}
                           for q in out["review_queue"]]
    return out


def error_result(path, code, detail, mode="rule_first"):
    res = {"file": os.path.basename(path), "status": "error", "error_code": code, "error_detail": detail,
           "mode": mode, "tables": [], "rows": [], "review_queue": [], "warnings": [],
           "llm": {"model": None, "calls": 0, "tokens_in": 0, "tokens_out": 0, "usd": 0.0, "cache_hits": 0, "errors": 0},
           "seconds": 0.0}
    return enrich(res, path)


class OverrideError(Exception):
    def __init__(self, detail, code="OVERRIDE_INVALID"):
        super().__init__(detail)
        self.code, self.detail = code, detail


def _bad(cond, detail):
    if cond:
        raise OverrideError(detail)


def _check_shape(ov):
    _bad(not isinstance(ov, dict) or not isinstance(ov.get("tables"), dict), "override.tables phải là object")
    _bad(not isinstance(ov.get("rows", {}), dict), "override.rows phải là object")
    for tid, t in ov["tables"].items():
        _bad(not isinstance(t, dict), f"{tid}: không phải object")
        m = t.get("mapping", {})
        _bad(not isinstance(m, dict), f"{tid}.mapping phải là object")
        for f, c in m.items():
            _bad(f not in FIELDS, f"{tid}: trường lạ {f}")
            _bad(c is None, f"{tid}.{f}: bỏ trường (null) chưa hỗ trợ")
            _bad(not isinstance(c, str) or not re.fullmatch(r"[A-Za-z]{1,3}", c), f"{tid}.{f}: cột không hợp lệ")
        conf = t.get("confirmed", [])
        _bad(not isinstance(conf, list), f"{tid}.confirmed phải là list")
        for f in conf:
            _bad(f != "multiplier" and f not in m, f"{tid}: confirmed {f} không có trong mapping")
        _bad("multiplier" in t and t["multiplier"] not in (1, 1000, 1000000), f"{tid}.multiplier ngoài 1, 1000, 1000000")
    for k, v in ov.get("rows", {}).items():
        _bad(not isinstance(v, dict) or v.get("trang_thai") not in ("ok", "bo"), f"{k}: trang_thai phải là ok hoặc bo")


def _status(res):
    ws = {w["code"] for w in res["warnings"]}
    bad = (res["review_queue"] or any(r["trang_thai"] == "can_xem" for r in res["rows"])
           or ws & {"TONG_LECH", "NO_PRICE_COLUMN", "LLM_UNAVAILABLE"}
           or any(not t.get("ledger", {}).get("reconciled", True) for t in res["tables"]))
    res["status"] = "needs_review" if bad else "ok"


def _apply(path, ov, mode, lenient_rows):
    _check_shape(ov)
    if ov.get("file_sha256") != sha256(path):
        raise OverrideError("file_sha256 khác file đang chạy", "OVERRIDE_STALE")
    core_ov = {tid: {f: c.upper() for f, c in (t.get("mapping") or {}).items()} for tid, t in ov["tables"].items()}
    kind, code, _ = sniff(path)
    sheets = {} if code else {s.name: s for s in read_grid(path, kind).sheets}
    for tid, t in ov["tables"].items():
        _bad(t.get("sheet") not in sheets, f"{tid}: không có sheet {t.get('sheet')}")
        for f, c in core_ov[tid].items():
            _bad(col_index(c) > sheets[t["sheet"]].ncols, f"{tid}.{f}: cột {c} ngoài sheet")
    res = run(path, mode, use_llm=False, use_cache=False, override=core_ov)
    if res["status"] == "error":
        return res
    _tag_rows(res)
    by_id = {t["id"]: t for t in res["tables"]}
    for tid, t in ov["tables"].items():
        cur = by_id.get(tid)
        _bad(cur is None or cur["sheet"] != t["sheet"], f"{tid}: không có trong kết quả tính lại")
        for k in ("header_rows", "data_rows"):
            _bad(k in t and t[k] != cur[k], f"{tid}.{k} khác bảng tìm lại (chạy lại không dùng bảng cũ được)")
        cols = [m["col"] for m in cur["mapping"].values()]
        _bad(len(cols) != len(set(cols)), f"{tid}: một cột thuộc hai trường (bỏ trường kia chưa hỗ trợ)")
        _bad("multiplier" in t and t["multiplier"] != cur.get("context", {}).get("multiplier", {}).get("value", 1),
             f"{tid}.multiplier khác hệ số tính được (đổi hệ số chưa hỗ trợ)")
    # tables absent from override are dropped
    keep = set(ov["tables"])
    res["tables"] = [t for t in res["tables"] if t["id"] in keep]
    res["rows"] = [r for r in res["rows"] if r["table"] in keep]
    res["review_queue"] = [q for q in res["review_queue"] if q["table"] in keep]
    # close queue items (4.3.4); fields overridden but not confirmed keep their item from the rules-only baseline
    closing = {(tid, f) for tid, t in ov["tables"].items() for f in t.get("confirmed") or []}
    pending = {(tid, f) for tid in core_ov for f in core_ov[tid]} - closing
    if pending:
        base = run(path, mode, use_llm=False, use_cache=False)
        res["review_queue"] += [q for q in base["review_queue"]
                                if q["kind"] == "mapping" and (q["table"], q["field"]) in pending]
    res["review_queue"] = [q for q in res["review_queue"] if not (
        (q["kind"] == "mapping" and (q["table"], q["field"]) in closing)
        or (q["kind"] == "price_choice" and (q["table"], "don_gia") in closing)
        or (q["kind"] == "context" and (q["table"], "multiplier") in closing))]
    # rows: can_xem -> ok/bo
    rows = {r["nguon"]: r for r in res["rows"]}
    for k, v in ov.get("rows", {}).items():
        r = rows.get(k)
        if r is None or r["trang_thai"] != "can_xem":
            if k in lenient_rows:
                continue
            raise OverrideError(f"{k}: không có trong kết quả tính lại" if r is None else f"{k}: không ở can_xem")
        if v["trang_thai"] == "ok":
            try:
                bad_price = float(r["don_gia"]) <= 0
            except (TypeError, ValueError):
                bad_price = True
            _bad(bad_price, f"{k}: giá rỗng hoặc ≤ 0")
        r["trang_thai"] = v["trang_thai"]
        r["ma_van_de"] = r["ma_van_de"] + ["DUYET_TAY"]
        res["review_queue"] = [q for q in res["review_queue"] if not (q["kind"] == "row" and q["nguon"] == k)]
    _status(res)
    return res


def apply_override(path, ov, mode="rule_first", lenient_rows=()):
    """Run with a spec-2.4 override: 0 model calls. Always returns an out.json dict (error dict if rejected).
    lenient_rows: row keys silently skipped when no longer can_xem (decisions kept from earlier review steps)."""
    try:
        return enrich(_apply(path, ov, mode, set(lenient_rows)), path)
    except OverrideError as e:
        return error_result(path, e.code, e.detail, mode)
