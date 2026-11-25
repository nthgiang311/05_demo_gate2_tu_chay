"""Layer 2: find tables (header rows + data region) on a sheet."""
import re
from dataclasses import dataclass, field

from .grid import col_letter
from .mapping_rules import header_scores
from .normalize import clean_text, fold, looks_price


@dataclass
class Table:
    sheet: object
    header_rows: list
    first_data: int
    last_data: int
    names: dict = field(default_factory=dict)     # col -> header text (multi-tier joined with ' / ')
    repeat_header_rows: list = field(default_factory=list)
    id: str = "t0"
    title_rows: list = field(default_factory=list)  # rows above the header that belong to this table's context
    ctx_from: int = 1                                # first row of the context window above the header

    @property
    def cols(self):
        return sorted(self.names)


def _is_numlike(c):
    if c.kind in ("n", "d"):
        return True
    return looks_price(c.v, c.kind) or (c.kind == "s" and bool(re.fullmatch(r"\d+\s*%", clean_text(c.v))))


def row_cells(sh, r):
    return {c: sh.cells[(r, c)] for c in range(1, sh.ncols + 1) if (r, c) in sh.cells and (sh.cells[(r, c)].v is not None)}


def header_row_score(sh, r):
    """Return (fields_matched_set, score, per-col best field) for a candidate header row."""
    cells = row_cells(sh, r)
    texts = {c: x for c, x in cells.items() if x.kind == "s" and not _is_numlike(x)}
    if len(texts) < 2 or len(texts) < 0.6 * len(cells):
        return set(), 0.0, {}
    best, per_col = {}, {}
    for c, x in texts.items():
        for fld, sc in header_scores(x.v).items():
            if sc >= 0.7:
                per_col.setdefault(c, {})[fld] = sc
                if sc > best.get(fld, 0):
                    best[fld] = sc
    return set(best), sum(best.values()), per_col


def _is_candidate(sh, r):
    fields, score, _ = header_row_score(sh, r)
    return len(fields) >= 2 and bool(fields & {"ten_hang", "don_gia", "ma_hang"}), score


def _row_sig(sh, r):
    return {c: fold(x.v) for c, x in row_cells(sh, r).items() if x.kind == "s"}


def _same_header(sig, ref_sigs):
    if not sig:
        return False
    for ref in ref_sigs:
        hit = sum(1 for c, t in sig.items() if ref.get(c) == t)
        if hit >= max(2, 0.6 * len(sig)) or (len(sig) == 1 and hit == 1 and len(ref) <= 2):
            return True
    return False


def _tier_below(sh, r, per_col):
    """Row r+1 is a sub-header if it only fills columns other than id/name columns and holds no numbers."""
    nxt = r + 1
    if nxt > sh.nrows or nxt in sh.hidden_rows:
        return False
    cells = row_cells(sh, nxt)
    if len(cells) < 2 or any(_is_numlike(x) or x.kind != "s" for x in cells.values()):
        return False            # one text cell (or one merged cell across the table) = group line, not a tier
    width = max(sh.ncols, 1)
    if any(m[0] == nxt and (m[3] - m[1] + 1) >= 0.6 * width for m in sh.merges):
        return False
    idname = {c for c, fs in per_col.items() if set(fs) & {"ma_hang", "ten_hang"}}
    if any(c in idname for c in cells):
        return False
    return len(cells) <= max(2, 0.6 * len(row_cells(sh, r)))


def _tier_above(sh, r):
    up = r - 1
    if up < 1 or up in sh.hidden_rows:
        return False
    cells = row_cells(sh, up)
    if not any(m[0] <= up <= m[2] and m[3] > m[1] for m in sh.merges):
        return False
    if any(_is_numlike(x) or x.kind != "s" for x in cells.values()):
        return False
    return not _is_candidate(sh, up)[0] and len(cells) >= 2


