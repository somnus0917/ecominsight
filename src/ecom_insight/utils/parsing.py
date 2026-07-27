from __future__ import annotations

import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


def fen_to_yuan_fen(value: Any) -> int | None:
    """Validate an integer-like source value already expressed in fen."""

    if value is None or value == "":
        return None
    try:
        return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"Invalid fen amount: {value!r}") from error


def yuan_to_fen(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    cleaned = text.replace(",", "").replace("￥", "").replace("¥", "").replace("元", "").strip()
    try:
        decimal_value = Decimal(cleaned)
    except InvalidOperation as error:
        raise ValueError(f"Invalid yuan amount: {value!r}") from error
    return int((decimal_value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def first_number(value: Any) -> Decimal | None:
    if value is None:
        return None
    text = str(value).replace(",", "")
    match = NUMBER_RE.search(text)
    return Decimal(match.group()) if match else None


def embedded_yuan_to_fen(value: Any) -> int | None:
    number = first_number(value)
    if number is None:
        return None
    return int((number * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def parse_price_quantity(value: Any) -> tuple[int | None, int | None]:
    if value is None:
        return None, None
    text = str(value).replace(",", "")
    numbers = [Decimal(item) for item in NUMBER_RE.findall(text)]
    if not numbers:
        return None, None
    price_fen = int((numbers[0] * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    quantity = int(numbers[-1]) if len(numbers) > 1 else None
    return price_fen, quantity


def parse_date(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip().replace("/", "-")
    if not text:
        return None
    if text.startswith("0000-00-00"):
        return None
    return date.fromisoformat(text[:10])


def parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip().replace("/", "-")
    if not text:
        return None
    if text.startswith("0000-00-00"):
        return None
    return datetime.fromisoformat(text)
