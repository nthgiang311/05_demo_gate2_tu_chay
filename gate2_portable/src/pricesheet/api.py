"""POST /api/v1/normalize (spec 2.5). Always answers with out.json; HTTP status from error_code."""
import json
import os
import tempfile

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from .graph import normalize
from .override import error_result

MAX_BYTES = 10 * 1024 * 1024
HTTP_BY_CODE = {
    "FILE_EMPTY": 400, "FILE_CORRUPT": 400, "OVERRIDE_STALE": 409,
    "FILE_TOO_LARGE": 413, "TOO_MANY_SHEETS": 413, "TOO_MANY_ROWS": 413,
    "WRONG_FORMAT_PDF": 415, "UNSUPPORTED_FORMAT": 415, "FILE_ENCRYPTED": 415,
    "NO_HEADER_FOUND": 422, "NO_PRICE_COLUMN": 422, "NO_DATA_ROWS": 422, "OVERRIDE_INVALID": 422,
    "BAD_MODE": 422, "INTERNAL_ERROR": 500,
}

router = APIRouter()


def http_status(res):
    return HTTP_BY_CODE.get(res.get("error_code"), 500) if res["status"] == "error" else 200


def reply(res):
    return JSONResponse(res, status_code=http_status(res))


def too_large(name, mode="rule_first"):
    return error_result(name, "FILE_TOO_LARGE", "Hơn 10 MB", mode)


def bad_mode(name):
    return error_result(name, "BAD_MODE", "mode phải là rule_first hoặc llm_all")


def read_limited(file: UploadFile):
    """At most 10 MB + 1 byte; None when bigger (nothing written)."""
    data = file.file.read(MAX_BYTES + 1)
    return None if len(data) > MAX_BYTES else data


def with_temp_file(name, data, fn):
    """Write data to a temp file that keeps the original extension, call fn(path), always delete it."""
    ext = os.path.splitext(os.path.basename(name or ""))[1].lower()
    ext = ext if ext.isascii() and ext[1:].isalnum() and len(ext) <= 6 else ""
    fd, path = tempfile.mkstemp(suffix=ext)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return fn(path)
    finally:
        os.remove(path)


def parse_override(raw):
    """JSON text -> dict, or None. Raises ValueError when it is not a JSON object."""
    if raw is None or not raw.strip():
        return None
    ov = json.loads(raw)
    if not isinstance(ov, dict):
        raise ValueError("override phải là object")
    if "_lenient_rows" in ov:
        raise ValueError("khóa _lenient_rows không hợp lệ")
    return ov


@router.post("/normalize")
def normalize_endpoint(file: UploadFile = File(...), mode: str = Form("rule_first"), override: str | None = Form(None)):
    name = file.filename or "upload"
    if mode not in ("rule_first", "llm_all"):
        return reply(bad_mode(name))
    data = read_limited(file)
    if data is None:
        return reply(too_large(name, mode))
    try:
        ov = parse_override(override)
    except ValueError as e:
        res = error_result(name, "OVERRIDE_INVALID", f"override không phải JSON object: {str(e)[:100]}", mode)
        return reply(res)

    def go(path):
        res = normalize(path, mode, override=ov)
        res["file"] = os.path.basename(name)  # temp path name -> original name
        return res

    return reply(with_temp_file(name, data, go))
