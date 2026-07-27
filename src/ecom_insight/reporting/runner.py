from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import structlog

from ecom_insight.llm import (
    DeterministicEvidenceReportGenerator,
    EvidenceReportGenerator,
    ReportValidator,
    generate_and_validate,
)
from ecom_insight.reporting.evidence import AttributionEvidenceService

LOGGER = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ReportRunResult:
    database_path: Path
    artifact_path: Path
    report_count: int
    claim_count: int
    unsupported_claim_count: int
    generator_name: str


class ReportRunner:
    def __init__(
        self,
        *,
        database_path: Path,
        artifact_root: Path,
        generator: EvidenceReportGenerator | None = None,
    ) -> None:
        self.database_path = database_path.resolve()
        self.artifact_root = artifact_root.resolve()
        self.generator = generator or DeterministicEvidenceReportGenerator()
        self.validator = ReportValidator()

    def run(self, *, limit: int | None = None) -> ReportRunResult:
        service = AttributionEvidenceService(self.database_path)
        attribution_ids = service.list_attribution_ids(limit=limit)
        rows: list[tuple[Any, ...]] = []
        claim_count = 0
        unsupported_count = 0
        for attribution_id in attribution_ids:
            bundle = service.get_bundle(attribution_id)
            report, validation = generate_and_validate(
                generator=self.generator,
                validator=self.validator,
                bundle=bundle,
            )
            claim_count += validation.claim_count
            unsupported_count += validation.unsupported_claim_count
            rows.append(
                (
                    report.report_id,
                    report.attribution_id,
                    report.generator,
                    json.dumps(report.model_dump(mode="json"), ensure_ascii=False),
                    validation.valid,
                    validation.claim_count,
                    validation.unsupported_claim_count,
                    json.dumps(
                        validation.model_dump(mode="json"), ensure_ascii=False
                    ),
                    bundle.data_origin,
                )
            )
        with duckdb.connect(str(self.database_path)) as connection:
            self._publish(connection, rows)
        payload = {
            "schema_version": "1",
            "report_count": len(rows),
            "claim_count": claim_count,
            "unsupported_claim_count": unsupported_count,
            "unsupported_claim_rate": (
                unsupported_count / claim_count if claim_count else 0
            ),
            "generator": self.generator.generator_name,
            "external_api_used": self.generator.generator_name.startswith(
                "structured_llm:"
            ),
            "validation_policy": [
                "所有事实和候选原因必须引用当前证据包中的evidence_id。",
                "历史案例引用必须来自当前检索结果。",
                "确定性因果措辞会使报告验证失败。",
            ],
        }
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        artifact_path = self.artifact_root / "phase6_report_summary.json"
        artifact_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        LOGGER.info(
            "phase6_report_complete",
            report_count=len(rows),
            claim_count=claim_count,
            unsupported_claim_count=unsupported_count,
            generator=self.generator.generator_name,
        )
        return ReportRunResult(
            database_path=self.database_path,
            artifact_path=artifact_path,
            report_count=len(rows),
            claim_count=claim_count,
            unsupported_claim_count=unsupported_count,
            generator_name=self.generator.generator_name,
        )

    @staticmethod
    def _publish(
        connection: duckdb.DuckDBPyConnection,
        rows: list[tuple[Any, ...]],
    ) -> None:
        connection.execute(
            """
            CREATE OR REPLACE TABLE fact_attribution_report (
                report_id VARCHAR PRIMARY KEY,
                attribution_id VARCHAR NOT NULL,
                generator VARCHAR NOT NULL,
                report_json JSON NOT NULL,
                validation_passed BOOLEAN NOT NULL,
                claim_count INTEGER NOT NULL,
                unsupported_claim_count INTEGER NOT NULL,
                validation_json JSON NOT NULL,
                data_origin VARCHAR NOT NULL
            )
            """
        )
        if rows:
            connection.executemany(
                "INSERT INTO fact_attribution_report VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )

