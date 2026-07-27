from __future__ import annotations

from datetime import date

from ecom_insight.attribution import (
    AttributionCandidate,
    ConfidenceBreakdown,
    EvidenceItem,
)
from ecom_insight.llm import (
    DeterministicEvidenceReportGenerator,
    ReportValidator,
)
from ecom_insight.reporting import (
    AttributionReport,
    EvidenceBundle,
    ReportCause,
    ReportFact,
)


def _bundle() -> EvidenceBundle:
    evidence = EvidenceItem(
        evidence_id="event:paid_amount",
        metric="paid_amount",
        source_table="mart_shop_performance_daily",
        current_value=70,
        baseline_value=100,
        change_rate=-0.30,
        unit="CNY",
        comparison_window="previous_14_observations_median",
    )
    breakdown = ConfidenceBreakdown(
        evidence_completeness=1,
        source_reliability=1,
        directional_consistency=1,
        temporal_alignment=1,
        contradiction_penalty=0,
    )
    return EvidenceBundle(
        attribution_id="a" * 24,
        entity_type="shop",
        entity_id="Shop_A",
        date=date(2025, 1, 20),
        target_metric="paid_amount",
        detector_names=["fixed_threshold"],
        anomaly_score=3,
        severity="medium",
        decomposition=None,
        candidates=[
            AttributionCandidate(
                rule_id="R001",
                cause_code="traffic_decline",
                cause="流量下降",
                status="supported_inference",
                confidence=1,
                confidence_breakdown=breakdown,
                supporting_evidence=[evidence],
                explanation="流量与支付同向下降",
            )
        ],
        evidence=[evidence],
        missing_information=["缺少活动日历"],
        retrieved_documents=[],
        data_origin="demo",
    )


def test_deterministic_report_passes_evidence_validation() -> None:
    bundle = _bundle()
    report = DeterministicEvidenceReportGenerator().generate(bundle)
    validation = ReportValidator().validate(report=report, bundle=bundle)

    assert validation.valid
    assert validation.unsupported_claim_count == 0
    assert report.possible_causes[0].status == "supported_inference"


def test_validator_rejects_unknown_evidence_and_causal_claim() -> None:
    bundle = _bundle()
    report = AttributionReport(
        report_id="r" * 24,
        attribution_id=bundle.attribution_id,
        summary="流量下降确定导致支付下降。",
        summary_evidence_ids=["unknown:evidence"],
        confirmed_facts=[
            ReportFact(
                fact="支付下降",
                evidence_ids=["unknown:evidence"],
                source="unknown",
                confidence=1,
            )
        ],
        possible_causes=[
            ReportCause(
                cause="流量下降是唯一原因",
                evidence_ids=[],
                confidence=1,
                status="supported_inference",
            )
        ],
        missing_information=[],
        recommended_checks=[],
        retrieved_documents=[],
        generator="bad-test",
    )

    validation = ReportValidator().validate(report=report, bundle=bundle)

    assert not validation.valid
    assert validation.unsupported_claim_count > 0
    assert "唯一原因" in validation.prohibited_causal_phrases

