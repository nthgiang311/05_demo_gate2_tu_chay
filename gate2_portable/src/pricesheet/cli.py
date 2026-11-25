"""CLI: python -X utf8 -m pricesheet.cli <file-or-dir>... --out <dir> --mode rule_first|llm_all [--no-llm] [--no-cache]"""
import argparse
import csv
import json
import os
import sys

from .graph import normalize

EXTS = (".xlsx", ".xlsm", ".xls")
COLS = ["nguon", "ma_hang", "ten_hang", "don_vi", "don_gia", "tien_te", "hieu_luc_tu", "extras", "trang_thai", "ma_van_de"]


def collect(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for n in sorted(os.listdir(p)):
                if n.lower().endswith(EXTS) and ".misa_them_moi" not in n and not n.startswith("~$"):
                    out.append(os.path.join(p, n))
        else:
            out.append(p)
    return out


def write_csv(f, res):
    w = csv.writer(f)
    w.writerow(COLS)
    for r in res["rows"]:
        w.writerow([r["nguon"], r["ma_hang"], r["ten_hang"], r["don_vi"], r["don_gia"], r["tien_te"], r["hieu_luc_tu"],
                    json.dumps(r["extras"], ensure_ascii=False, sort_keys=True), r["trang_thai"], ";".join(r["ma_van_de"])])


def write_outputs(res, outdir, stem):
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, stem + ".out.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, default=str)
    with open(os.path.join(outdir, stem + ".csv"), "w", encoding="utf-8-sig", newline="") as f:
        write_csv(f, res)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pricesheet")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", choices=["rule_first", "llm_all"], default="rule_first")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    a = ap.parse_args(argv)
    tot = {"calls": 0, "tokens_in": 0, "tokens_out": 0, "usd": 0.0, "errors": 0}
    statuses = set()
    for p in collect(a.paths):
        res = normalize(p, a.mode, use_llm=not a.no_llm, use_cache=not a.no_cache)
        statuses.add(res["status"])
        write_outputs(res, a.out, os.path.splitext(os.path.basename(p))[0])
        for k in tot:
            tot[k] += res["llm"][k]
        print(f"{res['file']}: {res['status']} {res['error_code'] or ''} rows={len(res['rows'])} "
              f"llm_calls={res['llm']['calls']} {res['seconds']}s")
    print(f"LLM total: calls={tot['calls']} in={tot['tokens_in']} out={tot['tokens_out']} usd={tot['usd']:.4f} errors={tot['errors']}")
    return 2 if "error" in statuses else 1 if "needs_review" in statuses else 0   # spec 2.2


if __name__ == "__main__":
    sys.exit(main())
