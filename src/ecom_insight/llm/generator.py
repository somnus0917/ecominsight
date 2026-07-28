from __future__ import annotations

import hashlib
from typing import Protocol

from ecom_insight.llm.models import StructuredLLMClient
from ecom_insight.llm.validation import ReportValidator
from ecom_insight.reporting.models import (
    AttributionReport,
    EvidenceBundle,
    ReportCause,
    ReportCauseStatus,
    ReportDocumentReference,
    ReportFact,
    ReportValidation,
)


class EvidenceReportGenerator(Protocol):
    @property
    def generator_name(self) -> str: ...

    def generate(self, bundle: EvidenceBundle) -> AttributionReport: ...


def _format_change(change_rate: float | None) -> str:
    if change_rate is None:
        return "无法计算相对变化"
    direction = "上升" if change_rate >= 0 else "下降"
    return f"{direction}{abs(change_rate):.1%}"


class DeterministicEvidenceReportGenerator:
    """Default report path: local, deterministic and evidence-reference complete."""

    @property
    def generator_name(self) -> str:
        return "deterministic_evidence_template_v1"

    def generate(self, bundle: EvidenceBundle) -> AttributionReport:
        evidence_by_metric = {item.metric: item for item in bundle.evidence}
        target = evidence_by_metric.get(bundle.target_metric)
        if target is None and bundle.evidence:
            target = bundle.evidence[0]
        if target is None:
            raise ValueError("Evidence bundle contains no confirmed fact")
        summary = (
            f"{bundle.entity_id} 在 {bundle.date.isoformat()} 的 "
            f"{bundle.target_metric} 相对基线{_format_change(target.change_rate)}。"
        )
        ranked_evidence = sorted(
            bundle.evidence,
            key=lambda item: (
                -abs(item.change_rate) if item.change_rate is not None else 0,
                item.metric,
            ),
        )
        facts = [
            ReportFact(
                fact=(
                    f"{item.metric} 当前值为 {item.current_value}, "
                    f"相对 {item.comparison_window} {_format_change(item.change_rate)}。"
                ),
                evidence_ids=[item.evidence_id],
                source=item.source_table,
                evidence_score=1.0,
            )
            for item in ranked_evidence[:5]
        ]
        retrieved_by_cause: dict[str, list[str]] = {}
        for hit in bundle.retrieved_documents:
            if hit.document.cause_code is not None:
                retrieved_by_cause.setdefault(hit.document.cause_code, []).append(
                    hit.document.document_id
                )
        causes: list[ReportCause] = []
        for candidate in bundle.candidates[:3]:
            cause_status: ReportCauseStatus = (
                "supported_inference" if candidate.status == "confirmed_fact" else candidate.status
            )
            causes.append(
                ReportCause(
                    cause=(
                        f"{candidate.cause}是有数据支持的候选解释, 但当前证据只支持统计关联."
                        if cause_status == "supported_inference"
                        else candidate.cause
                    ),
                    evidence_ids=[item.evidence_id for item in candidate.supporting_evidence],
                    historical_document_ids=retrieved_by_cause.get(candidate.cause_code, []),
                    evidence_score=candidate.evidence_score,
                    status=cause_status,
                )
            )
        recommended = list(
            dict.fromkeys(
                [
                    *bundle.missing_information,
                    "结合活动日历和运营变更记录进行人工复核。",
                ]
            )
        )
        report_id = hashlib.sha256(
            f"{bundle.attribution_id}|{self.generator_name}".encode()
        ).hexdigest()[:24]
        return AttributionReport(
            report_id=report_id,
            attribution_id=bundle.attribution_id,
            summary=summary,
            summary_evidence_ids=[target.evidence_id],
            confirmed_facts=facts,
            possible_causes=causes,
            missing_information=bundle.missing_information,
            recommended_checks=recommended,
            retrieved_documents=[
                ReportDocumentReference(
                    document_id=hit.document.document_id,
                    document_type=hit.document.document_type,
                    title=hit.document.title,
                    score=hit.score,
                )
                for hit in bundle.retrieved_documents
            ],
            generator=self.generator_name,
        )


class StructuredLLMReportGenerator:
    """Optional injected LLM path; external enablement is enforced by the caller."""

    SYSTEM_PROMPT = (
        "你只能组织已提供的证据。每个事实和推断必须引用有效 evidence_id。"
        "不得计算新指标, 不得把相关性写成确定因果, 不得补写缺失信息。"
    )

    def __init__(self, client: StructuredLLMClient) -> None:
        self.client = client

    @property
    def generator_name(self) -> str:
        return f"structured_llm:{self.client.model_name}"

    def generate(self, bundle: EvidenceBundle) -> AttributionReport:
        payload = bundle.model_dump(mode="json")
        result = self.client.generate_structured(
            system_prompt=self.SYSTEM_PROMPT,
            payload=payload,
            json_schema=AttributionReport.model_json_schema(),
        )
        report = AttributionReport.model_validate(result)
        return report.model_copy(update={"generator": self.generator_name})


def generate_and_validate(
    *,
    generator: EvidenceReportGenerator,
    validator: ReportValidator,
    bundle: EvidenceBundle,
) -> tuple[AttributionReport, ReportValidation]:
    report = generator.generate(bundle)
    validation = validator.validate(report=report, bundle=bundle)
    if not validation.valid:
        raise ValueError(f"Generated report failed validation: {validation.errors}")
    return report, validation
