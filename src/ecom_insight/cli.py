from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
import uvicorn

from ecom_insight.anomaly import AnomalyRunner
from ecom_insight.attribution import AttributionRunner
from ecom_insight.config import AppSettings
from ecom_insight.demo import DemoDataGenerator
from ecom_insight.evaluation import (
    AnomalyEvaluator,
    AttributionEvaluator,
    ReportingEvaluator,
)
from ecom_insight.logging import configure_logging
from ecom_insight.metrics import AnalysisRunner
from ecom_insight.reporting.runner import ReportRunner
from ecom_insight.retrieval import KnowledgeBuilder
from ecom_insight.warehouse import WarehouseBuilder

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _settings(source_root: Path | None, output_root: Path | None) -> AppSettings:
    if source_root is not None and output_root is not None:
        return AppSettings(source_root=source_root, output_root=output_root)
    if source_root is not None:
        return AppSettings(source_root=source_root)
    if output_root is not None:
        return AppSettings(output_root=output_root)  # type: ignore[call-arg]
    return AppSettings()  # type: ignore[call-arg]


@app.command("build-warehouse")
def build_warehouse_command(
    source_root: Annotated[
        Path | None,
        typer.Option(help="Snapshot current directory; defaults to ECOM_SOURCE_ROOT"),
    ] = None,
    output_root: Annotated[
        Path | None,
        typer.Option(help="Local generated-data directory; defaults to ECOM_OUTPUT_ROOT"),
    ] = None,
) -> None:
    settings = _settings(source_root, output_root)
    configure_logging(settings.log_level)
    result = WarehouseBuilder(settings).build()
    typer.echo(f"DuckDB: {result.database_path}")
    typer.echo(f"Quality: {result.quality_status}")
    typer.echo(f"Manifest: {result.manifest_path}")


@app.command("audit-data")
def audit_data_command(
    source_root: Annotated[
        Path | None,
        typer.Option(help="Snapshot current directory; defaults to ECOM_SOURCE_ROOT"),
    ] = None,
) -> None:
    settings = _settings(source_root, None)
    settings.validate_expected_sources()
    typer.echo("Source paths validated in read-only mode.")
    typer.echo(f"Main database: {settings.luopan_db().relative_to(settings.source_root)}")
    typer.echo("Sensitive session/auth/config paths are excluded by design.")


@app.command("run-analysis")
def run_analysis_command(
    database: Annotated[
        Path,
        typer.Option(help="DuckDB warehouse created by Phase 2"),
    ] = Path("data/processed/ecom_insight.duckdb"),
    metrics: Annotated[
        Path,
        typer.Option(help="Central metric registry YAML"),
    ] = Path("configs/metrics.yaml"),
    artifact_root: Annotated[
        Path,
        typer.Option(help="Local directory for generated analysis summaries"),
    ] = Path("data/processed/artifacts"),
    curated_parquet_root: Annotated[
        Path,
        typer.Option(help="Local directory for exported analysis marts"),
    ] = Path("data/processed/parquet/curated"),
) -> None:
    configure_logging()
    result = AnalysisRunner(
        database_path=database,
        metric_config_path=metrics,
        artifact_root=artifact_root,
        curated_parquet_root=curated_parquet_root,
    ).run()
    typer.echo(f"Metrics: {result.metric_count}")
    typer.echo(f"Summary: {result.summary_path}")
    typer.echo(f"Marts: {len(result.mart_counts)}")


@app.command("generate-demo-data")
def generate_demo_data_command(
    config: Annotated[
        Path,
        typer.Option(help="Synthetic dataset and controlled anomaly scenario config"),
    ] = Path("configs/demo_scenarios.yaml"),
    output_root: Annotated[
        Path,
        typer.Option(help="Public, fully synthetic JSON output directory"),
    ] = Path("data/demo/generated"),
    reference_database: Annotated[
        Path | None,
        typer.Option(
            help=(
                "Optional sanitized Phase 2 DuckDB; only bounded rate medians are read. "
                "No real rows or amounts are copied"
            )
        ),
    ] = Path("data/processed/ecom_insight.duckdb"),
) -> None:
    configure_logging()
    result = DemoDataGenerator(
        config_path=config,
        output_root=output_root,
        reference_database=reference_database,
    ).generate()
    typer.echo(f"Synthetic rows: {sum(result.row_counts.values())}")
    typer.echo(f"Scenarios: {result.scenario_count}")
    typer.echo(f"All scenarios verified: {result.all_scenarios_verified}")
    typer.echo(f"Manifest: {result.manifest_path}")


