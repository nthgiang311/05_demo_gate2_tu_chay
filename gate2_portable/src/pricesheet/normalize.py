"""Layer 7: cell-value normalizers (price, date, code, name, unit, currency). Pure functions."""
import datetime as dt
import re
import unicodedata
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

NBSP_RE = re.compile(r"\s+")


def fold(s):
    """Lower-case, accent-free, punctuation-free text for comparisons."""
    s = unicodedata.normalize("NFD", str(s)).replace("đ", "d").replace("Đ", "D")
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"[^0-9a-zA-Z%]+", " ", s.lower())
    return s.strip()


def clean_text(v):
    """NFC + collapse whitespace; never removes characters."""
    return NBSP_RE.sub(" ", unicodedata.normalize("NFC", str(v))).strip()


# ---------------------------------------------------------------- price
CUR_WORDS = r"(?:vnd|vnđ|đ|₫|d|đồng|dong|usd|eur|jpy|\$|€|¥|vn)"
RANGE_RE = re.compile(r"\d[\d.,\s]*\s*(?:-|–|—|~|đến|den|to)\s*\d")
NUM_CORE = re.compile(r"[-+]?\d[\d.,\s]*|[-+]?[.,]\d+")


def dec_str(d):
    """Canonical Decimal string: no exponent, no trailing zeros, no rounding."""
    if d == d.to_integral_value():
        return str(int(d))
    return format(d.normalize(), "f")


def sep_vote(txt):
    """'vn' | 'us' | 'amb' | None: the separator style a numeric string proves by itself."""
    t = txt.strip().replace(" ", "")
    if "." in t and "," in t:
        return "vn" if t.rfind(",") > t.rfind(".") else "us"
    for sep, other in ((".", "vn"), (",", "us")):
        n = t.count(sep)
        if n == 0:
            continue
        if n > 1:
            return other
        i, f = t.split(sep)
        i = i.lstrip("+-")
        if len(f) == 3 and 1 <= len(i) <= 3 and not i.startswith("0"):
            return "amb"
        return "us" if sep == "." else "vn"   # lone dot, non-3 digits = US decimal; lone comma = VN decimal
    return None


def _to_decimal(core, style):
    t = core.replace(" ", "")
    neg = t.startswith("-")
    t = t.lstrip("+-")
    if style == "vn":
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", "")
    d = Decimal(t)
    return -d if neg else d


def parse_price(v, kind, style="vn", mult=Decimal(1)):
    """Return (Decimal|None, issues, reason). reason in None|'empty'|'text'|'range'|'error'|'zero'.
    issues are ma_van_de codes."""
    issues = []
    if v is None or v == "":
        return None, ["GIA_TRONG"], "empty"
    if kind == "e":
        return None, ["GIA_LOI_EXCEL"], "error"
    if kind == "b":
        return None, ["GIA_LIEN_HE"], "text"
    if kind == "n":
        try:
            d = Decimal(str(v)) if isinstance(v, float) else Decimal(v)
        except InvalidOperation:
            return None, ["GIA_LIEN_HE"], "text"
        return _finish(d * mult, issues)
    s = clean_text(v)
    if not s:
        return None, ["GIA_TRONG"], "empty"
    if s.startswith("#"):
        return None, ["GIA_LOI_EXCEL"], "error"
    if RANGE_RE.search(re.sub(r"^[-+]", "", s)):
        return None, ["GIA_KHOANG"], "range"
    m = NUM_CORE.search(s)
    if not m:
        return None, ["GIA_LIEN_HE"], "text"
    core = m.group(0).strip().rstrip(".,")
    rest = (s[:m.start()] + " " + s[m.end():]).strip().lower()
    has_k = bool(re.search(r"(?<![a-zà-ỹ])k\b|nghìn|nghin", rest))
    st = sep_vote(core)
    use = style if st in (None, "amb") else st
    try:
        d = _to_decimal(core, use)
    except InvalidOperation:
        return None, ["GIA_LIEN_HE"], "text"
    if has_k:
        d *= 1000
    if rest and re.search(CUR_WORDS + r"|k\b", rest):
        issues.append("GIA_CO_DON_VI")
    elif use == "us" and ("," in core or "." in core):
        issues.append("GIA_CHU_US")
    elif use == "vn" and ("." in core or "," in core):
        issues.append("GIA_CHU_VN")
    return _finish(d * mult, issues)


