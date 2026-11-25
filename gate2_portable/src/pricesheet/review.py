"""Review page + session API (spec 8). Two roles over HTTP Basic: nguoi_xu_ly, ke_toan.

State: cho_xu_ly -> cho_duyet -> da_duyet -> da_xuat; tra lai (kem ly do) -> cho_xu_ly; any new override -> cho_xu_ly.
Everything of a session (file, run_N.json, lich_su.json, meta.json) lives in one temp dir under ROOT."""
import io
import json
import os
import re
import secrets
import shutil
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from src.config import get_settings

from .api import bad_mode, read_limited, reply, too_large
from .cli import write_csv
from .graph import normalize
from .grid import col_index, col_letter, read_grid
from .override import OverrideError, error_result
from .sniff import sniff
from .tables import make_table

ROOT = Path(tempfile.gettempdir()) / "pricesheet_sessions"
TTL_CREATED, TTL_EXPORTED = 24 * 3600, 3600
ROLES = ("nguoi_xu_ly", "ke_toan")
SID = re.compile(r"[A-Za-z0-9_-]{8,40}")
_lock = threading.RLock()
_basic = HTTPBasic(auto_error=False)

router = APIRouter(prefix="/review")   # mounted under /api/v1
page_router = APIRouter()               # mounted at /


# ---- auth -------------------------------------------------------------------------------------------------------
def current_role(creds: HTTPBasicCredentials | None = Depends(_basic)):
    s = get_settings()
    pw = {"nguoi_xu_ly": s.review_nguoi_xu_ly_password, "ke_toan": s.review_ke_toan_password}
    if creds and pw.get(creds.username) and secrets.compare_digest(creds.password.encode(), pw[creds.username].encode()):
        return creds.username
    raise HTTPException(401, "Cần đăng nhập", headers={"WWW-Authenticate": 'Basic realm="pricesheet"'})


def role_is(*allowed):
    def dep(role: str = Depends(current_role)):
        if role not in allowed:
            raise HTTPException(403, detail={"error_code": "FORBIDDEN", "detail": f"vai trò {role} không được phép"})
        return role
    return dep


def fail(status, code, detail):
    raise HTTPException(status, detail={"error_code": code, "detail": detail})


# ---- session storage ----------------------------------------------------------------------------------------------
def _dir(sid):
    if not SID.fullmatch(sid):
        fail(404, "SESSION_NOT_FOUND", "không có phiên")
    d = ROOT / sid
    if not d.is_dir():
        fail(404, "SESSION_NOT_FOUND", "không có phiên")
    return d


def _jload(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _jsave(p, obj):
    p = Path(p)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, p)   # atomic: a concurrent reader never sees a half-written file


def cleanup():
    """Lazy: 24 h after creation or 1 h after export, whichever first."""
    with _lock:
        now = time.time()
        if not ROOT.is_dir():
            return
        for d in ROOT.iterdir():
            m = _jload(d / "meta.json")
            if not m:   # missing/unreadable meta: only an old dir is garbage (a new one may be mid-creation)
                old = now - d.stat().st_mtime > TTL_CREATED
            else:
                old = now - m.get("created", 0) > TTL_CREATED or bool(m.get("exported_at") and now - m["exported_at"] > TTL_EXPORTED)
            if old:
                shutil.rmtree(d, ignore_errors=True)


def _meta(d):
    return _jload(d / "meta.json")


def _latest(d):
    return _jload(d / f"run_{_meta(d)['runs'] - 1}.json")


def _log(d, role, viec, truoc, sau):
    h = _jload(d / "lich_su.json", [])
    h.append({"ai": role, "vai_tro": role, "luc": datetime.now().astimezone().isoformat(timespec="seconds"),
              "viec": viec, "truoc": truoc, "sau": sau})
    _jsave(d / "lich_su.json", h)


def _file(d):
    return str(next(p for p in d.iterdir() if p.name.startswith("file")))


def _blocking(res):
    return [q for q in res["review_queue"] if q["blocking"]]