@app.command("run-anomaly")
def run_anomaly_command(
    database: Annotated[
        Path,
        typer.Option(help="DuckDB warehouse containing Phase 3 marts"),
    ] = Path("data/processed/ecom_insight.duckdb"),
    artifact_root: Annotated[
        Path,
        typer.Option(help="Local directory for anomaly summaries"),
    ] = Path("data/processed/artifacts"),
) -> None:
    configure_logging()
    result = AnomalyRunner(
        database_path=database,
        artifact_root=artifact_root,
    ).run()
    typer.echo(f"Series: {result.series_count}")
    typer.echo(f"Scored points: {result.scored_point_count}")
    typer.echo(f"Anomalies: {result.anomaly_count}")
    typer.echo(f"Summary: {result.artifact_path}")


@app.command("evaluate-anomaly")
def evaluate_anomaly_command(
    demo_root: Annotated[
        Path,
        typer.Option(help="Public demo data directory with controlled anomaly labels"),
    ] = Path("data/demo/generated"),
    artifact_root: Annotated[
        Path,
        typer.Option(help="Local directory for evaluation results"),
    ] = Path("data/processed/artifacts"),
) -> None:
    configure_logging()
    result = AnomalyEvaluator(
        demo_root=demo_root,
        artifact_root=artifact_root,
    ).run()
    typer.echo(f"Cases: {result.case_count}")
    for detector in result.detector_results:
        typer.echo(
            f"{detector.detector}: precision={detector.precision:.3f}, "
            f"recall={detector.recall:.3f}, f1={detector.f1:.3f}"
        )
    typer.echo(f"Evaluation: {result.artifact_path}")


@app.command("run-attribution")
def run_attribution_command(
    database: Annotated[
        Path,
        typer.Option(help="DuckDB warehouse containing Phase 4 anomaly results"),
    ] = Path("data/processed/ecom_insight.duckdb"),
    artifact_root: Annotated[
        Path,
        typer.Option(help="Local directory for attribution summaries"),
    ] = Path("data/processed/artifacts"),
) -> None:
    configure_logging()
    result = AttributionRunner(
        database_path=database,
        artifact_root=artifact_root,
    ).run()
    typer.echo(f"Events: {result.event_count}")
    typer.echo(f"Candidates: {result.candidate_count}")
    typer.echo(f"Evidence rows: {result.evidence_count}")
    typer.echo(f"Summary: {result.artifact_path}")


@app.command("evaluate-attribution")
def evaluate_attribution_command(
    demo_root: Annotated[
        Path,
        typer.Option(help="Public demo data directory with controlled scenario labels"),
    ] = Path("data/demo/generated"),
    artifact_root: Annotated[
        Path,
        typer.Option(help="Local directory for attribution evaluation results"),
    ] = Path("data/processed/artifacts"),
) -> None:
    configure_logging()
    result = AttributionEvaluator(
        demo_root=demo_root,
        artifact_root=artifact_root,
    ).run()
    typer.echo(f"Cases: {result.summary.case_count}")
    typer.echo(f"Top-1 accuracy: {result.summary.rule_top1_accuracy:.3f}")
    typer.echo(f"Evidence precision: {result.summary.evidence_precision:.3f}")
    typer.echo(f"Evidence coverage: {result.summary.evidence_coverage:.3f}")
    typer.echo(f"Evaluation: {result.artifact_path}")


@app.command("build-knowledge")
def build_knowledge_command(
    database: Annotated[
        Path,
        typer.Option(help="DuckDB warehouse used for local knowledge tables"),
    ] = Path("data/processed/ecom_insight.duckdb"),
    metrics: Annotated[
        Path,
        typer.Option(help="Central metric registry YAML"),
    ] = Path("configs/metrics.yaml"),
    rules: Annotated[
        Path,
        typer.Option(help="Attribution rule knowledge YAML"),
    ] = Path("configs/attribution_rules.yaml"),
    demo_root: Annotated[
        Path,
        typer.Option(help="Public controlled-case directory"),
    ] = Path("data/demo/generated"),
    artifact_root: Annotated[
        Path,
        typer.Option(help="Local directory for knowledge build summary"),
    ] = Path("data/processed/artifacts"),
) -> None:
    configure_logging()
    result = KnowledgeBuilder(
        database_path=database,
        metric_config_path=metrics,
        rule_config_path=rules,
        demo_root=demo_root,
        artifact_root=artifact_root,
    ).run()
    typer.echo(f"Documents: {result.document_count}")
    typer.echo(f"Embedding: {result.embedding_model}")
    typer.echo(f"Summary: {result.artifact_path}")


