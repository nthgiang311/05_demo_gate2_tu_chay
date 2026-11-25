"""Chấm out/<mode>/ với gold/, ghi results.json (số liệu) và in tóm tắt.
Chạy: ..\\gate2_portable\\.venv\\Scripts\\python -X utf8 score.py
"""
import json
import os
import re
import unicodedata
from collections import defaultdict
from decimal import Decimal, InvalidOperation

HERE = os.path.dirname(os.path.abspath(__file__))
MODES = ["rules", "rule_first", "llm_all", "rules_v2", "rule_first_v2", "rules_moi"]
FIELDS = ["ma_hang", "ten_hang", "don_vi", "don_gia", "tien_te"]


def norm(s):
    s = unicodedata.normalize("NFC", "" if s is None else str(s)).replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip().casefold()


def dec(x):
    if x is None or x == "":
        return None
    try:
        return Decimal(str(x)).normalize()
    except InvalidOperation:
        return None


def same(f, g, o):
    if f == "don_gia":
        return dec(g) == dec(o)
    return norm(g) == norm(o)


def score_file(gold, res):
    s = {"file": gold["file"], "category": gold["category"], "status": res["status"], "error_code": res["error_code"],
         "llm_calls": res["llm"]["calls"], "llm_errors": res["llm"]["errors"], "usd": res["llm"]["usd"],
         "tokens": res["llm"]["tokens_in"] + res["llm"]["tokens_out"], "seconds": res.get("seconds", 0)}
    if gold["expect_error"]:
        s["error_ok"] = res["error_code"] == gold["expect_error"]
        s.update(gold_rows=0, found=0, out_rows=0, spurious=0, exact=0, field_ok={f: 0 for f in FIELDS},
                 ok_correct=0, ok_wrong=0, traps=0, traps_caught=0, normal=0, map_total=0, map_ok=0, hdr_total=0,
                 hdr_ok=0, map_detail=[], llm_fields=[], date_ok=None)
        return s
    s["error_ok"] = None
    out = defaultdict(list)          # một dòng Excel có thể chứa 2 bảng cạnh nhau: ghép mỗi dòng ra với 1 dòng đáp án
    for r in res.get("rows", []):
        out[r["nguon"]].append(r)
    g_rows = gold["rows"]
    s["gold_rows"], s["out_rows"] = len(g_rows), len(res.get("rows", []))
    found = exact = ok_correct = ok_wrong = traps = caught = normal = 0
    fok = {f: 0 for f in FIELDS}
    wrong_examples = []
    used = set()
    for g in g_rows:
        cand = [o for o in out.get(g["nguon"], []) if id(o) not in used]
        o = max(cand, key=lambda o: sum(same(f, g[f], o.get(f)) for f in FIELDS), default=None)
        if o is not None:
            used.add(id(o))
        if g["trap"]:
            traps += 1
        else:
            normal += 1
        if not o:
            continue
        found += 1
        oks = {f: same(f, g[f], o.get(f)) for f in FIELDS}
        for f in FIELDS:
            fok[f] += oks[f]
        allok = all(oks.values())
        exact += allok
        if g["trap"]:
            caught += o["trang_thai"] != "ok"
        if o["trang_thai"] == "ok":
            if g["expect_ok"] and allok:
                ok_correct += 1
            else:
                ok_wrong += 1     # lọt vào file MISA nhưng sai hoặc lẽ ra phải chặn
                if len(wrong_examples) < 3:
                    bad = [f for f in FIELDS if not oks[f]]
                    wrong_examples.append({"nguon": g["nguon"], "sai": bad or ["lẽ ra phải chặn: " + str(g["trap"])],
                                           "gold": {f: g[f] for f in bad}, "tool": {f: o.get(f) for f in bad}})
    gold_set = {g["nguon"] for g in g_rows}
    s.update(found=found, spurious=sum(len(v) for k, v in out.items() if k not in gold_set), exact=exact, field_ok=fok,
             ok_correct=ok_correct, ok_wrong=ok_wrong, traps=traps, traps_caught=caught, normal=normal,
             wrong_examples=wrong_examples)
    # bảng: tiêu đề + ánh xạ cột
    map_total = map_ok = hdr_total = hdr_ok = 0
    detail, llm_fields = [], []
    for gt in gold["tables"]:
        cands = [t for t in res.get("tables", []) if t["sheet"] == gt["sheet"]]

        def overlap(t):
            a, b = t.get("data_rows") or [0, -1]
            return max(0, min(b, gt["data_last"]) - max(a, gt["data_first"]) + 1)
        t = max(cands, key=overlap, default=None)
        if t is not None and overlap(t) == 0:
            t = None
        hdr_total += 1
        if t and gt["header_rows"] and t["header_rows"] and t["header_rows"][-1] == gt["header_rows"][-1]:
            hdr_ok += 1
        for f, col in gt["mapping"].items():
            map_total += 1
            m = (t or {}).get("mapping", {}).get(f)
            ok = bool(m) and m["col"] == col
            map_ok += ok
            detail.append({"sheet": gt["sheet"], "field": f, "gold": col, "tool": m["col"] if m else None,
                           "source": m["source"] if m else None, "ok": ok})
        for f, m in (t or {}).get("mapping", {}).items():
            if m["source"] in ("llm", "both"):
                llm_fields.append({"field": f, "col": m["col"], "source": m["source"],
                                   "ok": gt["mapping"].get(f) == m["col"] if f in gt["mapping"] else None})
    s.update(map_total=map_total, map_ok=map_ok, hdr_total=hdr_total, hdr_ok=hdr_ok, map_detail=detail,
             llm_fields=llm_fields)
    if gold["hieu_luc_tu"]:
        vals = {r.get("hieu_luc_tu") for r in res.get("rows", [])}
        s["date_ok"] = vals == {gold["hieu_luc_tu"]}
    else:
        s["date_ok"] = None
    return s


