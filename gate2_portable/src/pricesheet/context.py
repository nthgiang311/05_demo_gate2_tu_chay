"""Layer 3: context above/below the table: effective date, currency, price multiplier."""
import re
from decimal import Decimal

from .grid import col_letter
from .normalize import clean_text, fold, parse_date, DATE_RE, VNDATE_RE, MONTH_RE, _mk, _year
from .tables import row_cells

EFFECTIVE = re.compile(r"ap dung|hieu luc|valid|effective|tu ngay|bang gia ngay|ngay bao gia|cap nhat")
MULT_PATTERNS = [
    (re.compile(r"(?:don vi|dvt|unit)[^0-9a-z]*(?:tinh|tien)?[^0-9a-z]*(1\s?[.,]?\s?000\s?[.,]?\s?000|trieu)"), Decimal(1000000)),
    (re.compile(r"(?:don vi|dvt|unit)[^0-9a-z]*(?:tinh|tien)?[^0-9a-z]*(1\s?[.,]?\s?000|nghin|ngan|k\b)"), Decimal(1000)),
    (re.compile(r"\(\s*(nghin|ngan)\s*dong\s*\)|\bx\s?1\s?[.,]?\s?000\b|\bnghin dong\b|\bngan dong\b|\b1\s?[.,]?\s?000\s?(?:d|dong|vnd)\b"), Decimal(1000)),
    (re.compile(r"\(\s*trieu\s*dong\s*\)|\btrieu dong\b|\bx\s?1\s?[.,]?\s?000\s?[.,]?\s?000\b"), Decimal(1000000)),
]
CURRENCY = re.compile(r"\b(usd|eur|jpy|vnd|vnđ|cny|krw|sgd|thb)\b|\bus\$|\$|€|¥|vnđ|₫", re.I)


def find_date(text):
    """First ISO date inside free text (dd/mm/yyyy, ngày d tháng m năm y, tháng m/yyyy), or None."""
    m = VNDATE_RE.search(text)
    if m:
        d = _mk(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        return d.isoformat() if d else None
    m = DATE_RE.search(text)
    if m and len(m.group(1)) <= 2:
        a, b, c = int(m.group(1)), int(m.group(2)), _year(int(m.group(3)))
        d = _mk(c, b, a)
        return d.isoformat() if d else None
    if m and len(m.group(1)) == 4:
        d = _mk(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return d.isoformat() if d else None
    m = MONTH_RE.search(text)
    if m:
        d = _mk(int(m.group(2)), int(m.group(1)), 1)
        return d.isoformat() if d else None
    return None


def scan(sh, table, price_header=""):
    """Return dict {hieu_luc_tu, multiplier, tien_te, text_fold} each {value, cell} (or None)."""
    rows = [r for r in range(table.ctx_from, table.header_rows[0]) if r not in sh.hidden_rows]
    lines = []
    for r in rows:
        for c, x in row_cells(sh, r).items():
            ref = f"{col_letter(c)}{r}"
            if x.kind == "s":
                lines.append((ref, clean_text(x.v)))
            elif x.kind == "d":
                lines.append((ref, x.v.strftime("%d/%m/%Y")))
    out = {"hieu_luc_tu": None, "multiplier": None, "tien_te": None}
    tf = " ".join(fold(t) for _, t in lines)
    for i, (ref, t) in enumerate(lines):
        f = fold(t)
        if out["hieu_luc_tu"] is None and EFFECTIVE.search(f):
            d = find_date(t)
            if d is None and i + 1 < len(lines):            # label in one cell, date in the next
                d = find_date(lines[i + 1][1])
                ref = lines[i + 1][0] if d else ref
            if d:
                out["hieu_luc_tu"] = {"value": d, "cell": ref}
        if out["multiplier"] is None:
            for rx, mult in MULT_PATTERNS:
                if rx.search(f):
                    out["multiplier"] = {"value": mult, "cell": ref}
                    break
        if out["tien_te"] is None:
            m = CURRENCY.search(t)
            if m and re.search(r"tien|currency|don vi|dvt|bang gia|usd|eur", f):
                from .normalize import norm_currency
                out["tien_te"] = {"value": norm_currency(m.group(0)), "cell": ref}
    if out["multiplier"] is None and price_header:
        f = fold(price_header)
        for rx, mult in MULT_PATTERNS[2:]:
            if rx.search(f):
                out["multiplier"] = {"value": mult, "cell": None}
                break
    if out["hieu_luc_tu"] is None:       # no keyword: a lone date line in the header block is the list date
        for ref, t in lines:
            if not re.search(r"(han|het|sinh|mst|dien thoai|tel|fax)", fold(t)):
                d = find_date(t)
                if d:
                    out["hieu_luc_tu"] = {"value": d, "cell": ref}
                    break
    if out["tien_te"] is None and price_header:
        m = CURRENCY.search(price_header)
        if m:
            from .normalize import norm_currency
            out["tien_te"] = {"value": norm_currency(m.group(0)), "cell": None}
    out["text_fold"] = tf
    return out


def workbook_date(sheets, max_rows=40):
    """Exactly one effective-date statement on sheets that hold no table -> {value, cell, sheet}; else None."""
    found = {}
    for sh in sheets:
        for r in range(1, min(sh.nrows, max_rows) + 1):
            for c, x in row_cells(sh, r).items():
                if x.kind != "s":
                    continue
                t = clean_text(x.v)
                if EFFECTIVE.search(fold(t)):
                    d = find_date(t)
                    if d:
                        found[(sh.name, f"{col_letter(c)}{r}")] = d
    if len({d for d in found.values()}) != 1:
        return None
    (sheet, ref), d = next(iter(found.items()))
    return {"value": d, "cell": f"{sheet}!{ref}"}
