"""Layer 0: detect the real format from the first bytes, not the extension."""
import os, zipfile

OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def sniff(path):
    """Return (kind, error_code, detail). kind in xlsx|xls|None."""
    try:
        size = os.path.getsize(path)
        if size == 0:
            return None, "FILE_EMPTY", "File 0 byte"
        with open(path, "rb") as f:
            head = f.read(4096)
    except OSError as e:
        return None, "FILE_CORRUPT", f"Không đọc được file: {e}"
    return sniff_bytes(path, head)


def sniff_bytes(path, head):
    if head[:2] == b"PK":
        try:
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
                bad = z.testzip()
        except Exception as e:
            return None, "FILE_CORRUPT", f"Zip hỏng hoặc bị cắt: {e}"
        if bad:
            return None, "FILE_CORRUPT", f"Zip hỏng ({bad})"
        if any(n.startswith("xl/") for n in names):
            if "xl/workbook.bin" in names:
                return None, "UNSUPPORTED_FORMAT", "Định dạng thật: xlsb"
            return "xlsx", None, None
        if "content.xml" in names and "mimetype" in names:
            return None, "UNSUPPORTED_FORMAT", "Định dạng thật: ods"
        if "EncryptionInfo" in names:
            return None, "FILE_ENCRYPTED", "File có mật khẩu"
        return None, "UNSUPPORTED_FORMAT", "Định dạng thật: zip không phải xlsx"
    if head[:8] == OLE2:
        # shortcut: encrypted xlsx is OLE2 with EncryptionInfo stream, looked up by raw scan
        try:
            if b"E\x00n\x00c\x00r\x00y\x00p\x00t\x00i\x00o\x00n\x00I\x00n\x00f\x00o" in open(path, "rb").read():
                return None, "FILE_ENCRYPTED", "File có mật khẩu"
        except OSError:
            pass
        return "xls", None, None
    if head[:4] == b"%PDF":
        return None, "WRONG_FORMAT_PDF", "File thực chất là PDF, hãy xin bản Excel"
    h = head.lstrip(b"\xef\xbb\xbf \t\r\n")[:200].lower()
    if h.startswith(b"<?xml") and b"urn:schemas-microsoft-com:office:spreadsheet" in head.lower():
        return None, "UNSUPPORTED_FORMAT", "Định dạng thật: XML Spreadsheet 2003"
    if h.startswith(b"<?xml"):
        return None, "UNSUPPORTED_FORMAT", "Định dạng thật: XML"
    if h.startswith((b"<html", b"<!doctype", b"<table", b"<meta", b"<head", b"<body")):
        return None, "UNSUPPORTED_FORMAT", "Định dạng thật: HTML"
    if head[:8] == b"\x89PNG\r\n\x1a\n" or head[:3] == b"\xff\xd8\xff" or head[:4] in (b"GIF8", b"RIFF") or head[:2] == b"BM":
        return None, "UNSUPPORTED_FORMAT", "Định dạng thật: ảnh"
    if b"\x00" not in head:
        return None, "UNSUPPORTED_FORMAT", "Định dạng thật: văn bản/CSV"
    return None, "UNSUPPORTED_FORMAT", "Định dạng không nhận ra"
