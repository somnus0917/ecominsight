from __future__ import annotations

from collections.abc import Mapping, Sequence

from ecom_insight.attribution.models import (
    AttributionCandidate,
    ConfidenceBreakdown,
    EvidenceItem,
)

DECLINE_THRESHOLD = -0.15
INCREASE_THRESHOLD = 0.15
STABLE_THRESHOLD = 0.12


def _available(
    evidence: Mapping[str, EvidenceItem], metrics: Sequence[str]
) -> list[EvidenceItem]:
    return [evidence[metric] for metric in metrics if metric in evidence]


def _declined(item: EvidenceItem | None, threshold: float = DECLINE_THRESHOLD) -> bool:
    return item is not None and item.change_rate is not None and item.change_rate <= threshold


def _increased(item: EvidenceItem | None, threshold: float = INCREASE_THRESHOLD) -> bool:
    return item is not None and item.change_rate is not None and item.change_rate >= threshold


def _stable(item: EvidenceItem | None, threshold: float = STABLE_THRESHOLD) -> bool:
    return item is not None and item.change_rate is not None and abs(item.change_rate) <= threshold


class AttributionRuleEngine:
    """Deterministic evidence rules; candidates are inferences, never causal facts."""

    def evaluate(
        self,
        *,
        target_metric: str,
        evidence: Mapping[str, EvidenceItem],
    ) -> list[AttributionCandidate]:
        candidates = [
            candidate
            for candidate in (
                self._traffic_decline(target_metric, evidence),
                self._click_efficiency_decline(target_metric, evidence),
                self._conversion_decline(target_metric, evidence),
                self._aov_decline(target_metric, evidence),
                self._refund_pressure(target_metric, evidence),
                self._ad_inefficiency(target_metric, evidence),
                self._inventory_shortage(target_metric, evidence),
                self._commission_pressure(target_metric, evidence),
                self._settlement_adjustment(target_metric, evidence),
                self._overstock(target_metric, evidence),
            )
            if candidate is not None
        ]
        return sorted(candidates, key=lambda candidate: candidate.confidence, reverse=True)

    @staticmethod
    def _candidate(
        *,
        rule_id: str,
        cause_code: str,
        cause: str,
        support: list[EvidenceItem],
        counter: list[EvidenceItem],
        required_count: int,
        explanation: str,
        missing: list[str] | None = None,
        source_reliability: float = 1.0,
    ) -> AttributionCandidate:
        completeness = min(len(support) / required_count, 1.0)
        consistency = len(support) / (len(support) + len(counter)) if support else 0.0
        breakdown = ConfidenceBreakdown(
            evidence_completeness=completeness,
            source_reliability=source_reliability,
            directional_consistency=consistency,
            temporal_alignment=1.0,
            contradiction_penalty=min(len(counter) * 0.15, 0.6),
        )
        return AttributionCandidate(
            rule_id=rule_id,
            cause_code=cause_code,
            cause=cause,
            status="supported_inference",
            confidence=breakdown.score,
            confidence_breakdown=breakdown,
            supporting_evidence=support,
            counter_evidence=counter,
            missing_information=missing or [],
            explanation=explanation,
        )

    def _traffic_decline(
        self, target: str, evidence: Mapping[str, EvidenceItem]
    ) -> AttributionCandidate | None:
        paid = evidence.get("paid_amount")
        exposure = evidence.get("exposure_users")
        if target not in {"paid_amount", "exposure_users"} or not _declined(exposure):
            return None
        if target == "paid_amount" and not _declined(paid):
            return None
        rates = [
            evidence.get("exposure_click_rate"),
            evidence.get("click_conversion_rate"),
        ]
        support = _available(evidence, ["paid_amount", "exposure_users"])
        for item in rates:
            if item is not None and _stable(item):
                support.append(item)
        natural_search = evidence.get("natural_search_exposure")
        if natural_search is not None and _declined(natural_search):
            support.append(natural_search)
        search_rank = evidence.get("search_rank")
        if search_rank is not None and _increased(search_rank):
            support.append(search_rank)
        counter = [item for item in rates if item is not None and _declined(item)]
        return self._candidate(
            rule_id="R001",
            cause_code="traffic_decline",
            cause="流量下降",
            support=support,
            counter=counter,
            required_count=3,
            explanation="支付或曝光下降与流量指标同向, 转化效率未出现更强的反向证据.",
        )

    def _click_efficiency_decline(
        self, target: str, evidence: Mapping[str, EvidenceItem]
    ) -> AttributionCandidate | None:
        ctr = evidence.get("exposure_click_rate")
        paid = evidence.get("paid_amount")
        if target not in {"paid_amount", "exposure_click_rate"} or not _declined(ctr):
            return None
        if target == "paid_amount" and not _declined(paid):
            return None
        support = _available(evidence, ["exposure_click_rate"])
        if paid is not None and _declined(paid):
            support.append(paid)
        click_users = evidence.get("click_users")
        if click_users is not None and _declined(click_users):
            support.append(click_users)
        product_paid = evidence.get("captured_product_paid_amount")
        if product_paid is not None and _declined(product_paid):
            support.append(product_paid)
        exposure = evidence.get("exposure_users")
        if exposure is not None and _stable(exposure):
            support.append(exposure)
        counter = [exposure] if exposure is not None and _declined(exposure) else []
        return self._candidate(
            rule_id="R002",
            cause_code="click_efficiency_decline",
            cause="点击效率下降",
            support=support,
            counter=counter,
            required_count=2,
            explanation="曝光到点击率明显下降, 且支付变化方向一致.",
        )

    def _conversion_decline(
        self, target: str, evidence: Mapping[str, EvidenceItem]
    ) -> AttributionCandidate | None:
        conversion = evidence.get("click_conversion_rate")
        paid = evidence.get("paid_amount")
        if target not in {"paid_amount", "click_conversion_rate"} or not _declined(conversion):
            return None
        if target == "paid_amount" and not _declined(paid):
            return None
        support = _available(evidence, ["click_conversion_rate"])
        if paid is not None and _declined(paid):
            support.append(paid)
        paid_users = evidence.get("paid_users")
        if paid_users is not None and _declined(paid_users):
            support.append(paid_users)
        product_paid = evidence.get("captured_product_paid_amount")
        if product_paid is not None and _declined(product_paid):
            support.append(product_paid)
        ctr = evidence.get("exposure_click_rate")
        if ctr is not None and _stable(ctr):
            support.append(ctr)
        counter = [ctr] if ctr is not None and _declined(ctr) else []
        return self._candidate(
            rule_id="R003",
            cause_code="conversion_decline",
            cause="成交转化效率下降",
            support=support,
            counter=counter,
            required_count=2,
            explanation="点击到成交率明显下降, 支付变化方向一致.",
            missing=["库存不足是否参与转化下降, 需可靠商品-SKU桥接后验证."],
        )

    def _aov_decline(
        self, target: str, evidence: Mapping[str, EvidenceItem]
    ) -> AttributionCandidate | None:
        aov = evidence.get("avg_order_value")
        paid = evidence.get("paid_amount")
        if target not in {"paid_amount", "avg_order_value"} or not _declined(aov):
            return None
        if target == "paid_amount" and not _declined(paid):
            return None
        support = _available(evidence, ["avg_order_value"])
        if paid is not None and _declined(paid):
            support.append(paid)
        conversion = evidence.get("click_conversion_rate")
        if conversion is not None and _stable(conversion):
            support.append(conversion)
        avg_item_price = evidence.get("avg_item_price")
        if avg_item_price is not None and _declined(avg_item_price):
            support.append(avg_item_price)
        counter = [conversion] if conversion is not None and _declined(conversion) else []
        return self._candidate(
            rule_id="R004",
            cause_code="aov_decline",
            cause="客单价下降",
            support=support,
            counter=counter,
            required_count=2,
            explanation="客单价明显下降, 且支付变化方向一致.",
        )

    def _refund_pressure(
        self, target: str, evidence: Mapping[str, EvidenceItem]
    ) -> AttributionCandidate | None:
        refund = evidence.get("refund_rate")
        refund = refund or evidence.get("refund_rate_by_pay_time")
        if target not in {"refund_rate", "refund_rate_by_pay_time", "paid_amount"} or not _increased(
            refund, 0.20
        ):
            return None
        support = _available(evidence, ["refund_rate", "refund_rate_by_pay_time"])
        refund_amount = evidence.get("refund_amount")
        if refund_amount is not None and _increased(refund_amount):
            support.append(refund_amount)
        net_paid = evidence.get("net_paid_amount")
        if net_paid is not None and _declined(net_paid):
            support.append(net_paid)
        paid = evidence.get("paid_amount")
        if target == "paid_amount" and not _declined(paid):
            return None
        if paid is not None and _declined(paid):
            support.append(paid)
        return self._candidate(
            rule_id="R005",
            cause_code="refund_pressure",
            cause="退款压力上升",
            support=support,
            counter=[],
            required_count=2,
            explanation="退款率明显上升, 并伴随净支付或支付金额走弱.",
        )

    def _ad_inefficiency(
        self, target: str, evidence: Mapping[str, EvidenceItem]
    ) -> AttributionCandidate | None:
        ad_spend = evidence.get("ad_spend")
        roas = evidence.get("roas")
        if target not in {"ad_spend", "paid_amount"}:
            return None
        if not _increased(ad_spend, 0.20) or not _declined(roas):
            return None
        support = _available(evidence, ["ad_spend", "roas"])
        paid = evidence.get("paid_amount")
        if target == "paid_amount" and not (
            _stable(paid) or _declined(paid, -STABLE_THRESHOLD)
        ):
            return None
        if paid is not None and (
            _stable(paid) or _declined(paid, -STABLE_THRESHOLD)
        ):
            support.append(paid)
        return self._candidate(
            rule_id="R006",
            cause_code="ad_inefficiency",
            cause="投放效率下降",
            support=support,
            counter=[],
            required_count=3,
            explanation="广告消耗上升但ROAS下降, 支付金额未同比例增长.",
        )

    def _inventory_shortage(
        self, target: str, evidence: Mapping[str, EvidenceItem]
    ) -> AttributionCandidate | None:
        available = evidence.get("available_qty")
        if target not in {"available_qty", "click_conversion_rate", "paid_amount"}:
            return None
        if not _declined(available, -0.50):
            return None
        product_paid = evidence.get("core_product_paid_amount")
        conversion = evidence.get("click_conversion_rate")
        if not (_declined(product_paid) or _declined(conversion)):
            return None
        paid = evidence.get("paid_amount")
        if target == "paid_amount" and not _declined(paid):
            return None
        support = _available(evidence, ["available_qty"])
        support.extend(
            item
            for item in (product_paid, conversion)
            if item is not None and _declined(item)
        )
        return self._candidate(
            rule_id="R007",
            cause_code="inventory_shortage",
            cause="主销规格库存不足",
            support=support,
            counter=[],
            required_count=2,
            explanation="主销规格可用库存显著下降, 并与商品支付或店铺转化同步走弱.",
        )

    def _commission_pressure(
        self, target: str, evidence: Mapping[str, EvidenceItem]
    ) -> AttributionCandidate | None:
        commission_rate = evidence.get("platform_commission_rate")
        settlement_ratio = evidence.get("settlement_ratio")
        if target not in {"platform_commission_rate", "settlement_ratio"}:
            return None
        if not _increased(commission_rate, 0.20):
            return None
        support = _available(evidence, ["platform_commission_rate"])
        if settlement_ratio is not None and _declined(settlement_ratio, -0.08):
            support.append(settlement_ratio)
        return self._candidate(
            rule_id="R008",
            cause_code="commission_pressure",
            cause="平台佣金率上升",
            support=support,
            counter=[],
            required_count=2,
            explanation="平台佣金率显著上升, 并对结算比例形成压力.",
        )

    def _settlement_adjustment(
        self, target: str, evidence: Mapping[str, EvidenceItem]
    ) -> AttributionCandidate | None:
        ratio = evidence.get("settlement_ratio")
        amount = evidence.get("settlement_amount_by_pay_time")
        adjustment = evidence.get("settlement_adjustment")
        target_declined = _declined(ratio) or _declined(amount)
        if target not in {
            "settlement_ratio",
            "settlement_amount_by_pay_time",
        } or not target_declined:
            return None
        support = [
            item for item in (ratio, amount) if item is not None and _declined(item)
        ]
        if adjustment is not None and _declined(adjustment):
            support.append(adjustment)
        paid = evidence.get("paid_amount")
        if paid is not None and _stable(paid):
            support.append(paid)
        missing = []
        if adjustment is None:
            missing.append("当前店铺日报与结算流水不能可靠关联, 无法验证结算调整项.")
        return self._candidate(
            rule_id="R009",
            cause_code="settlement_adjustment_decline",
            cause="结算侧调整或费用变化",
            support=support,
            counter=[],
            required_count=3,
            explanation="结算比例或结算金额下降, 支付相对稳定时应优先核查结算侧调整.",
            missing=missing,
            source_reliability=0.85 if missing else 1.0,
        )

    def _overstock(
        self, target: str, evidence: Mapping[str, EvidenceItem]
    ) -> AttributionCandidate | None:
        days = evidence.get("days_of_supply")
        if target not in {"days_of_supply", "available_qty"} or not _increased(days, 0.50):
            return None
        available = evidence.get("available_qty")
        sales = evidence.get("sales_7d")
        support = _available(evidence, ["days_of_supply"])
        support.extend(
            item
            for item in (available, sales)
            if item is not None and (_increased(item) or _declined(item))
        )
        return self._candidate(
            rule_id="R010",
            cause_code="overstock",
            cause="高库存低动销",
            support=support,
            counter=[],
            required_count=2,
            explanation="预计可售天数显著增加, 并伴随库存增加或近7日销量下降.",
        )
