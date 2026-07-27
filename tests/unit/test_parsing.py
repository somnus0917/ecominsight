from __future__ import annotations

from datetime import date

from ecom_insight.utils.parsing import (
    embedded_yuan_to_fen,
    fen_to_yuan_fen,
    parse_date,
    parse_price_quantity,
    yuan_to_fen,
)


def test_money_units_are_exact() -> None:
    assert fen_to_yuan_fen(12345) == 12345
    assert yuan_to_fen("123.45") == 12345
    assert yuan_to_fen("-0.01") == -1
    assert embedded_yuan_to_fen("预计收入 ¥1,234.56") == 123456


def test_price_quantity_parser() -> None:
    assert parse_price_quantity("¥5,499.00 x 2") == (549900, 2)
    assert parse_price_quantity("") == (None, None)


def test_date_parser_accepts_source_slashes() -> None:
    assert parse_date("2026/07/26") == date(2026, 7, 26)
    assert parse_date("0000-00-00") is None
