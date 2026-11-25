"""Layer 4: per-column profile over the data region."""
import statistics
from decimal import Decimal
from collections import Counter

from .normalize import CUR_MAP, UNIT_CANON, clean_text, fold, looks_price, parse_date, parse_price
from .tables import row_cells


def profile_columns(sh, table, limit=1500):
    """{col: stats}. Looks at up to `limit` non-hidden data rows."""
    rows = [r for r in range(table.first_data, table.last_data + 1)
            if r not in sh.hidden_rows and r not in table.repeat_header_rows][:limit]
    out = {}
    for c in table.cols:
        vals = [sh.cells[(r, c)] for r in rows if (r, c) in sh.cells and (sh.cells[(r, c)].v is not None or sh.cells[(r, c)].f)]
        n = len(vals)
        p = {"n": n, "rows": len(rows), "empty": 1 - n / len(rows) if rows else 1.0, "samples": []}
        if n:
            txt = [clean_text(x.v) if x.kind == "s" else str(x.v) for x in vals]
            numlike = [x for x in vals if x.v is None or looks_price(x.v, x.kind)]
            vals_num = [d for d in (parse_price(x.v, x.kind)[0] for x in numlike if x.v is not None) if d is not None]
            p["num_ratio"] = len(numlike) / n
            p["median"] = float(statistics.median(vals_num)) if vals_num else 0.0
            p["avg_len"] = sum(len(t) for t in txt) / n
            p["text_ratio"] = sum(1 for x in vals if x.kind == "s") / n
            cnt = Counter(txt)
            p["distinct"] = len(cnt) / n
            p["top_freq"] = cnt.most_common(1)[0][1] / n
            p["cur_ratio"] = sum(1 for t in txt if t.lower() in CUR_MAP or (len(t) == 3 and t.isalpha() and t.isupper())) / n
            p["unit_ratio"] = sum(1 for t in txt if fold(t) in UNIT_CANON) / n
            p["date_ratio"] = sum(1 for x in vals if x.kind == "d" or (x.kind == "s" and parse_date(x.v, "s", "dmy")[0])) / n
            p["code_ratio"] = sum(1 for t in txt if " " not in t and any(ch.isdigit() for ch in t) and len(t) <= 30) / n
            p["samples"] = txt[:8]
        out[c] = p
    return out
