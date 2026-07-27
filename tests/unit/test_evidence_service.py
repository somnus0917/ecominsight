from __future__ import annotations

from pathlib import Path

import pytest

from ecom_insight.reporting.evidence import ATTRIBUTION_ID_PATTERN


@pytest.mark.parametrize(
    "value",
    [
        "abc",
        "a" * 23,
        "a" * 25,
        "' OR 1=1 --",
        str(Path("../../secret")),
    ],
)
def test_attribution_id_contract_rejects_non_hash_ids(value: str) -> None:
    assert ATTRIBUTION_ID_PATTERN.fullmatch(value) is None