def agg(rows):
    a = defaultdict(float)
    for s in rows:
        for k in ("gold_rows", "found", "out_rows", "spurious", "exact", "ok_correct", "ok_wrong", "traps",
                  "traps_caught", "normal", "map_total", "map_ok", "hdr_total", "hdr_ok", "llm_calls", "llm_errors",
                  "usd", "tokens", "seconds"):
            a[k] += s[k]
        for f in FIELDS:
            a["f_" + f] += s["field_ok"][f]
        if s["error_ok"] is not None:
            a["err_total"] += 1
            a["err_ok"] += s["error_ok"]
        if s["date_ok"] is not None:
            a["date_total"] += 1
            a["date_ok"] += s["date_ok"]
        a["files"] += 1
        a["files_llm"] += s["llm_calls"] > 0
        a["files_error"] += s["status"] == "error"
        a["files_review"] += s["status"] == "needs_review"
        a["files_perfect"] += (s["error_ok"] if s["error_ok"] is not None else
                               s["found"] == s["gold_rows"] and s["exact"] == s["gold_rows"] and s["spurious"] == 0)
    return dict(a)


def main():
    import sys
    root = os.path.join(HERE, sys.argv[2]) if sys.argv[1:2] == ["--root"] else HERE
    gold = {}
    for n in sorted(os.listdir(os.path.join(root, "gold"))):
        g = json.load(open(os.path.join(root, "gold", n), encoding="utf-8"))
        gold[g["file"]] = g
    result = {"files": {}, "total": {}, "by_cat": {}, "cats": {}}
    for g in gold.values():
        result["cats"][g["category"]] = g["category_desc"]
    for m in MODES:
        d = os.path.join(root, "out", m)
        if not os.path.isdir(d) or len(os.listdir(d)) < len(gold):
            continue
        per = []
        for name, g in gold.items():
            res = json.load(open(os.path.join(d, name + ".json"), encoding="utf-8"))
            per.append(score_file(g, res))
        result["files"][m] = per
        result["total"][m] = agg(per)
        result["by_cat"][m] = {c: agg([s for s in per if s["category"] == c]) for c in sorted(result["cats"])}
    with open(os.path.join(root, "results.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1, default=str)
    pct = lambda a, b: f"{100 * a / b:5.1f}%" if b else "  -  "
    print(f"{'mode':13} recall  exact  ok_dung  ok_SAI  bay_chan  anh_xa  tieu_de  ma_loi  file_hoan_hao  calls  usd")
    for m, t in result["total"].items():
        print(f"{m:13} {pct(t['found'], t['gold_rows'])} {pct(t['exact'], t['gold_rows'])} {int(t['ok_correct']):6} "
              f"{int(t['ok_wrong']):6}   {pct(t['traps_caught'], t['traps'])} {pct(t['map_ok'], t['map_total'])} "
              f"{pct(t['hdr_ok'], t['hdr_total'])} {int(t.get("err_ok",0))}/{int(t.get("err_total",0))}   "
              f"{int(t['files_perfect']):3}/{int(t['files'])}   {int(t['llm_calls']):4} {t['usd']:.4f}")
    for m in result["by_cat"]:
        print("\n==", m)
        for c, t in result["by_cat"][m].items():
            print(f"C{c:02d} {result['cats'][c][:45]:45} recall {pct(t['found'], t['gold_rows'])} exact {pct(t['exact'], t['gold_rows'])} "
                  f"map {pct(t['map_ok'], t['map_total'])} okSAI {int(t['ok_wrong']):3} spur {int(t['spurious']):3} calls {int(t['llm_calls'])}")


if __name__ == "__main__":
    main()
