from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import duckdb

from ecom_insight.attribution import (
    AttributionCandidate,
    ConfidenceBreakdown,
    EvidenceItem,
    MetricDecomposition,
)
from ecom_insight.reporting.models import EvidenceBundle
from ecom_insight.retrieval import (
    DuckDBKnowledgeRepository,
    RetrievalFilters,
)

ATTRIBUTION_ID_PATTERN = re.compile(r"^[0-9a-f]{24}$")


def _json_list(value: Any) -> list[Any]:
    payload = json.loads(str(value))
    if not isinstance(payload, list):
        raise ValueError("Expected JSON list in attribution warehouse")
    return payload


class AttributionEvidenceService:
    """Allowlisted, parameterized SQL access for one masked attribution event."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.resolve()
        self.knowledge_index = DuckDBKnowledgeRepository(
            database_path=self.database_path
        ).load()

    def list_attribution_ids(self, *, limit: int | None = None) -> list[str]:
        query = """
            SELECT DISTINCT attribution_id
            FROM fact_attribution
            WHERE data_origin = 'real'
            ORDER BY attribution_id
        """
        parameters: list[int] = []
        if limit is not None:
            if limit < 1:
                raise ValueError("Attribution limit must be positive")
            query += " LIMIT ?"
            parameters.append(limit)
        with duckdb.connect(str(self.database_path), read_only=True) as connection:
            return [
                str(row[0])
                for row in connection.execute(query, parameters).fetchall()
            ]

    def get_bundle(self, attribution_id: str) -> EvidenceBundle:
        if not ATTRIBUTION_ID_PATTERN.fullmatch(attribution_id):
            raise ValueError("Invalid attribution ID")
        with duckdb.connect(str(self.database_path), read_only=True) as connection:
            candidate_rows = connection.execute(
                """
                SELECT
                    entity_type,
                    entity_id,
                    date,
                    target_metric,
                    detector_names_json,
                    anomaly_score,
                    severity,
                    rule_id,
                    cause_code,
                    cause,
                    evidence_status,
                    confidence,
                    confidence_breakdown_json,
                    explanation,
                    missing_information_json,
                    decomposition_json,
                    data_origin
                FROM fact_attribution
                WHERE attribution_id = ?
                ORDER BY confidence DESC, rule_id
                """,
                [attribution_id],
            ).fetchall()
            if not candidate_rows:
                raise KeyError(f"Unknown attribution ID: {attribution_id}")
            evidence_rows = connection.execute(
                """
                SELECT
                    rule_id,
                    evidence_role,
                    evidence_id,
                    metric,
                    source_table,
                    current_value,
                    baseline_value,
                    change_rate,
                    unit,
                    comparison_window,
                    evidence_status,
                    quality_flags_json
                FROM fact_attribution_evidence
                WHERE attribution_id = ?
                ORDER BY rule_id, evidence_role, evidence_id
                """,
                [attribution_id],
            ).fetchall()

        evidence_by_id: dict[str, EvidenceItem] = {}
        evidence_by_rule_role: dict[tuple[str, str], list[EvidenceItem]] = {}
        for row in evidence_rows:
            item = EvidenceItem(
                evidence_id=str(row[2]),
                metric=str(row[3]),
                source_table=str(row[4]),
                current_value=float(row[5]) if row[5] is not None else None,
                baseline_value=float(row[6]) if row[6] is not None else None,
                change_rate=float(row[7]) if row[7] is not None else None,
                unit=str(row[8]),
                comparison_window=str(row[9]),
                status=str(row[10]),  # type: ignore[arg-type]
                quality_flags=[str(value) for value in _json_list(row[11])],
            )
            evidence_by_id[item.evidence_id] = item
            evidence_by_rule_role.setdefault((str(row[0]), str(row[1])), []).append(
                item
            )

        first = candidate_rows[0]
        candidates: list[AttributionCandidate] = []
        all_missing: list[str] = []
        for row in candidate_rows:
            rule_id = str(row[7])
            missing = [str(value) for value in _json_list(row[14])]
            all_missing.extend(missing)
            candidates.append(
                AttributionCandidate(
                    rule_id=rule_id,
                    cause_code=str(row[8]),
                    cause=str(row[9]),
                    status=str(row[10]),  # type: ignore[arg-type]
                    evidence_score=float(row[11]),
                    evidence_score_breakdown=ConfidenceBreakdown.model_validate_json(
                        str(row[12])
                    ),
                    supporting_evidence=evidence_by_rule_role.get(
                        (rule_id, "supporting"), []
                    ),
                    counter_evidence=evidence_by_rule_role.get(
                        (rule_id, "counter"), []
                    ),
                    missing_information=missing,
                    explanation=str(row[13]),
                )
            )
        decomposition = (
            MetricDecomposition.model_validate_json(str(first[15]))
            if first[15] is not None
            else None
        )
        query_text = self._retrieval_query(
            target_metric=str(first[3]),
            candidates=candidates,
            evidence=list(evidence_by_id.values()),
        )
        retrieved = self.knowledge_index.search(
            query_text,
            limit=5,
            filters=RetrievalFilters(
                document_types={
                    "historical_case",
                    "attribution_rule",
                    "metric_definition",
                }
            ),
            minimum_score=0.01,
        )
        return EvidenceBundle(
            attribution_id=attribution_id,
            entity_type=str(first[0]),
            entity_id=str(first[1]),
            date=first[2],
            target_metric=str(first[3]),
            detector_names=[str(value) for value in _json_list(first[4])],
            anomaly_score=float(first[5]),
            severity=str(first[6]),  # type: ignore[arg-type]
            decomposition=decomposition,
            candidates=candidates,
            evidence=list(evidence_by_id.values()),
            missing_information=list(dict.fromkeys(all_missing)),
            retrieved_documents=retrieved,
            data_origin=str(first[16]),  # type: ignore[arg-type]
        )

    @staticmethod
    def _retrieval_query(
        *,
        target_metric: str,
        candidates: list[AttributionCandidate],
        evidence: list[EvidenceItem],
    ) -> str:
        cause_terms = " ".join(
            f"{candidate.cause} {candidate.cause_code}"
            for candidate in candidates[:2]
            if candidate.status != "insufficient_data"
        )
        evidence_terms = " ".join(
            item.metric
            for item in evidence
            if item.change_rate is not None and abs(item.change_rate) >= 0.15
        )
        return f"异常指标 {target_metric} {cause_terms} 变化证据 {evidence_terms}"
