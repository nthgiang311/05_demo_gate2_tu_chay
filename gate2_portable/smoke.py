"""Hits each endpoint in-process (TestClient). use_llm=False everywhere except one L04 run with the model."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server
from fastapi.testclient import TestClient

c = TestClient(server.app)
ok = True


def check(name, cond, extra=""):
    global ok
    ok &= bool(cond)
    print(("OK   " if cond else "FAIL ") + name, extra)


smp = c.get("/api/samples").json()
check("samples", len(smp) == 17, len(smp))
ids = {s["name"][:3]: s["id"] for s in smp}
check("so_do", "dev" in c.get("/api/so_do").json())
for s in smp:
    g = c.get("/api/grid", params={"file": s["id"]}).json()
    r = c.post("/api/run", json={"file": s["id"], "use_llm": False}).json()
    check(f"run {s['name'][:3]}", r["llm"]["calls"] == 0, f"{r['status']} {r['error_code']} sheets={len(g['sheets'])} rows={len(r['rows'])}")
b06 = c.post("/api/run", json={"file": ids["B06"], "use_llm": False}).json()
check("B06 WRONG_FORMAT_PDF", b06["error_code"] == "WRONG_FORMAT_PDF" and not b06["rows"])
check("grid B06 error", c.get("/api/grid", params={"file": ids["B06"]}).json()["error_code"] == "WRONG_FORMAT_PDF")
up = c.post("/api/upload", files={"file": ("x.xlsx", open(os.path.join(server.SAMPLES, "F03_Bao_gia_mau_hai_cot_gia_vat.xlsx"), "rb"))}).json()
check("upload+run", c.post("/api/run", json={"file": up["id"], "use_llm": False}).json()["status"] == "ok")
check("upload 11MB rejected", c.post("/api/upload", files={"file": ("big.xlsx", b"0" * (10 * 1024 * 1024 + 1))}).status_code == 413)

# F03: csv, lock, override with 0 calls, approve, misa
f = ids["F03"]
r = c.post("/api/run", json={"file": f, "use_llm": False}).json()
check("csv", c.get("/api/csv", params={"file": f}).text.count("\n") >= len(r["rows"]))
check("misa locked 409", c.get("/api/misa", params={"file": f}).status_code == 409)
tb = r["tables"][0]
cur = tb["mapping"]["don_gia"]["col"]
new = "E" if cur != "E" else "D"
o = c.post("/api/override", json={"file": f, "tables": {tb["id"]: {"mapping": {"don_gia": new}, "confirmed": ["don_gia"]}}}).json()
check("override 0 model calls", o["llm"]["calls"] == 0 and o["tables"][0]["mapping"]["don_gia"]["col"] == new,
      f"{cur}->{new} calls={o['llm']['calls']} source={o['tables'][0]['mapping']['don_gia']['source']} price0={o['rows'][0]['don_gia']}")
c.post("/api/run", json={"file": f, "use_llm": False})
check("approve", c.post("/api/approve", json={"file": f}).json().get("approved"))
m = c.get("/api/misa", params={"file": f}).json()
check("misa preview", m["n_rows"] == 120 and m["rows"][5][2] != "", f"n_rows={m['n_rows']} files={m['files']} report={len(m['report'])}")
check("misa xlsx dl", c.get("/api/misa/download", params={"file": f}).content[:2] == b"PK")
check("bao_cao dl", c.get("/api/misa/download", params={"file": f, "kind": "bao_cao"}).content[:3] == b"\xef\xbb\xbf")

l8 = c.post("/api/run", json={"file": ids["L08"], "use_llm": False}).json()
rq = next(x for x in l8["review_queue"] if x["kind"] == "row")
o = c.post("/api/override", json={"file": ids["L08"], "rows": {rq["nguon"]: {"trang_thai": "bo"}}}).json()
check("L08 row drop override 0 calls", o["llm"]["calls"] == 0 and next(x for x in o["rows"] if x["nguon"] == rq["nguon"])["trang_thai"] == "bo")

# L04 with the model, rule_first, no cache
l = c.post("/api/run", json={"file": ids["L04"], "mode": "rule_first", "use_cache": False, "use_llm": True}).json()
print("L04 model run:", l["status"], "llm=", l["llm"], "queue=", len(l["review_queue"]), "seconds=", l["seconds"])
check("L04 cost < 0.01", l["llm"]["usd"] < 0.01)
q = [x for x in l["review_queue"] if x["kind"] in ("mapping", "price_choice")]
if q:
    t = next(t for t in l["tables"] if t["id"] == q[0]["table"])
    fld = q[0]["field"] or "don_gia"
    o = c.post("/api/override", json={"file": ids["L04"], "tables": {t["id"]: {"mapping": {fld: t["mapping"][fld]["col"] if fld in t["mapping"] else "D"}, "confirmed": [fld]}}}).json()
    check("L04 override 0 calls", o.get("llm", {}).get("calls") == 0, str(o)[:200] if "llm" not in o else "")
print("SMOKE", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
