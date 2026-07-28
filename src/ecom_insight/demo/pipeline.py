"""One-command demo pipeline orchestrator.

Generates synthetic data, builds a DuckDB warehouse, runs analysis, anomaly
detection, attribution, knowledge and reports, then writes a build summary.
No real data or external API is required.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from ecom_insight.anomaly import AnomalyRunner
from ecom_insight.attribution import AttributionRunner
from ecom_insight.demo import DemoDataGenerator, DemoWarehouseBuilder
from ecom_insight.evaluation import AnomalyEvaluator, AttributionEvaluator
from ecom_insight.metrics import AnalysisRunner
from ecom_insight.reporting.runner import ReportRunner
from ecom_insight.retrieval import KnowledgeBuilder

LOGGER = structlog.get_logger(__name__)

DEFAULT_DEMO_ROOT = Path("data/demo/generated")
DEFAULT_OUTPUT_ROOT = Path("data/demo/processed")
DEFAULT_DATABASE = DEFAULT_OUTPUT_ROOT / "ecom_insight_demo.duckdb"
DEFAULT_CONFIG = Path("configs/demo_scenarios.yaml")
DEFAULT_METRICS = Path("configs/metrics.yaml")
DEFAULT_RULES = Path("configs/attribution_rules.yaml")
BUILD_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class DemoBuildResult:
    database_path: Path
    summary_path: Path
    success: bool
    steps_completed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class DemoPipeline:
    """Orchestrates the full demo build from synthetic data to reports."""

    def __init__(
        self,
        *,
        config_path: Path = DEFAULT_CONFIG,
        demo_data_root: Path = DEFAULT_DEMO_ROOT,
        output_root: Path = DEFAULT_OUTPUT_ROOT,
        metrics_config: Path = DEFAULT_METRICS,
        rules_config: Path = DEFAULT_RULES,
    ) -> None:
        self.config_path = config_path
        self.demo_data_root = demo_data_root
        self.output_root = output_root
        self.metrics_config = metrics_config
        self.rules_config = rules_config
        self.database_path = output_root / "ecom_insight_demo.duckdb"
        self.artifact_root = output_root / "artifacts"
        self.summary_path = output_root / "demo_build_summary.json"

    def run(self) -> DemoBuildResult:
        steps: list[str] = []
        errors: list[str] = []

        try:
            self._clean_previous()
            steps.append("clean_previous")

            gen_result = DemoDataGenerator(
                config_path=self.config_path,
                output_root=self.demo_data_root,
                reference_database=None,
            ).generate()
            steps.append("generate_synthetic_data")
            LOGGER.info("demo_synthetic_generated", rows=sum(gen_result.row_counts.values()))

            wh_result = DemoWarehouseBuilder(
                demo_root=self.demo_data_root,
                database_path=self.database_path,
            ).build()
            steps.append("build_warehouse")
            LOGGER.info("demo_warehouse_built", tables=wh_result.table_counts)

            AnalysisRunner(
                database_path=self.database_path,
                metric_config_path=self.metrics_config,
                artifact_root=self.artifact_root,
            ).run()
            steps.append("run_analysis")

            anomaly_result = AnomalyRunner(
                database_path=self.database_path,
                artifact_root=self.artifact_root,
                data_origin="demo",
            ).run()
            steps.append("run_anomaly")

            attribution_result = AttributionRunner(
                database_path=self.database_path,
                artifact_root=self.artifact_root,
                config_path=self.rules_config,
                data_origin="demo",
            ).run()
            steps.append("run_attribution")

            KnowledgeBuilder(
                database_path=self.database_path,
                metric_config_path=self.metrics_config,
                rule_config_path=self.rules_config,
                demo_root=self.demo_data_root,
                artifact_root=self.artifact_root,
                data_origin="demo",
            ).run()
            steps.append("build_knowledge")

            report_result = ReportRunner(
                database_path=self.database_path,
                artifact_root=self.artifact_root,
                data_origin="demo",
            ).run()
            steps.append("generate_reports")

            AnomalyEvaluator(
                demo_root=self.demo_data_root,
                artifact_root=self.artifact_root,
            ).run()
            steps.append("evaluate_anomaly")

            AttributionEvaluator(
                demo_root=self.demo_data_root,
                artifact_root=self.artifact_root,
                config_path=self.rules_config,
            ).run()
            steps.append("evaluate_attribution")

            self._write_summary(
                gen_result=gen_result,
                wh_result=wh_result,
                anomaly_result=anomaly_result,
                attribution_result=attribution_result,
                report_result=report_result,
                steps=steps,
            )
            steps.append("write_summary")

        except Exception as exc:
            LOGGER.error(
                "demo_pipeline_failed", error=str(exc), step=steps[-1] if steps else "init"
            )
            errors.append(f"{steps[-1] if steps else 'init'}: {exc}")
            return DemoBuildResult(
                database_path=self.database_path,
                summary_path=self.summary_path,
                success=False,
                steps_completed=steps,
                errors=errors,
            )

        return DemoBuildResult(
            database_path=self.database_path,
            summary_path=self.summary_path,
            success=True,
            steps_completed=steps,
            errors=errors,
        )

    def _clean_previous(self) -> None:
        if self.output_root.exists():
            shutil.rmtree(self.output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    def _write_summary(
        self,
        *,
        gen_result: Any,
        wh_result: Any,
        anomaly_result: Any,
        attribution_result: Any,
        report_result: Any,
        steps: list[str],
    ) -> None:
        manifest = json.loads((self.demo_data_root / "manifest.json").read_text(encoding="utf-8"))
        summary: dict[str, Any] = {
            "build_version": BUILD_VERSION,
            "synthetic": True,
            "data_origin": "demo",
            "built_at": datetime.now(UTC).isoformat(),
            "random_seed": manifest.get("seed"),
            "date_range": manifest.get("date_range"),
            "shop_count": len(
                {
                    row.get("shop_id")
                    for row in _load_json_safe(self.demo_data_root / "shop_daily.json")
                    if row.get("shop_id")
                }
            ),
            "product_count": wh_result.table_counts.get("fact_product_daily", 0),
            "scenario_count": manifest.get("scenario_count", 0),
            "scenario_ids": manifest.get("scenario_ids", []),
            "anomaly_event_count": anomaly_result.anomaly_count,
            "attribution_candidate_count": attribution_result.candidate_count,
            "report_count": report_result.report_count,
            "unsupported_claim_count": report_result.unsupported_claim_count,
            "warehouse_table_counts": wh_result.table_counts,
            "steps_completed": steps,
            "quality_checks": {
                "all_scenarios_verified": gen_result.all_scenarios_verified,
            },
        }
        self.summary_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        LOGGER.info("demo_summary_written", path=self.summary_path)


def _load_json_safe(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []
