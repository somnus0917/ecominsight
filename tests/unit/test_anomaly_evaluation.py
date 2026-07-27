from __future__ import annotations

from pathlib import Path

from ecom_insight.anomaly import FixedThresholdDetector, RollingMADDetector
from ecom_insight.evaluation import AnomalyEvaluator


def test_anomaly_evaluation_uses_controlled_labels(tmp_path: Path) -> None:
    result = AnomalyEvaluator(
        demo_root=Path("data/demo/generated"),
        artifact_root=tmp_path,
        detectors=(FixedThresholdDetector(), RollingMADDetector()),
    ).run()

    assert result.case_count == 10
    assert len(result.detector_results) == 2
    for detector in result.detector_results:
        assert 0 <= detector.precision <= 1
        assert 0 <= detector.recall <= 1
        assert 0 <= detector.f1 <= 1
        assert detector.eligible_points > detector.positive_points
        assert detector.scenario_count == 10
    assert result.artifact_path.is_file()
    assert result.predictions_path.is_file()