def _view(d):
    m, res = _meta(d), _latest(d)
    names, raw = {}, {}
    try:
        kind, code, _ = sniff(_file(d))
        sheets = {s.name: s for s in read_grid(_file(d), kind).sheets}
        for t in res["tables"]:
            sh = sheets[t["sheet"]]
            names[t["id"]] = {col_letter(c): n for c, n in make_table(sh, t["header_rows"]).names.items()}
        for r in res["rows"]:
            if r["trang_thai"] == "can_xem":
                sh = sheets[r["nguon"].rpartition("!")[0]]
                raw[r["nguon"]] = {f: _cell_text(sheets, sh, ref) for f, ref in r["src"].items()}
    except Exception:  # view still works without header names / raw values
        pass
    return {"id": d.name, "file": m["file_name"], "state": m["state"], "ly_do_tra_lai": m.get("ly_do"),
            "result": res, "columns": names, "raw": raw, "lich_su": _jload(d / "lich_su.json", []),
            "co_blocking": bool(_blocking(res)), "override": m.get("override")}


def _cell_text(sheets, sh, ref):
    sheet, _, cell = ref.rpartition("!")
    sh = sheets.get(sheet, sh)
    mm = re.fullmatch(r"([A-Z]+)(\d+)", cell)
    if not mm:
        return ""
    v = sh.val(int(mm.group(2)), col_index(mm.group(1)))
    return "" if v is None else str(v)


def _open(sid):
    cleanup()
    return _dir(sid)


# ---- API ----------------------------------------------------------------------------------------------------------
@router.get("/me")
def me(role: str = Depends(current_role)):
    return {"role": role}


@router.get("/sessions")
def list_sessions(role: str = Depends(current_role)):
    cleanup()
    out = []
    for d in sorted(ROOT.iterdir() if ROOT.is_dir() else [], key=lambda p: -(_meta(p) or {}).get("created", 0)):
        m = _meta(d)
        if m:
            out.append({"id": d.name, "file": m["file_name"], "state": m["state"]})
    return out


@router.post("/sessions")
def create_session(file: UploadFile = File(...), mode: str = Form("rule_first"),
                   role: str = Depends(role_is("nguoi_xu_ly"))):
    name = os.path.basename(file.filename or "upload")
    if mode not in ("rule_first", "llm_all"):
        return reply(bad_mode(name))
    cleanup()
    data = read_limited(file)
    if data is None:
        return reply(too_large(name, mode))
    ext = os.path.splitext(name)[1].lower()
    ext = ext if ext.isascii() and ext[1:].isalnum() and len(ext) <= 6 else ""
    sid = secrets.token_urlsafe(12)
    d = ROOT / sid
    d.mkdir(parents=True)
    try:
        meta = {"created": time.time(), "state": "cho_xu_ly", "mode": mode, "file_name": name, "runs": 0,
                "override": None, "exported_at": None, "ly_do": None}
        _jsave(d / "meta.json", meta)   # first, so cleanup() never sees a live dir without meta
        (d / f"file{ext}").write_bytes(data)
        res = normalize(_file(d), mode)
        res["file"] = name
        if res["status"] == "error":
            shutil.rmtree(d, ignore_errors=True)
            return reply(res)
        _jsave(d / "run_0.json", res)
        _jsave(d / "meta.json", {**meta, "runs": 1})
        _log(d, role, "tai_len", None, "cho_xu_ly")
        return _view(d)
    except BaseException:
        shutil.rmtree(d, ignore_errors=True)
        raise


@router.get("/sessions/{sid}")
def get_session(sid: str, role: str = Depends(current_role)):
    return _view(_open(sid))


class Change(BaseModel):
    tables: dict = {}   # {"t0": {"mapping": {"don_gia": "G"}, "confirmed": ["don_gia"]}}
    rows: dict = {}     # {"Sheet!12": {"trang_thai": "ok"|"bo"}}


def _merge(cur, ch):
    for tid, t in ch.tables.items():
        if tid not in cur["tables"]:
            raise OverrideError(f"không có bảng {tid}")
        mp = t.get("mapping", {}) if isinstance(t, dict) else None
        cf = t.get("confirmed", []) if isinstance(t, dict) else None
        if not isinstance(mp, dict) or not isinstance(cf, list) or not all(isinstance(x, str) for x in cf):
            raise OverrideError(f"{tid}: mapping phải là object, confirmed phải là list chuỗi")
        c = cur["tables"][tid]
        c["mapping"].update(mp)
        c["confirmed"] = sorted(set(c["confirmed"]) | set(cf))
    cur["rows"].update(ch.rows)