def _finish(d, issues):
    if d <= 0:
        return d, issues + ["GIA_0_AM"], "zero"
    if d != d.to_integral_value():
        issues = issues + ["GIA_LE_THAP_PHAN"]
    return d, issues, None


def excel_round(d, n):
    if n >= 0:
        return d.quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP)
    f = Decimal(10) ** -n
    return (d / f).quantize(Decimal(1), rounding=ROUND_HALF_UP) * f


# ---------------------------------------------------------------- formula (same-row arithmetic only)
_TOK = re.compile(r"\s*(?:(\d+\.?\d*(?:[eE][+-]?\d+)?)|(\$?[A-Za-z]{1,3}\$?\d+)|([A-Za-z]+)\(|([-+*/(),%]))")


def eval_formula(f, getter):
    """Evaluate '=D5*(1-E5)' / '=ROUND(..,n)'; getter(col_letters, row)->Decimal|None.
    Returns Decimal, or None for anything unsupported (other functions, cross-row refs are the getter's call)."""
    s = f.lstrip("=").strip()
    toks, pos = [], 0
    while pos < len(s):
        m = _TOK.match(s, pos)
        if not m or m.end() == pos:
            return None
        pos = m.end()
        if m.group(1):
            toks.append(("n", Decimal(m.group(1))))
        elif m.group(2):
            toks.append(("r", m.group(2).replace("$", "").upper()))
        elif m.group(3):
            if m.group(3).upper() != "ROUND":
                return None
            toks.append(("f", "ROUND"))
        else:
            toks.append(("o", m.group(4)))
    i = [0]

    def peek():
        return toks[i[0]] if i[0] < len(toks) else (None, None)

    def eat():
        t = toks[i[0]]
        i[0] += 1
        return t

    def expr():
        v = term()
        while peek() in (("o", "+"), ("o", "-")):
            op = eat()[1]
            r = term()
            v = v + r if op == "+" else v - r
        return v

    def term():
        v = unary()
        while peek() in (("o", "*"), ("o", "/")):
            op = eat()[1]
            r = unary()
            v = v * r if op == "*" else v / r
        return v

    def unary():
        if peek() == ("o", "-"):
            eat()
            return -unary()
        if peek() == ("o", "+"):
            eat()
        return atom()

    def atom():
        t, x = eat()
        if t == "n":
            v = x
        elif t == "r":
            m = re.match(r"([A-Z]+)(\d+)", x)
            v = getter(m.group(1), int(m.group(2)))
            if v is None:
                raise ValueError
        elif t == "f":
            a = expr()
            if eat() != ("o", ","):
                raise ValueError
            b = expr()
            if eat() != ("o", ")"):
                raise ValueError
            return excel_round(a, int(b))
        elif (t, x) == ("o", "("):
            v = expr()
            if eat() != ("o", ")"):
                raise ValueError
        else:
            raise ValueError
        if peek() == ("o", "%"):
            eat()
            v = v / 100
        return v

    try:
        v = expr()
        return v if i[0] == len(toks) else None
    except (ValueError, ZeroDivisionError, IndexError, InvalidOperation, TypeError):
        return None


# ---------------------------------------------------------------- dates
def _mk(y, m, d):
    try:
        return dt.date(y, m, d)
    except ValueError:
        return None


def _year(y):
    return y + 2000 if y < 100 else y


