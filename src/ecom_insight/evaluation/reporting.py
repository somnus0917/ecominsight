from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

import structlog
from pydantic import BaseModel, ConfigDict

from ecom_insight.attribution import (
    AttributionCandidate,
    AttributionRuleEngine,
    EvidenceItem,
)
from ecom_insight.evaluation.attribution import (
    EXPECTED_RULES,
    DemoAttributionEvidenceLoader,
    _load_json_records,
)
from ecom_insight.llm import (
    DeterministicEvidenceReportGenerator,
    ReportValidator,
)
from ecom_insight.reporting import AttributionReport, EvidenceBundle
from ecom_insight.retrieval import (
    DuckDBKnowledgeRepository,
    KnowledgeIndex,
    RetrievalFilters,
    RetrievalHit,
)

LOGGER = structlog.get_logger(__name__)


class ReportingEvaluationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RetrievalEvaluationSummary(ReportingEvaluationModel):
    query_count: int
    rule_hit_at_1: float
    rule_hit_at_3: float
    case_self_hit_at_1: float
    case_self_hit_at_3: float
    case_generalization_status: Literal["insufficient_data"]
    case_generalization_reason: str


class ReportingVariantResult(ReportingEvaluationModel):
    variant: str
    status: Literal["completed", "not_run"]
    report_count: int | None
    claim_count: int | None
    unsupported_claim_count: int | None
    unsupported_claim_rate: float | None
    evidence_coverage: float | None
    historical_reference_rate: float | None
    reason: str | None = None


class ReportingEvaluationSummary(ReportingEvaluationModel):
    retrieval: RetrievalEvaluationSummary
    variants: list[ReportingVariantResult]


@dataclass(frozen=True, slots=True)
class ReportingEvaluationResult:
    artifact_path: Path
    summary: ReportingEvaluationSummary


