"""Assert-based self-check: python -X utf8 -m pricesheet.selftest"""
import os
import tempfile
from decimal import Decimal

from .normalize import (clean_text, dec_str, eval_formula, norm_code, norm_unit, parse_date, parse_price, sep_vote,
                        unit_from_spec, cell_currency)
from .sniff import sniff
from .mapping_rules import extras_key, header_scores


def price(v, kind="s", style="vn", mult=1):
    d, iss, reason = parse_price(v, kind, style, Decimal(mult))
    return (dec_str(d) if d is not None else "", reason)


def main():
    # price: unambiguous cells read by themselves, ambiguous by column style, default Vietnamese
    assert price("6.400") == ("6400", None)
    assert price("6.400", style="us") == ("6.4", None)
    assert price("1.250.000") == ("1250000", None)
    assert price("1,250.50") == ("1250.5", None)
    assert price("1,250,000", style="vn") == ("1250000", None)
    assert price("11,025", style="us") == ("11025", None)
    assert price("11,025", style="vn") == ("11.025", None)
    assert price("6,5") == ("6.5", None)
    assert price("0.14") == ("0.14", None)
    assert price("104,000.00") == ("104000", None)
    assert price("103000 VNĐ") == ("103000", None)
    assert price("6.400đ") == ("6400", None)
    assert price("6,4k") == ("6400", None)
    assert price("2.38 USD") == ("2.38", None)
    assert price("6,4", mult=1000) == ("6400", None)
    assert price(124500.25, "n") == ("124500.25", None)
    assert price(0, "n")[1] == "zero" and price(-500, "n") == ("-500", "zero")
    assert price("91.500-92.500")[1] == "range"
    assert price("Liên hệ")[1] == "text" and price("-")[1] == "text"
    assert price("#N/A", "e")[1] == "error" and price(None, "")[1] == "empty"
    assert sep_vote("65.000") == "amb" and sep_vote("0.500") == "us" and sep_vote("1.234.567") == "vn"
    assert cell_currency("2.38 USD") == "USD" and cell_currency("6.400đ") == ""
    # formula (same-row arithmetic only)
    vals = {"D": Decimal(64000), "E": Decimal("0.12")}
    assert eval_formula("=ROUND(D5*(1-E5),-2)", lambda c, r: vals.get(c)) == Decimal(56300)
    assert eval_formula("=D5*1.05", lambda c, r: vals.get(c)) == Decimal("67200.00")
    assert eval_formula("=SUM(D5:E5)", lambda c, r: vals.get(c)) is None
    assert eval_formula("=__import__('os')", lambda c, r: None) is None
    # dates
    import datetime as dt
    assert parse_date("13-12-26", "s")[0] == "2026-12-13"
    assert parse_date("12/15/2026", "s")[0] == "2026-12-15"
    assert parse_date("03/04/2026", "s", None)[2] is True              # ambiguous, order unknown -> unresolved
    assert parse_date("03/04/2026", "s", "mdy")[0] == "2026-03-04"
    assert parse_date("T12/2026", "s")[0] == "2026-12-01"
    assert parse_date("tháng 12 năm 2026", "s")[0] == "2026-12-01"
    assert parse_date("Từ 06/11 đến 28/11/2026", "s")[0] == "2026-11-06"
    assert parse_date(46377, "n")[0] == "2026-12-21"
    assert parse_date(dt.datetime(2026, 12, 1, 10, 30), "d")[0] == "2026-12-01"
    assert parse_date("2026-11-17 10:36:13", "s")[0] == "2026-11-17"
    assert parse_date(1000, "n", epoch1904=True)[0] is None          # not a plausible serial
    # codes, names, units
    assert norm_code("PARA500\xa0", "s")[0] == "PARA500"
    assert norm_code(194, "n", "00000") == ("00194", ["MA_MAT_SO_0"], False)
    assert norm_code(157, "n")[2] is True
    assert norm_code(8.9e12, "n")[0] == "8.90E+12"
    assert norm_code("X" * 51, "s")[1] == ["MA_QUA_DAI"]
    assert clean_text("Cefixim\n100mg  viên nang") == "Cefixim 100mg viên nang"
    import unicodedata
    assert clean_text(unicodedata.normalize("NFD", "Hộp")) == "Hộp"
    assert norm_unit("HỘP ")[0] == "Hộp" and norm_unit("Vỉ 10 ")[0] == "Vỉ 10" and norm_unit("kg")[0] == "kg"
    assert unit_from_spec("Hộp 1 vỉ x 10 viên") == "Hộp" and unit_from_spec("10x10") == ""
    # header synonyms
    assert header_scores("Đơn giá\n(VNĐ)").get("don_gia", 0) >= 0.9
    assert header_scores("Gía bán").get("don_gia", 0) >= 0.9
    assert extras_key("Số ĐK") == "so_dang_ky" and extras_key("Giá có VAT") == "gia_co_vat" and extras_key("Bậc 2 (mua 10-49)") == "bac_2"
    assert extras_key("Mã kho") is None
    # sniff
    with tempfile.TemporaryDirectory() as d:
        def mk(name, data):
            p = os.path.join(d, name)
            with open(p, "wb") as f:
                f.write(data)
            return p
        assert sniff(mk("a.xlsx", b""))[1] == "FILE_EMPTY"
        assert sniff(mk("b.xlsx", b"%PDF-1.4 ..."))[1] == "WRONG_FORMAT_PDF"
        assert sniff(mk("c.xls", b"<html><table>"))[1] == "UNSUPPORTED_FORMAT"
        assert sniff(mk("d.xls", b'<?xml version="1.0"?><Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet">'))[2].endswith("2003")
        assert sniff(mk("e.xlsx", b"PK\x03\x04garbage"))[1] == "FILE_CORRUPT"
        assert sniff(mk("f.xlsx", "Mã;Tên\n1;2\n".encode("utf-8")))[1] == "UNSUPPORTED_FORMAT"
        assert sniff(mk("g.xlsx", b"\x89PNG\r\n\x1a\n" + b"\0" * 20))[1] == "UNSUPPORTED_FORMAT"
        import zipfile
        p = os.path.join(d, "h.xlsx")
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("xl/workbook.xml", "<x/>")
        assert sniff(p) == ("xlsx", None, None)
    print("selftest OK")


if __name__ == "__main__":
    main()
