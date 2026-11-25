"""Demo server for PriceSheet Normalizer, Gate 2. Single user, in-memory state. Run with the P-177-core venv."""
import datetime as dt
import io
import json
import os
import re
import secrets
import sys
import tempfile
import threading
import warnings
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import envsetup  # noqa: E402

envsetup.setup()
warnings.filterwarnings("ignore")

import openpyxl  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI, File, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, Response  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import misa_export  # noqa: E402
from src.pricesheet import review  # noqa: E402
from src.pricesheet.cli import write_csv  # noqa: E402
from src.pricesheet.graph import normalize  # noqa: E402
from src.pricesheet.grid import read_grid  # noqa: E402
from src.pricesheet.override import OverrideError  # noqa: E402
from src.pricesheet.sniff import sniff  # noqa: E402

SAMPLES = os.path.join(HERE, "samples")
UPLOADS = tempfile.mkdtemp(prefix="gate2_up_")
MAX_BYTES, MAX_GRID_ROWS, MAX_GRID_COLS = 10 * 1024 * 1024, 1000, 60
LABELS = {
    "P01_Bao_gia_mau_tieu_de_dong_7_ghi_chu_cuoi.xlsx": "[Mẫu] Tiêu đề ở dòng 7, ghi chú ở cuối",
    "P02_Bao_gia_mau_tieu_de_lap_moi_trang.xlsx": "[Mẫu] Tiêu đề lặp lại ở mỗi trang",
    "P03_Bao_gia_mau_tieu_de_2_tang_2_cot_gia.xlsx": "[Mẫu] Tiêu đề 2 tầng, ô gộp, 2 cột giá",
    "P04_Bao_gia_mau_gia_nghin_dong.xlsx": "[Mẫu] Đơn vị trong tiêu đề (nghìn đồng)",
    "P05_Bao_gia_mau_nhieu_sheet_sheet_an.xlsx": "[Mẫu] Nhiều sheet, có sheet ẩn",
    "P06_Bao_gia_mau_dong_nhom_cong_nhom.xlsx": "[Mẫu] Dòng nhóm và dòng cộng nhóm bằng công thức",
    "P07_Bao_gia_mau_gia_chu_kieu_viet.xlsx": "[Mẫu] Giá dạng chữ kiểu Việt, lẫn kiểu cột trống",
    "P11_Bao_gia_mau_xls_97_2003.xls": "[Mẫu] File .xls cũ (97-2003)",
    "P12_Bao_gia_mau_565_dong_co_dong_trung.xlsx": "[Mẫu] 565 dòng, có dòng trùng y hệt",
    "P13_Bao_gia_mau_gop_nhieu_bay.xlsx": "[Mẫu] Gộp nhiều bẫy: nhóm, tiêu đề lặp, giá nghìn, dòng ẩn",
    "P14_Bao_gia_mau_tong_nhom_lech.xlsx": "[Mẫu] Tổng nhóm gõ sẵn, một nhóm lệch 1.000 đ",
    "P20_Bao_gia_cong_khai_TBYT_bom_tiem.xlsx": "[Công khai] Kê khai giá thiết bị y tế (bơm tiêm), file gốc không sửa",
    "P21_Bao_gia_cong_khai_thuoc_benh_vien.xlsx": "[Công khai] Giá thuốc của một bệnh viện, dán từ PDF",
    "L04_Bao_gia_mau_ban_le_cong_thuc.xlsx": "[Mẫu] Luật chưa chắc, gọi mô hình ở chế độ Luật trước",
    "L08_Bao_gia_mau_dong_nhom_lien_he_trung.xlsx": "[Mẫu] Dòng nhóm, dòng tổng, giá Liên hệ, mã trùng",
    "F03_Bao_gia_mau_hai_cot_gia_vat.xlsx": "[Mẫu] Giá trước và sau VAT",
    "B06_Bao_gia_mau_pdf_doi_ten.xlsx": "[Mẫu] PDF đổi đuôi thành .xlsx: phải báo mã lỗi",
}
STATE = {}   # file id -> {"path","name","mode","res","override","approved"}
_lock = threading.RLock()
app = FastAPI()


def err(status, code, detail):
    return JSONResponse({"error_code": code, "detail": detail}, status_code=status)