DATE_RE = re.compile(r"(?<!\d)(\d{1,4})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{2,4})(?!\d)")
DM_RE = re.compile(r"(?<!\d)(\d{1,2})\s*[/\-.]\s*(\d{1,2})(?![\d/\-.])")
MONTH_RE = re.compile(r"(?:\bT|th[aá]ng\s*)(\d{1,2})\s*(?:/|-|\s+n[aă]m\s*)\s*(\d{4})", re.I)
VNDATE_RE = re.compile(r"ng[aà]y\s*(\d{1,2})\s*th[aá]ng\s*(\d{1,2})\s*n[aă]m\s*(\d{4})", re.I)


RECALL_RE = re.compile(r"thu hồi|hết hiệu lực|hết hạn|ngừng|đình chỉ|hủy bỏ", re.I)


def date_vote(s):
    """'dmy' | 'mdy' | None: the order a numeric date string proves by itself."""
    m = DATE_RE.search(str(s))
    if not m or len(m.group(1)) == 4:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    if a > 12 and b <= 12:
        return "dmy"
    if b > 12 and a <= 12:
        return "mdy"
    return None


def serial_to_date(n, epoch1904=False):
    base = dt.date(1904, 1, 1) if epoch1904 else dt.date(1899, 12, 30)
    try:
        return base + dt.timedelta(days=int(n))
    except (OverflowError, ValueError):
        return None


