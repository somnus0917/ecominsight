from __future__ import annotations

from pathlib import Path

from ecom_insight.evaluation import AttributionEvaluator


def test_attribution_evaluation_recovers_controlled_rules(tmp_path: Path) -> None:
    demo_root = Path("data/demo/generated")
    result = AttributionEvaluator(
        demo_root=demo_root,
        artifact_root=tmp_path,
    ).run()

    assert result.summary.case_count == 10
    assert result.summary.rule_candidate_recall >= 0.8
    assert result.summary.unsupported_claim_rate == 0
    assert result.summary.hallucination_rate == 0
    assert result.artifact_path.is_file()
    assert result.predictions_path.is_file()

