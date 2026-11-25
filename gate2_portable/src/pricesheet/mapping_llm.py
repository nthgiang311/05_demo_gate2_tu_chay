"""Layer 5 (model): gpt-4o-mini proposes header rows and column->field mapping. Never returns cell values."""
import hashlib
import json
import os
from typing import List, Literal, Optional

from pydantic import BaseModel

from .grid import col_index, col_letter
from .mapping_rules import extras_key, header_scores
from .normalize import clean_text
from .tables import row_cells

MODEL = "gpt-4o-mini"
PRICE_IN_PER_M, PRICE_OUT_PER_M = 0.15, 0.60   # USD per 1M tokens: verify current price
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".cache", "pricesheet")
FIELDS = ("ma_hang", "ten_hang", "don_vi", "don_gia", "tien_te", "hieu_luc_tu")


class FieldMap(BaseModel):
    field: Literal["ma_hang", "ten_hang", "don_vi", "don_gia", "tien_te", "hieu_luc_tu"]
    column: str
    evidence_cells: List[str]
    reason_code: str


class Proposal(BaseModel):
    header_rows: List[int]
    field_mappings: List[FieldMap]
    effective_date_cell: Optional[str]
    reason_codes: List[str]


SYSTEM = (
    "You map columns of a Vietnamese supplier price list. You only output structure: header row numbers and which "
    "column letter holds each field. Never output cell values. Fields: ma_hang (item code), ten_hang (item name), "
    "don_vi (unit of measure, e.g. Hop/Vi/Cai), don_gia (unit price: if several price columns, choose the base unit "
    "price before VAT, not promo, not cost price, not total, not quantity tiers beyond the first), tien_te (currency), "
    "hieu_luc_tu (effective-from date column). Omit a field when no column holds it. Use each column at most once. "
    "header_rows: row numbers of the header (several rows if the header spans multiple rows). effective_date_cell: "
    "cell reference such as B3 that holds a date the price list applies from, outside the table, else null. "
    "evidence_cells: header cells that justify the choice. reason_code: short code like HEADER_EXACT, HEADER_SYNONYM, "
    "PROFILE, TITLE_HINT."
)


def build_prompt(sh, table, prof, ctx_lines):
    """Compact prompt: context lines, header + 8 sample rows (cells cut to 40 chars), column profile."""
    first = min(table.header_rows[0], table.first_data)
    start = max(1, first - 6)
    end = min(sh.nrows, table.header_rows[-1] + 8)
    cols = sorted({c for r in range(start, end + 1) for c in row_cells(sh, r)} | set(table.cols))[:30]
    lines = [f"Sheet: {sh.name}", f"Columns: {' '.join(col_letter(c) for c in cols)}", "Rows (row: COL=value):"]
    for r in range(start, end + 1):
        cells = row_cells(sh, r)
        if not cells:
            continue
        parts = [f"{col_letter(c)}={clean_text(x.v)[:40]!r}" if x.kind != "d" else f"{col_letter(c)}=<date>"
                 for c, x in cells.items() if c in cols]
        lines.append(f"{r}: " + " | ".join(parts))
    lines.append("Column profile (data rows): num=share parsing as number, len=avg text length, uniq=distinct share")
    for c in cols:
        p = prof.get(c)
        if p and p.get("n"):
            lines.append(f"{col_letter(c)}: num={p['num_ratio']:.2f} len={p['avg_len']:.0f} uniq={p['distinct']:.2f} "
                         f"date={p['date_ratio']:.2f} empty={p['empty']:.2f}")
    return "\n".join(lines)


def _key():
    from src.config import get_settings
    return get_settings().openai_api_key


def call(prompt, usage, use_cache=True):
    """Return Proposal or None. usage dict is updated in place (calls, tokens, cache_hits, errors, usd)."""
    h = hashlib.sha256((MODEL + "\n" + SYSTEM + "\n" + prompt).encode("utf-8")).hexdigest()
    path = os.path.join(CACHE_DIR, h + ".json")
    if use_cache and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                usage["cache_hits"] += 1
                return Proposal.model_validate_json(f.read())
        except Exception:
            usage["cache_hits"] -= 1
    try:
        from openai import OpenAI
        key = _key()
        if not key:
            raise RuntimeError("no key")
        client = OpenAI(api_key=key, timeout=60, max_retries=1)
        usage["calls"] += 1
        res = client.chat.completions.parse(
            model=MODEL, temperature=0, response_format=Proposal,
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}])
        u = res.usage
        usage["tokens_in"] += u.prompt_tokens
        usage["tokens_out"] += u.completion_tokens
        usage["usd"] += u.prompt_tokens * PRICE_IN_PER_M / 1e6 + u.completion_tokens * PRICE_OUT_PER_M / 1e6
        prop = res.choices[0].message.parsed
        if prop is None:
            raise ValueError("refusal/empty")
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(prop.model_dump_json())
        return prop
    except Exception:
        usage["errors"] += 1      # never log exception text: it could carry request details
        return None


def validate(prop, sh, table, prof):
    """Keep only proposals whose coordinates lie inside the candidate table. Returns (header_rows, {field: col})."""
    lo = max(1, min(table.header_rows[0], table.first_data) - 6)
    hi = min(sh.nrows, table.header_rows[-1] + 8)
    hdr = sorted({r for r in prop.header_rows if lo <= r <= hi})
    valid_cols = set(table.cols)
    maps, used = {}, set()
    for fm in prop.field_mappings:
        try:
            c = col_index(fm.column.strip().upper())
        except Exception:
            continue
        if c not in valid_cols or c in used or fm.field in maps:
            continue
        if extras_key(table.names.get(c, "")) is not None:   # known extras column (Quy cách, Giá có VAT, Bậc 2...)
            continue
        maps[fm.field] = c
        used.add(c)
    return hdr, maps
