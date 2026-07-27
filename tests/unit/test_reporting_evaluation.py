from __future__ import annotations

from pathlib import Path

import duckdb

from ecom_insight.evaluation import ReportingEvaluator
from ecom_insight.retrieval import KnowledgeBuilder


def test_reporting_evaluation_measures_retrieval_and_claim_constraints(
    tmp_path: Path,
) -> None:
    database = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(database)):
        pass
    KnowledgeBuilder(
        database_path=database,
        metric_config_path=Path("configs/metrics.yaml"),
        rule_config_path=Path("configs/attribution_rules.yaml"),
        demo_root=Path("data/demo/generated"),
        artifact_root=tmp_path / "artifacts",
    ).run()

    result = ReportingEvaluator(
        database_path=database,
        demo_root=Path("data/demo/generated"),
        artifact_root=tmp_path / "artifacts",
    ).run()

    variants = {item.variant: item for item in result.summary.variants}
    assert result.summary.retrieval.query_count == 10
    assert result.summary.retrieval.rule_hit_at_3 >= 0.8
    assert variants["direct_llm"].status == "not_run"
    assert variants["rules_only"].unsupported_claim_rate == 1.0
    assert variants["rules_sql"].unsupported_claim_rate == 0
    assert variants["rules_sql_rag"].evidence_coverage >= 0.9
