"""Evidence rules and metric decomposition (Phase 5)."""

from ecom_insight.attribution.decomposition import (
    PAID_AMOUNT_FACTORS,
    PAID_AMOUNT_FORMULA,
    decompose_multiplicative_change,
    decompose_paid_amount,
)
from ecom_insight.attribution.models import (
    AttributionCandidate,
    AttributionResult,
    ConfidenceBreakdown,
    EvidenceItem,
    EvidenceStatus,
    FactorContribution,
    MetricDecomposition,
)
from ecom_insight.attribution.rules import AttributionRuleEngine
from ecom_insight.attribution.runner import AttributionRunner, AttributionRunResult

__all__ = [
    "PAID_AMOUNT_FACTORS",
    "PAID_AMOUNT_FORMULA",
    "AttributionCandidate",
    "AttributionResult",
    "AttributionRuleEngine",
    "AttributionRunResult",
    "AttributionRunner",
    "ConfidenceBreakdown",
    "EvidenceItem",
    "EvidenceStatus",
    "FactorContribution",
    "MetricDecomposition",
    "decompose_multiplicative_change",
    "decompose_paid_amount",
]