@router.post("/sessions/{sid}/override")
def post_override(sid: str, ch: Change, role: str = Depends(role_is("nguoi_xu_ly"))):
    with _lock:
        d = _open(sid)
        m, last = _meta(d), _latest(d)
        if m["state"] == "da_xuat":
            fail(409, "SESSION_STATE", "phiên đã xuất, không sửa được")
        before = m["override"]
        cur = json.loads(json.dumps(before)) if before else {
            "schema_version": 1, "file_sha256": last["file_sha256"], "rows": {},
            "tables": {t["id"]: {"sheet": t["sheet"], "header_rows": t["header_rows"], "data_rows": t["data_rows"],
                                 "mapping": {f: v["col"] for f, v in t["mapping"].items()}, "confirmed": []}
                       for t in last["tables"]}}
        try:
            _merge(cur, ch)
        except OverrideError as e:
            return reply(error_result(_file(d), e.code, e.detail, m["mode"]))
        res = normalize(_file(d), m["mode"], override=cur, lenient_rows=set(cur["rows"]) - set(ch.rows))
        res["file"] = m["file_name"]
        if res["status"] == "error":
            return reply(res)
        _jsave(d / f"run_{m['runs']}.json", res)
        m.update(runs=m["runs"] + 1, override=cur, state="cho_xu_ly", ly_do=None)
        _jsave(d / "meta.json", m)
        _log(d, role, "override", before, {"override": cur, "trang_thai_phien": "cho_xu_ly"})
        return _view(d)


def _move(sid, role, viec, src, dst, ly_do=None):
    with _lock:
        d = _open(sid)
        m = _meta(d)
        if m["state"] != src:
            fail(409, "SESSION_STATE", f"phiên đang {m['state']}, cần {src}")
        if viec == "gui_duyet" and _blocking(_latest(d)):
            fail(409, "BLOCKING_OPEN", "còn mục blocking chưa đóng")
        _log(d, role, viec if ly_do is None else f"{viec}: {ly_do}", m["state"], dst)
        m.update(state=dst, ly_do=ly_do)
        _jsave(d / "meta.json", m)
        return _view(d)


@router.post("/sessions/{sid}/submit")
def submit(sid: str, role: str = Depends(role_is("nguoi_xu_ly"))):
    return _move(sid, role, "gui_duyet", "cho_xu_ly", "cho_duyet")


@router.post("/sessions/{sid}/approve")
def approve(sid: str, role: str = Depends(role_is("ke_toan"))):
    return _move(sid, role, "duyet", "cho_duyet", "da_duyet")


class Reason(BaseModel):
    ly_do: str = ""


@router.post("/sessions/{sid}/reject")
def reject(sid: str, body: Reason, role: str = Depends(role_is("ke_toan"))):
    if not body.ly_do.strip():
        fail(422, "REASON_REQUIRED", "trả lại phải kèm lý do")
    return _move(sid, role, "tra_lai", "cho_duyet", "cho_xu_ly", body.ly_do.strip())


@router.get("/sessions/{sid}/export")
def export(sid: str, format: str = "csv", role: str = Depends(role_is("ke_toan"))):
    if format not in ("csv", "json"):
        fail(422, "BAD_FORMAT", "format phải là csv hoặc json")
    with _lock:
        d = _open(sid)
        m, res = _meta(d), _latest(d)
        if m["state"] not in ("da_duyet", "da_xuat") or _blocking(res):
            fail(409, "EXPORT_LOCKED", "chỉ xuất khi đã duyệt và không còn mục blocking")
        stem = os.path.splitext(m["file_name"])[0]
        ext = ".out.json" if format == "json" else ".csv"
        cd = f'attachment; filename="export{ext}"; filename*=UTF-8\'\'{quote(stem + ext)}'   # non-ASCII safe
        if format == "json":
            resp = JSONResponse(res, headers={"Content-Disposition": cd})
        else:
            buf = io.StringIO(newline="")
            write_csv(buf, res)
            resp = Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": cd})
        if m["state"] == "da_duyet":   # state moves only after the body exists
            _log(d, role, "xuat", "da_duyet", "da_xuat")
            m.update(state="da_xuat", exported_at=time.time())
            _jsave(d / "meta.json", m)
        return resp


@page_router.get("/review", response_class=HTMLResponse)
def page(role: str = Depends(current_role)):
    return (Path(__file__).parent / "review.html").read_text(encoding="utf-8")