def tier_names(sh, rows):
    """Join multi-row header text per column; empty top cells inherit across a merge/contiguous group."""
    cols = sorted({c for r in rows for c in row_cells(sh, r)})
    names = {}
    top = rows[0]
    merged = {}
    for r1, c1, r2, c2 in sh.merges:
        if r1 in rows and c2 > c1:
            for c in range(c1, c2 + 1):
                merged[(r1, c)] = (r1, c1)
    for c in cols:
        parts = []
        for r in rows:
            x = sh.cells.get((r, c))
            if x is not None and x.v is not None:
                parts.append(clean_text(x.v))
                continue
            if (r, c) in merged:
                src = sh.cells.get(merged[(r, c)])
                if src is not None and src.v is not None:
                    parts.append(clean_text(src.v))
                    continue
            if r == top and len(rows) > 1 and any(sh.cells.get((r2, c)) is not None and sh.cells[(r2, c)].v is not None for r2 in rows[1:]):
                k = c - 1
                while k >= 1 and sh.cells.get((r, k)) is None and any(sh.cells.get((r2, k)) is not None for r2 in rows[1:]):
                    k -= 1
                if k >= 1 and sh.cells.get((r, k)) is not None and sh.cells[(r, k)].v is not None and k != c:
                    parts.append(clean_text(sh.cells[(r, k)].v))
        dedup = []
        for p in parts:
            if p and (not dedup or dedup[-1] != p):
                dedup.append(p)
        if dedup:
            names[c] = " / ".join(dedup)
    return names


def make_table(sh, header_rows, first_data=None, last_data=None, tid="t0", ctx_from=1):
    header_rows = sorted(header_rows)
    names = tier_names(sh, header_rows)
    return Table(sh, header_rows, first_data or header_rows[-1] + 1, last_data or sh.nrows, names, [], tid,
                 ctx_from=ctx_from)


def find_tables(sh):
    """Rule-based table detection on one visible sheet."""
    cands = [r for r in range(1, sh.nrows + 1) if r not in sh.hidden_rows and _is_candidate(sh, r)[0]]
    tables, i = [], 0
    consumed = set()
    for r in cands:
        if r in consumed:
            continue
        if tables:
            t = tables[-1]
            sig = _row_sig(sh, r)
            refs = [_row_sig(sh, h) for h in t.header_rows]
            prev, prev2 = r - 1, r - 2
            title_before = (prev >= 1 and len(row_cells(sh, prev)) == 1 and prev2 >= 1 and not row_cells(sh, prev2))
            if _same_header(sig, refs) and not title_before:
                t.repeat_header_rows.append(r)
                consumed.add(r)
                continue
        _, _, per_col = header_row_score(sh, r)
        rows = [r]
        if _tier_below(sh, r, per_col):
            rows.append(r + 1)
            consumed.add(r + 1)
        elif _tier_above(sh, r):
            rows.insert(0, r - 1)
        ctx_from = 1
        if tables:
            ctx_from = max(tables[-1].header_rows[-1] + 1, r - 4)
            tables[-1].last_data = (rows[0] - 1) if not title_before else (prev - 1)
            if title_before:
                ctx_from = prev
        t = make_table(sh, rows, tid=f"t{len(tables)}", ctx_from=ctx_from)
        tables.append(t)
    # collect repeated header rows that sit inside data (incl. their tier rows)
    for t in tables:
        refs = [_row_sig(sh, h) for h in t.header_rows]
        for r in range(t.first_data, t.last_data + 1):
            if r in t.repeat_header_rows or r in sh.hidden_rows:
                continue
            if _same_header(_row_sig(sh, r), refs):
                t.repeat_header_rows.append(r)
        t.repeat_header_rows.sort()
    return tables


def sheet_texts(sh, rows):
    out = []
    for r in rows:
        for c, x in row_cells(sh, r).items():
            if x.kind == "s":
                out.append((f"{col_letter(c)}{r}", clean_text(x.v)))
    return out
