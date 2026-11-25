"""Layer 1: any workbook -> Workbook/Sheet/Cell grid. Later layers only see this."""
import datetime as dt
from dataclasses import dataclass, field

from openpyxl.utils import get_column_letter as col_letter, column_index_from_string as col_index  # noqa: F401


@dataclass
class Cell:
    v: object = None      # str | int | float | datetime | bool | None
    kind: str = ""        # s n d e b ("" = empty)
    f: str = None         # formula text when no cached value exists
    fmt: str = "General"


@dataclass
class Sheet:
    name: str
    hidden: bool = False
    cells: dict = field(default_factory=dict)   # (row, col) -> Cell
    hidden_rows: set = field(default_factory=set)
    hidden_cols: set = field(default_factory=set)
    merges: list = field(default_factory=list)  # (r1, c1, r2, c2)
    nrows: int = 0
    ncols: int = 0
    empty_str: set = field(default_factory=set)  # cells holding a literal empty string (kept for extras)

    def get(self, r, c):
        return self.cells.get((r, c))

    def val(self, r, c):
        x = self.cells.get((r, c))
        return x.v if x else None

    def ref(self, r, c):
        return f"{col_letter(c)}{r}"


@dataclass
class Workbook:
    sheets: list
    epoch1904: bool = False


def _kind(v, dtype=None):
    if v is None:
        return ""
    if dtype == "e":
        return "e"
    if isinstance(v, bool):
        return "b"
    if isinstance(v, (int, float)):
        return "n"
    if isinstance(v, (dt.datetime, dt.date, dt.time)):
        return "d"
    return "s"


def read_xlsx(path):
    import openpyxl
    with open(path, "rb") as fh:          # file object: skips openpyxl's extension check (renamed files)
        wv = openpyxl.load_workbook(fh, data_only=True)
    with open(path, "rb") as fh:
        wf = openpyxl.load_workbook(fh, data_only=False)
    sheets = []
    for sv in wv.worksheets:
        sf = wf[sv.title]
        sh = Sheet(sv.title, hidden=sv.sheet_state != "visible")
        sh.nrows, sh.ncols = sv.max_row or 0, sv.max_column or 0
        if sh.nrows * max(sh.ncols, 1) > 3_000_000:
            raise MemoryError("sheet quá lớn")
        for row in sv.iter_rows():
            for c in row:
                fv = sf.cell(c.row, c.column).value
                formula = fv if isinstance(fv, str) and fv.startswith("=") else None
                if isinstance(c.value, str) and not c.value.strip():
                    sh.empty_str.add((c.row, c.column))
                if (c.value is None or (isinstance(c.value, str) and not c.value.strip())) and formula is None:
                    continue
                if c.value is None:
                    sh.cells[(c.row, c.column)] = Cell(None, "", formula, c.number_format)
                else:
                    sh.cells[(c.row, c.column)] = Cell(c.value, _kind(c.value, c.data_type), formula, c.number_format)
        for r, d in sv.row_dimensions.items():
            if d.hidden:
                sh.hidden_rows.add(r)
        for k, d in sv.column_dimensions.items():
            if d.hidden:
                for ci in range(col_index(k), (d.max or col_index(k)) + 1):
                    sh.hidden_cols.add(ci)
        for m in sv.merged_cells.ranges:
            sh.merges.append((m.min_row, m.min_col, m.max_row, m.max_col))
        sheets.append(sh)
    return Workbook(sheets, epoch1904=(wv.epoch.year == 1904))


def read_xls(path):
    import xlrd
    wb = xlrd.open_workbook(path, formatting_info=True)
    sheets = []
    for i, s in enumerate(wb.sheets()):
        sh = Sheet(s.name, hidden=s.visibility != 0, nrows=s.nrows, ncols=s.ncols)
        for r in range(s.nrows):
            for c in range(s.ncols):
                t, v = s.cell_type(r, c), s.cell_value(r, c)
                if t == xlrd.XL_CELL_TEXT and not v.strip():
                    sh.empty_str.add((r + 1, c + 1))
                if t in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK) or (t == xlrd.XL_CELL_TEXT and not v.strip()):
                    continue
                fmt = "General"
                try:
                    fmt = wb.format_map[wb.xf_list[s.cell_xf_index(r, c)].format_key].format_str
                except Exception:
                    pass
                if t == xlrd.XL_CELL_DATE:
                    v, k = xlrd.xldate_as_datetime(v, wb.datemode), "d"
                elif t == xlrd.XL_CELL_ERROR:
                    v, k = xlrd.error_text_from_code.get(v, "#ERR"), "e"
                elif t == xlrd.XL_CELL_BOOLEAN:
                    v, k = bool(v), "b"
                elif t == xlrd.XL_CELL_NUMBER:
                    k = "n"
                else:
                    k = "s"
                sh.cells[(r + 1, c + 1)] = Cell(v, k, None, fmt)
        for r, ri in s.rowinfo_map.items():
            if ri.hidden:
                sh.hidden_rows.add(r + 1)
        for c, ci in s.colinfo_map.items():
            if ci.hidden:
                sh.hidden_cols.add(c + 1)
        for r1, r2, c1, c2 in s.merged_cells:
            sh.merges.append((r1 + 1, c1 + 1, r2, c2))
        sheets.append(sh)
    return Workbook(sheets, epoch1904=wb.datemode == 1)


def read_grid(path, kind):
    return read_xlsx(path) if kind == "xlsx" else read_xls(path)