def _safe_divide(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


class ReportingEvaluator:
    def __init__(
        self,
        *,
        database_path: Path,
        demo_root: Path,
        artifact_root: Path,
    ) -> None:
        self.database_path = database_path.resolve()
        self.demo_root = demo_root.resolve()
        self.artifact_root = artifact_root.resolve()
        self.rule_engine = AttributionRuleEngine()
        self.generator = DeterministicEvidenceReportGenerator()
        self.validator = ReportValidator()

    def run(self) -> ReportingEvaluationResult:
        labels = _load_json_records(self.demo_root / "anomaly_labels.json")
        evidence_loader = DemoAttributionEvidenceLoader(self.demo_root)
        index = DuckDBKnowledgeRepository(database_path=self.database_path).load()
        retrieval = self._evaluate_retrieval(labels, index)

        rules_only_claims = 0
        rules_only_unsupported = 0
        sql_reports = sql_claims = sql_unsupported = sql_expected = sql_cited = 0
        rag_reports = rag_claims = rag_unsupported = rag_expected = rag_cited = 0
        rag_historical_references = 0
        for label in labels:
            evidence = evidence_loader.build(label)
            candidates = self.rule_engine.evaluate(
                target_metric=str(label["target_metric"]),
                evidence=evidence,
            )
            if candidates:
                rules_only_claims += 1
                rules_only_unsupported += 1
            expected_evidence_ids = {
                f"demo:{metric}" for metric in label["expected_evidence"]
            }
            base_bundle = self._bundle(
                label=label,
                candidates=candidates,
                evidence=list(evidence.values()),
                retrieved_documents=[],
            )
            sql_report = self.generator.generate(base_bundle)
            sql_validation = self.validator.validate(
                report=sql_report,
                bundle=base_bundle,
            )
            sql_reports += 1
            sql_claims += sql_validation.claim_count
            sql_unsupported += sql_validation.unsupported_claim_count
            sql_expected += len(expected_evidence_ids)
            sql_cited += len(
                expected_evidence_ids.intersection(
                    self._report_evidence_ids(sql_report)
                )
            )

            query = self._query_for_label(label)
            excluded = {
                document.document_id
                for document in index.documents
                if document.document_type == "historical_case"
                and document.shop_id == str(label["entity_id"])
                and document.start_date == str(label["start_date"])
                and document.anomaly_metric == str(label["target_metric"])
            }
            hits = index.search(
                query,
                limit=5,
                filters=RetrievalFilters(
                    document_types={
                        "historical_case",
                        "attribution_rule",
                        "metric_definition",
                    },
                    exclude_document_ids=excluded,
                ),
                minimum_score=0.01,
            )
            rag_bundle = self._bundle(
                label=label,
                candidates=candidates,
                evidence=list(evidence.values()),
                retrieved_documents=hits,
            )
            rag_report = self.generator.generate(rag_bundle)
            rag_validation = self.validator.validate(
                report=rag_report,
                bundle=rag_bundle,
            )
            rag_reports += 1
            rag_claims += rag_validation.claim_count
            rag_unsupported += rag_validation.unsupported_claim_count
            rag_expected += len(expected_evidence_ids)
            rag_cited += len(
                expected_evidence_ids.intersection(
                    self._report_evidence_ids(rag_report)
                )
            )
            if any(
                reference.document_type == "historical_case"
                for reference in rag_report.retrieved_documents
            ):
                rag_historical_references += 1

        variants = [
            ReportingVariantResult(
                variant="direct_llm",
                status="not_run",
                report_count=None,
                claim_count=None,
                unsupported_claim_count=None,
                unsupported_claim_rate=None,
                evidence_coverage=None,
                historical_reference_rate=None,
                reason="外部API默认关闭, 且未配置本地生成模型; 不生成虚构基线.",
            ),
            ReportingVariantResult(
                variant="rules_only",
                status="completed",
                report_count=len(labels),
                claim_count=rules_only_claims,
                unsupported_claim_count=rules_only_unsupported,
                unsupported_claim_rate=_safe_divide(
                    rules_only_unsupported, rules_only_claims
                ),
                evidence_coverage=0.0,
                historical_reference_rate=0.0,
            ),
            ReportingVariantResult(
                variant="rules_sql",
                status="completed",
                report_count=sql_reports,
                claim_count=sql_claims,
                unsupported_claim_count=sql_unsupported,
                unsupported_claim_rate=_safe_divide(sql_unsupported, sql_claims),
                evidence_coverage=_safe_divide(sql_cited, sql_expected),
                historical_reference_rate=0.0,
            ),
            ReportingVariantResult(
                variant="rules_sql_rag",
                status="completed",
                report_count=rag_reports,
                claim_count=rag_claims,
                unsupported_claim_count=rag_unsupported,
                unsupported_claim_rate=_safe_divide(rag_unsupported, rag_claims),
                evidence_coverage=_safe_divide(rag_cited, rag_expected),
                historical_reference_rate=_safe_divide(
                    rag_historical_references, rag_reports
                ),
            ),
        ]
        summary = ReportingEvaluationSummary(
            retrieval=retrieval,
            variants=variants,
        )
        payload = {
            "schema_version": "1",
            "data_origin": "demo",
            "summary": summary.model_dump(mode="json"),
            "limitations": [
                "规则和报告评测使用公开受控场景, 不代表真实生产准确率.",
                "rules_only基线故意不附evidence_id, 用于验证引用约束的增益.",
                "当前每个原因标签只有一个历史案例, 无法进行同标签留一泛化评测.",
                "direct_llm在未配置本地或外部模型时保持not_run。",
            ],
        }
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        artifact_path = self.artifact_root / "reporting_evaluation.json"
        artifact_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        LOGGER.info(
            "phase6_reporting_evaluation_complete",
            retrieval=retrieval.model_dump(mode="json"),
            variants=[variant.model_dump(mode="json") for variant in variants],
        )
        return ReportingEvaluationResult(
            artifact_path=artifact_path,
            summary=summary,
        )

    def _evaluate_retrieval(
        self,
        labels: list[dict[str, Any]],
        index: KnowledgeIndex,
    ) -> RetrievalEvaluationSummary:
        rule_hit_1 = rule_hit_3 = case_hit_1 = case_hit_3 = 0
        for label in labels:
            query = self._query_for_label(label)
            expected_rule_id = EXPECTED_RULES[str(label["scenario_type"])]
            expected_rule_document = f"rule:{expected_rule_id}"
            rule_hits = index.search(
                query,
                limit=3,
                filters=RetrievalFilters(document_types={"attribution_rule"}),
            )
            rule_ids = [hit.document.document_id for hit in rule_hits]
            rule_hit_1 += int(bool(rule_ids) and rule_ids[0] == expected_rule_document)
            rule_hit_3 += int(expected_rule_document in rule_ids)

            expected_cases = {
                document.document_id
                for document in index.documents
                if document.document_type == "historical_case"
                and document.shop_id == str(label["entity_id"])
                and document.start_date == str(label["start_date"])
                and document.anomaly_metric == str(label["target_metric"])
            }
            case_hits = index.search(
                query,
                limit=3,
                filters=RetrievalFilters(document_types={"historical_case"}),
            )
            case_ids = [hit.document.document_id for hit in case_hits]
            case_hit_1 += int(
                bool(case_ids) and case_ids[0] in expected_cases
            )
            case_hit_3 += int(bool(expected_cases.intersection(case_ids)))
        count = len(labels)
        return RetrievalEvaluationSummary(
            query_count=count,
            rule_hit_at_1=_safe_divide(rule_hit_1, count),
            rule_hit_at_3=_safe_divide(rule_hit_3, count),
            case_self_hit_at_1=_safe_divide(case_hit_1, count),
            case_self_hit_at_3=_safe_divide(case_hit_3, count),
            case_generalization_status="insufficient_data",
            case_generalization_reason=(
                "每个cause_code当前仅有一个案例, 留一后没有同标签正例."
            ),
        )

    @staticmethod
    def _query_for_label(label: dict[str, Any]) -> str:
        evidence = " ".join(str(item) for item in label["expected_evidence"])
        return (
            f"异常指标 {label['target_metric']} "
            f"变化方向 {label['expected_direction']} 证据 {evidence}"
        )

    @staticmethod
    def _bundle(
        *,
        label: dict[str, Any],
        candidates: list[AttributionCandidate],
        evidence: list[EvidenceItem],
        retrieved_documents: list[RetrievalHit],
    ) -> EvidenceBundle:
        attribution_id = hashlib.sha256(
            f"evaluation|{label['scenario_id']}".encode()
        ).hexdigest()[:24]
        return EvidenceBundle(
            attribution_id=attribution_id,
            entity_type=str(label["entity_type"]),
            entity_id=str(label["entity_id"]),
            date=date.fromisoformat(str(label["start_date"])),
            target_metric=str(label["target_metric"]),
            detector_names=["controlled_label"],
            anomaly_score=1,
            severity="high",
            decomposition=None,
            candidates=candidates,
            evidence=evidence,
            missing_information=[],
            retrieved_documents=retrieved_documents,
            data_origin="demo",
        )

    @staticmethod
    def _report_evidence_ids(report: AttributionReport) -> set[str]:
        return {
            *report.summary_evidence_ids,
            *(
                evidence_id
                for fact in report.confirmed_facts
                for evidence_id in fact.evidence_ids
            ),
            *(
                evidence_id
                for cause in report.possible_causes
                for evidence_id in cause.evidence_ids
            ),
        }
