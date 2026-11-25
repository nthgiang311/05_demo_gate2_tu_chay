"""Chạy tool trên <root>/files ở các chế độ, lưu <root>/out/<mode>/<file>.json.
  rules        : chỉ luật (use_llm=False)
  rule_first   : luật trước, gọi AI khi luật không chắc (mặc định của tool), không dùng cache
  llm_all      : gọi AI cho mọi bảng, không dùng cache
  rules_v2     : chỉ luật, có vá luật thử nghiệm (rules_v2.py)
  rule_first_v2: luật trước + AI, có vá luật thử nghiệm
Chạy: ..\\gate2_portable\\.venv\\Scripts\\python -X utf8 run_eval.py [--root hard] [mode...]
Chế độ _v2 phải chạy riêng một lệnh (bản vá áp dụng cho cả tiến trình).
"""
import json
import os
import sys
import warnings
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(os.path.dirname(HERE), "gate2_portable")
sys.path.insert(0, TOOL)
sys.path.insert(0, HERE)
import envsetup  # noqa: E402

envsetup.setup()
warnings.filterwarnings("ignore")
from src.pricesheet.graph import normalize  # noqa: E402

MODES = {"rules": ("rule_first", False), "rule_first": ("rule_first", True), "llm_all": ("llm_all", True),
         "rules_v2": ("rule_first", False), "rule_first_v2": ("rule_first", True),
         "rules_moi": ("rule_first", False),
         "code1": ("rule_first", False, "v1"), "code2": ("rule_first", False, "v2")}


def main():
    args = sys.argv[1:]
    root = HERE
    if args[:1] == ["--root"]:
        root = os.path.join(HERE, args[1])
        args = args[2:]
    modes = args or ["rules", "rule_first", "llm_all"]
    v2 = {m.endswith("_v2") for m in modes}
    if len(v2) > 1:
        sys.exit("chạy chế độ _v2 trong lệnh riêng")
    if v2 == {True}:
        import rules_v2
        rules_v2.apply()
    names = sorted(n for n in os.listdir(os.path.join(root, "files")) if not n.startswith("~$"))

    def one(mode_key, name):
        mode, use_llm, *rv = MODES[mode_key]
        kw = {"rules": rv[0]} if rv else {}
        res = normalize(os.path.join(root, "files", name), mode, use_llm=use_llm, use_cache=False, **kw)
        with open(os.path.join(root, "out", mode_key, name + ".json"), "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, default=str)
        return res["llm"]["calls"], res["llm"]["errors"], res["llm"]["usd"]

    for m in modes:
        os.makedirs(os.path.join(root, "out", m), exist_ok=True)
        with ThreadPoolExecutor(1 if not MODES[m][1] else 4) as ex:
            rs = list(ex.map(lambda n: one(m, n), names))
        print(f"[{m}] files={len(rs)} llm_calls={sum(r[0] for r in rs)} llm_errors={sum(r[1] for r in rs)} "
              f"usd={sum(r[2] for r in rs):.4f}", flush=True)


if __name__ == "__main__":
    main()
