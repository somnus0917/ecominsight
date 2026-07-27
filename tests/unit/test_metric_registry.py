from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
import yaml

from ecom_insight.metrics import MetricRegistry


def test_project_registry_is_valid_and_roles_are_consistent() -> None:
    registry = MetricRegistry.load(Path("configs/metrics.yaml"))

    assert len(registry.config.metrics) >= 30
    assert registry.get("paid_amount").role == "outcome"
    assert registry.get("refund_rate_by_pay_time").role == "guardrail"
    assert registry.get("exposure_click_rate").aggregation == "ratio_of_sums"


def test_registry_publishes_to_duckdb() -> None:
    registry = MetricRegistry.load(Path("configs/metrics.yaml"))
    connection = duckdb.connect()

    registry.publish_to_duckdb(connection)

    assert connection.execute("SELECT count(*) FROM metric_registry").fetchone()[0] == len(
        registry.config.metrics
    )


def test_duplicate_metric_code_is_rejected(tmp_path: Path) -> None:
    source = yaml.safe_load(Path("configs/metrics.yaml").read_text(encoding="utf-8"))
    source["metrics"].append(dict(source["metrics"][0]))
    path = tmp_path / "metrics.yaml"
    path.write_text(yaml.safe_dump(source, allow_unicode=True), encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate metric codes"):
        MetricRegistry.load(path)
