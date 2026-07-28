from __future__ import annotations

from ecom_insight.attribution import AttributionCandidate, EvidenceScoreBreakdown


def test_candidate_accepts_legacy_confidence_payload_during_migration() -> None:
    breakdown = EvidenceScoreBreakdown(
        evidence_completeness=1,
        source_reliability=1,
        directional_consistency=1,
        temporal_alignment=1,
        contradiction_penalty=0,
    )

    candidate = AttributionCandidate(
        rule_id="R001",
        cause_code="traffic_decline",
        cause="流量下降",
        status="supported_inference",
        confidence=0.8,
        confidence_breakdown=breakdown,
        explanation="仅作为有证据支持的推断。",
    )

    assert candidate.evidence_score == 0.8
    assert candidate.confidence == 0.8
    assert candidate.model_dump()["evidence_score"] == 0.8