def parse_date(v, kind, order="dmy", epoch1904=False):
    """Return (iso|None, issues, ambiguous). order: dmy | mdy | None (None = ambiguous cells stay unresolved)."""
    if v is None or v == "":
        return None, [], False
    if kind == "d":
        d = v.date() if isinstance(v, dt.datetime) else v
        return d.isoformat(), [], False
    if kind == "n":
        if 20000 < float(v) < 80000:
            d = serial_to_date(v, epoch1904)
            return (d.isoformat(), ["NGAY_SO"], False) if d else (None, [], False)
        return None, [], False
    s = clean_text(v)
    if RECALL_RE.search(s):      # 'Đã thu hồi. Ngày thu hồi: 06/06/2022' is not an effective date
        return None, ["HIEU_LUC_THU_HOI"], False
    m = VNDATE_RE.search(s)
    if m:
        d = _mk(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        return (d.isoformat(), ["NGAY_CHU"], False) if d else (None, [], False)
    m = MONTH_RE.search(s)
    if m:
        d = _mk(int(m.group(2)), int(m.group(1)), 1)
        return (d.isoformat(), ["NGAY_CHU"], False) if d else (None, [], False)
    m = DATE_RE.search(s)
    if m:
        a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
        extra = ["NGAY_KHOANG"] if re.search(r"\b(?:đến|den|to)\b|^\s*từ", s, re.I) else []
        if len(m.group(1)) == 4:
            d = _mk(a, b, c)
            return (d.isoformat(), extra, False) if d else (None, [], False)
        y = _year(c)
        vote = date_vote(s)
        if vote == "dmy" or a == b:
            d = _mk(y, b, a)
        elif vote == "mdy":
            d = _mk(y, a, b)
        elif order == "mdy":
            d = _mk(y, a, b)
        elif order == "dmy":
            d = _mk(y, b, a)
        else:
            return None, ["NGAY_MY"], True
        if d is None:
            return None, [], False
        if extra:  # "Từ 06/11 đến 28/11/2026": first date is dd/mm without year
            m0 = DM_RE.search(s)
            if m0 and m0.start() < m.start():
                d0 = _mk(y, int(m0.group(2)), int(m0.group(1)))
                if d0:
                    d = d0
        return d.isoformat(), extra, False
    return None, [], False


# ---------------------------------------------------------------- code / name / unit / currency
def norm_code(v, kind, fmt="General"):
    """Return (code_str, issues, needs_review). Numbers keep digits; leading zeros come back from a '00000' format."""
    if v is None:
        return "", [], False
    if kind == "n":
        if isinstance(v, float) and (not v.is_integer() or abs(v) >= 1e11):
            return "{:.2E}".format(v), ["MA_KHOA_HOC"], True
        n = int(v)
        if re.fullmatch(r"0+", fmt or ""):
            return str(n).zfill(len(fmt)), ["MA_MAT_SO_0"], False
        return str(n), ["MA_MAT_SO_0"], True
    s = clean_text(v)
    if re.fullmatch(r"\d\.\d+E\+\d+", s, re.I):
        return s, ["MA_KHOA_HOC"], True
    if len(s) > 50:
        return s, ["MA_QUA_DAI"], True
    return s, [], False


UNITS = "Viên Vỉ Hộp Lọ Ống Tuýp Chai Gói Cái".split()   # unknown spellings keep the trimmed source text
UNIT_CANON = {fold(u): u for u in UNITS}
SPEC_UNITS = {fold(u) for u in "Bộ Chiếc Thùng Lốc Túi Cuộn Bao Cây Bóng Lon Hũ Bịch Cặp Đôi Tuýt Gói".split()}
METRIC = {"kg", "g", "m", "m2", "m3", "l", "ml", "cm", "mm"}


def norm_unit(v):
    if v is None:
        return "", []
    s = clean_text(v)
    if not s:
        return "", []
    if fold(s) in METRIC:
        return s, []
    c = UNIT_CANON.get(fold(s))
    if c:
        return c, (["DVT_NHIEU_KIEU"] if c != s else [])
    return s, (["DVT_NHIEU_KIEU"] if len(s) == 1 else [])


def unit_from_spec(spec):
    """Leading unit word of 'Hộp 10 vỉ x 10 viên' when there is no unit column."""
    m = re.match(r"\s*([^\d\s/x×(]+)", clean_text(spec))
    if m and (fold(m.group(1)) in UNIT_CANON or fold(m.group(1)) in SPEC_UNITS):
        return UNIT_CANON.get(fold(m.group(1)), m.group(1).capitalize())
    return ""


CUR_MAP = {"vnd": "VND", "vnđ": "VND", "đ": "VND", "₫": "VND", "vn": "VND", "đồng": "VND", "dong": "VND",
           "usd": "USD", "$": "USD", "us$": "USD", "eur": "EUR", "€": "EUR", "jpy": "JPY", "¥": "JPY", "yen": "JPY"}


def norm_currency(v):
    s = clean_text(v).lower() if v is not None else ""
    if not s:
        return ""
    if s in CUR_MAP:
        return CUR_MAP[s]
    return s.upper() if re.fullmatch(r"[a-z]{3}", s) else clean_text(v)


def extras_value(c):
    """Keep value as read: numbers as numbers, dates ISO, text as clean text."""
    if c is None or c.v is None:
        return None
    if c.kind == "d":
        return (c.v.date() if isinstance(c.v, dt.datetime) else c.v).isoformat()
    if c.kind == "n":
        return int(c.v) if isinstance(c.v, float) and c.v.is_integer() else c.v
    if c.kind == "b":
        return c.v
    return clean_text(c.v) or None


PRICE_LIKE = re.compile(r"[-+]?[$€¥]?\d[\d.,\s]*\s*(?:vnd|vnđ|đ|₫|d|k|usd|eur|jpy|đồng)?(?:\s*[-–]\s*\d[\d.,\s]*)?", re.I)


def looks_price(v, kind):
    """True when a cell is a number or a string that is only a number with an optional currency mark."""
    if kind == "n":
        return True
    return kind == "s" and bool(PRICE_LIKE.fullmatch(clean_text(v)))


FOREIGN_CUR = re.compile(r"(?<![a-z])(usd|eur|jpy|cny|krw|sgd|thb)(?![a-z])|(us\$)|([$€¥])", re.I)


def cell_currency(v):
    """Foreign currency written inside a price cell ('2.38 USD', '$5'), else ''."""
    m = FOREIGN_CUR.search(str(v)) if isinstance(v, str) else None
    return norm_currency(m.group(0)) if m else ""