def _entry(fid):
    if fid in STATE:
        return STATE[fid]
    if fid.startswith("s:"):
        n = os.path.basename(fid[2:])
        p = os.path.join(SAMPLES, n)
        if not os.path.isfile(p):
            return None
        STATE[fid] = {"path": p, "name": n, "mode": "rule_first", "res": None, "override": None, "approved": False}
        return STATE[fid]
    return None


@app.get("/")
def index():
    return FileResponse(os.path.join(HERE, "index.html"))


@app.get("/api/so_do")
def so_do():
    return FileResponse(os.path.join(HERE, "so_do.json"))


@app.get("/api/samples")
def samples():
    return [{"id": "s:" + n, "name": n, "label": LABELS[n]} for n in LABELS if os.path.isfile(os.path.join(SAMPLES, n))]


@app.post("/api/upload")
def upload(file: UploadFile = File(...)):
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        return err(413, "FILE_TOO_LARGE", "File quá 10 MB")
    ext = os.path.splitext(file.filename or "")[1].lower()
    ext = ext if ext in (".xlsx", ".xls", ".xlsm") else ".bin"
    fid = "u:" + secrets.token_hex(8) + ext
    path = os.path.join(UPLOADS, fid[2:])
    os.makedirs(UPLOADS, exist_ok=True)  # temp dir may be cleaned while the server runs
    with open(path, "wb") as f:
        f.write(data)
    STATE[fid] = {"path": path, "name": os.path.basename(file.filename or "upload"), "mode": "rule_first",
                  "res": None, "override": None, "approved": False}
    return {"id": fid, "name": STATE[fid]["name"]}


def _text(v):
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float) and v == int(v) and abs(v) < 1e15:
        return str(int(v))
    if isinstance(v, (dt.datetime, dt.date)):
        return v.strftime("%Y-%m-%d")
    return str(v)


@app.get("/api/grid")
def grid(file: str):
    e = _entry(file)
    if not e:
        return err(404, "NOT_FOUND", "không có file")
    kind, code, detail = sniff(e["path"])
    if not kind:
        return {"error_code": code, "detail": detail, "sheets": []}
    try:
        wb = read_grid(e["path"], kind)
    except Exception as ex:
        return {"error_code": "FILE_CORRUPT", "detail": str(ex)[:200], "sheets": []}
    out = []
    for s in wb.sheets:
        cells = [[r, c, _text(x.v)] for (r, c), x in sorted(s.cells.items())
                 if x.v is not None and r <= MAX_GRID_ROWS and c <= MAX_GRID_COLS]
        out.append({"name": s.name, "hidden": s.hidden, "nrows": min(s.nrows, MAX_GRID_ROWS), "ncols": min(s.ncols, MAX_GRID_COLS),
                    "truncated": s.nrows > MAX_GRID_ROWS, "cells": cells,
                    "merges": [m for m in s.merges if m[0] <= MAX_GRID_ROWS],
                    "hidden_rows": sorted(r for r in s.hidden_rows if r <= MAX_GRID_ROWS),
                    "hidden_cols": sorted(s.hidden_cols)})
    return {"sheets": out}


class RunReq(BaseModel):
    file: str
    mode: str = "rule_first"
    use_cache: bool = True
    use_llm: bool = True
    rules: str = "v1"


def _reset(e, res, mode, override):
    # core adds LLM_UNAVAILABLE only in rule_first; show it in llm_all too so a rules-only run is not presented as model-mapped
    if res.get("llm", {}).get("errors") and not any(w.get("code") == "LLM_UNAVAILABLE" for w in res["warnings"]):
        res["warnings"].append({"code": "LLM_UNAVAILABLE", "detail": "gọi mô hình lỗi, dùng luật"})
    e.update(res=res, mode=mode, override=override, approved=False, misa=None)
    res["file"] = e["name"]
    return res


@app.post("/api/run")
def run(q: RunReq):
    e = _entry(q.file)
    if not e:
        return err(404, "NOT_FOUND", "không có file")
    if q.mode not in ("rule_first", "llm_all"):
        return err(422, "BAD_MODE", "mode phải là rule_first hoặc llm_all")
    if q.rules not in ("v1", "v2"):
        return err(422, "BAD_RULES", "rules phải là v1 hoặc v2")
    with _lock:
        e["rules"] = q.rules
        res = normalize(e["path"], q.mode, use_llm=q.use_llm, use_cache=q.use_cache, rules=q.rules)
        return _reset(e, res, q.mode, None)


