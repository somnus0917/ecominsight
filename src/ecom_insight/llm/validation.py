from __future__ import annotations

from ecom_insight.reporting.models import (
    AttributionReport,
    EvidenceBundle,
    ReportValidation,
)

PROHIBITED_CAUSAL_PHRASES = (
    "确定导致",
    "必然导致",
    "已经证明",
    "唯一原因",
    "确定原因是",
)


class ReportValidator:
    def validate(
        self,
        *,
        report: AttributionReport,
        bundle: EvidenceBundle,
    ) -> ReportValidation:
        allowed_evidence = {item.evidence_id for item in bundle.evidence}
        allowed_documents = {
            hit.document.document_id for hit in bundle.retrieved_documents
        }
        evidence_references = [
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
        ]
        document_references = [
            *(
                reference.document_id
                for reference in report.retrieved_documents
            ),
            *(
                document_id
                for cause in report.possible_causes
                for document_id in cause.historical_document_ids
            ),
        ]
        invalid_evidence = sorted(set(evidence_references) - allowed_evidence)
        invalid_documents = sorted(set(document_references) - allowed_documents)
        report_text = " ".join(
            [
                report.summary,
                *(fact.fact for fact in report.confirmed_facts),
                *(cause.cause for cause in report.possible_causes),
            ]
        )
        prohibited = [
            phrase for phrase in PROHIBITED_CAUSAL_PHRASES if phrase in report_text
        ]
        claim_count = 1 + len(report.confirmed_facts) + len(report.possible_causes)
        unsupported = len(invalid_evidence) + len(invalid_documents)
        unsupported += sum(
            1
            for cause in report.possible_causes
            if cause.status == "supported_inference" and not cause.evidence_ids
        )
        errors: list[str] = []
        if invalid_evidence:
            errors.append("报告引用了证据包之外的 evidence_id。")
        if invalid_documents:
            errors.append("报告引用了检索结果之外的 document_id。")
        if prohibited:
            errors.append("报告使用了不允许的确定性因果措辞。")
        if unsupported:
            errors.append("报告包含无可验证引用的声明。")
        return ReportValidation(
            valid=not errors,
            claim_count=claim_count,
            unsupported_claim_count=unsupported,
            invalid_evidence_ids=invalid_evidence,
            invalid_document_ids=invalid_documents,
            prohibited_causal_phrases=prohibited,
            errors=errors,
        )