@app.command("generate-reports")
def generate_reports_command(
    database: Annotated[
        Path,
        typer.Option(help="DuckDB warehouse containing attribution and knowledge tables"),
    ] = Path("data/processed/ecom_insight.duckdb"),
    artifact_root: Annotated[
        Path,
        typer.Option(help="Local directory for validated report summary"),
    ] = Path("data/processed/artifacts"),
    limit: Annotated[
        int | None,
        typer.Option(help="Optional maximum number of attribution events"),
    ] = None,
) -> None:
    configure_logging()
    result = ReportRunner(
        database_path=database,
        artifact_root=artifact_root,
    ).run(limit=limit)
    typer.echo(f"Reports: {result.report_count}")
    typer.echo(f"Claims: {result.claim_count}")
    typer.echo(f"Unsupported claims: {result.unsupported_claim_count}")
    typer.echo(f"Summary: {result.artifact_path}")


@app.command("evaluate-reporting")
def evaluate_reporting_command(
    database: Annotated[
        Path,
        typer.Option(help="DuckDB warehouse containing local knowledge tables"),
    ] = Path("data/processed/ecom_insight.duckdb"),
    demo_root: Annotated[
        Path,
        typer.Option(help="Public controlled-case directory"),
    ] = Path("data/demo/generated"),
    artifact_root: Annotated[
        Path,
        typer.Option(help="Local directory for retrieval/report evaluation"),
    ] = Path("data/processed/artifacts"),
) -> None:
    configure_logging()
    result = ReportingEvaluator(
        database_path=database,
        demo_root=demo_root,
        artifact_root=artifact_root,
    ).run()
    retrieval = result.summary.retrieval
    typer.echo(f"Rule Hit@1: {retrieval.rule_hit_at_1:.3f}")
    typer.echo(f"Rule Hit@3: {retrieval.rule_hit_at_3:.3f}")
    for variant in result.summary.variants:
        typer.echo(
            f"{variant.variant}: status={variant.status}, "
            f"unsupported_rate={variant.unsupported_claim_rate}"
        )
    typer.echo(f"Evaluation: {result.artifact_path}")


@app.command("serve-api")
def serve_api_command(
    host: Annotated[
        str,
        typer.Option(help="API bind host"),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option(help="API bind port"),
    ] = 8000,
    reload: Annotated[
        bool,
        typer.Option(help="Reload the server when Python files change"),
    ] = False,
) -> None:
    uvicorn.run(
        "ecom_insight.api.app:app",
        host=host,
        port=port,
        reload=reload,
    )


def build_warehouse_entrypoint() -> None:
    app(args=["build-warehouse", *sys.argv[1:]], prog_name="ecom-build-warehouse")


def audit_data_entrypoint() -> None:
    app(args=["audit-data", *sys.argv[1:]], prog_name="ecom-audit-data")


def run_analysis_entrypoint() -> None:
    app(args=["run-analysis", *sys.argv[1:]], prog_name="ecom-run-analysis")


def generate_demo_data_entrypoint() -> None:
    app(
        args=["generate-demo-data", *sys.argv[1:]],
        prog_name="ecom-generate-demo-data",
    )


def run_anomaly_entrypoint() -> None:
    app(args=["run-anomaly", *sys.argv[1:]], prog_name="ecom-run-anomaly")


def evaluate_anomaly_entrypoint() -> None:
    app(
        args=["evaluate-anomaly", *sys.argv[1:]],
        prog_name="ecom-evaluate-anomaly",
    )


def run_attribution_entrypoint() -> None:
    app(
        args=["run-attribution", *sys.argv[1:]],
        prog_name="ecom-run-attribution",
    )


def evaluate_attribution_entrypoint() -> None:
    app(
        args=["evaluate-attribution", *sys.argv[1:]],
        prog_name="ecom-evaluate-attribution",
    )


def build_knowledge_entrypoint() -> None:
    app(
        args=["build-knowledge", *sys.argv[1:]],
        prog_name="ecom-build-knowledge",
    )


def generate_reports_entrypoint() -> None:
    app(
        args=["generate-reports", *sys.argv[1:]],
        prog_name="ecom-generate-reports",
    )


def evaluate_reporting_entrypoint() -> None:
    app(
        args=["evaluate-reporting", *sys.argv[1:]],
        prog_name="ecom-evaluate-reporting",
    )


def serve_api_entrypoint() -> None:
    app(
        args=["serve-api", *sys.argv[1:]],
        prog_name="ecom-api",
    )


if __name__ == "__main__":
    app()
