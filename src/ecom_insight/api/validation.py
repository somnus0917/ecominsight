"""Guards that prevent a database from being presented under the wrong mode."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import duckdb


def _table_exists(connection: duckdb.DuckDBPyConnection, table: str) -> bool:
    row = connection.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [table]
    ).fetchone()
    return bool(row and row[0])


def validate_database_data_mode(
    database_path: Path, expected_mode: Literal["real", "demo"]
) -> None:
    """Raise when warehouse lineage contradicts the API configuration."""
    if not database_path.is_file():
        raise ValueError(f"Analytics database does not exist: {database_path}")
    with duckdb.connect(str(database_path), read_only=True) as connection:
        if not _table_exists(connection, "fact_shop_daily"):
            if expected_mode == "demo":
                raise ValueError("Database mode cannot be validated: missing fact_shop_daily")
            return
        columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info('fact_shop_daily')").fetchall()
        }
        if "synthetic" in columns:
            counts = connection.execute(
                "SELECT count(*), count(*) FILTER (WHERE synthetic) FROM fact_shop_daily"
            ).fetchone()
            if counts is None:
                raise ValueError("Database mode cannot be validated: empty fact_shop_daily query")
            total, synthetic_count = counts
            is_demo = int(total) > 0 and int(total) == int(synthetic_count)
        else:
            is_demo = False
        for table in ("fact_anomaly", "fact_attribution"):
            if _table_exists(connection, table):
                origins = {
                    str(row[0])
                    for row in connection.execute(
                        f"SELECT DISTINCT data_origin FROM {table}"
                    ).fetchall()
                }
                if expected_mode == "demo" and origins and origins != {"demo"}:
                    raise ValueError(f"Database mode mismatch: {table} contains {sorted(origins)}")
                if expected_mode == "real" and "demo" in origins:
                    raise ValueError(f"Database mode mismatch: {table} contains demo records")
        if expected_mode == "demo" and not is_demo:
            raise ValueError(
                "Database mode mismatch: demo mode requires fully synthetic fact_shop_daily"
            )
        if expected_mode == "real" and is_demo:
            raise ValueError(
                "Database mode mismatch: real mode cannot use a fully synthetic warehouse"
            )
