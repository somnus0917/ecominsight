from __future__ import annotations

import duckdb

from ecom_insight.warehouse.builder import WarehouseBuilder


def test_curated_fact_converts_fen_to_decimal_yuan() -> None:
    connection = duckdb.connect()
    connection.execute("CREATE TABLE stg_test (entity VARCHAR, paid_amount_fen BIGINT)")
    connection.execute("INSERT INTO stg_test VALUES ('synthetic', 12345), ('null', NULL)")

    WarehouseBuilder._create_curated_fact(connection, "stg_test", "fact_test")
    rows = connection.execute(
        "SELECT entity, paid_amount, typeof(paid_amount) FROM fact_test ORDER BY entity"
    ).fetchall()

    assert str(rows[1][1]) == "123.45"
    assert rows[1][2] == "DECIMAL(18,2)"
    assert rows[0][1] is None