class Change(BaseModel):
    file: str
    tables: dict = {}   # {"t0": {"mapping": {"don_gia": "G"}, "confirmed": ["don_gia"]}}
    rows: dict = {}     # {"Sheet!12": {"trang_thai": "ok"|"bo"}}


@app.post("/api/override")
def override(ch: Change):
    e = _entry(ch.file)
    if not e or not e["res"]:
        return err(409, "NO_RUN", "chạy file trước")
    with _lock:
        last = e["res"]
        cur = json.loads(json.dumps(e["override"])) if e["override"] else {
            "schema_version": 1, "file_sha256": last["file_sha256"], "rows": {},
            "tables": {t["id"]: {"sheet": t["sheet"], "header_rows": t["header_rows"], "data_rows": t["data_rows"],
                                 "mapping": {f: v["col"] for f, v in t["mapping"].items()}, "confirmed": []}
                       for t in last["tables"]}}
        try:
            review._merge(cur, ch)
        except OverrideError as ex:
            return err(422, ex.code, ex.detail)
        res = normalize(e["path"], e["mode"], override=cur, lenient_rows=set(cur["rows"]) - set(ch.rows),
                        rules=e.get("rules", "v1"))
        if res["status"] == "error":
            return err(422, res["error_code"], res["error_detail"])
        return _reset(e, res, e["mode"], cur)


def _blocking(res):
    return [q for q in res["review_queue"] if q["blocking"]]


class FileReq(BaseModel):
    file: str


@app.post("/api/approve")
def approve(q: FileReq):
    e = _entry(q.file)
    if not e or not e["res"]:
        return err(409, "NO_RUN", "chạy file trước")
    if e["res"]["status"] == "error":
        return err(409, "RUN_ERROR", "file lỗi, không có gì để duyệt")
    if _blocking(e["res"]):
        return err(409, "BLOCKING_OPEN", "còn mục blocking chưa đóng")
    e["approved"] = True
    return {"approved": True}


def _misa_out(e):
    if not e.get("misa"):
        e["misa"] = misa_export.export(e["res"])
    return e["misa"]


def _locked(e):
    if not e or not e["res"] or e["res"]["status"] == "error" or not e["approved"] or _blocking(e["res"]):
        return err(409, "EXPORT_LOCKED", "chỉ xuất khi đã duyệt và không còn mục blocking")


@app.get("/api/misa")
def misa(file: str):
    e = _entry(file)
    if (r := _locked(e)):
        return r
    out = _misa_out(e)
    ws = openpyxl.load_workbook(io.BytesIO(out["files"][0][1]))[misa_export.SHEET]
    last = 5 + min(out["n_rows"], 200)
    rows = [["" if c.value is None else c.value for c in ws[n][2:24]] for n in range(1, last + 1)]
    return {"rows": rows, "first_col": 3, "n_rows": out["n_rows"], "files": [n for n, _ in out["files"]],
            "report": out["report"], "bao_cao_name": out["bao_cao_name"]}


@app.get("/api/misa/download")
def misa_dl(file: str, kind: str = "xlsx", n: int = 0):
    e = _entry(file)
    if (r := _locked(e)):
        return r
    out = _misa_out(e)
    if kind == "bao_cao":
        name, data, mt = out["bao_cao_name"], out["bao_cao_csv"], "text/csv; charset=utf-8"
    else:
        if not 0 <= n < len(out["files"]):
            return err(404, "NOT_FOUND", "không có file")
        name, data = out["files"][n]
        mt = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return Response(data, media_type=mt, headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(name)})


@app.get("/api/csv")
def csv_dl(file: str):
    e = _entry(file)
    if not e or not e["res"]:
        return err(409, "NO_RUN", "chạy file trước")
    buf = io.StringIO(newline="")
    write_csv(buf, e["res"])
    name = os.path.splitext(e["name"])[0] + ".csv"
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(name)})


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
