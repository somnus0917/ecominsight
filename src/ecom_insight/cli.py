from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from ecom_insight.config import AppSettings
from ecom_insight.demo import DemoDataGenerator
from ecom_insight.logging import configure_logging
from ecom_insight.metrics import AnalysisRunner
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


if __name__ == "__main__":
    app()
