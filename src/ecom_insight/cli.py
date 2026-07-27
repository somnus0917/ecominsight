from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from ecom_insight.config import AppSettings
from ecom_insight.logging import configure_logging
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


def build_warehouse_entrypoint() -> None:
    app(args=["build-warehouse", *sys.argv[1:]], prog_name="ecom-build-warehouse")


def audit_data_entrypoint() -> None:
    app(args=["audit-data", *sys.argv[1:]], prog_name="ecom-audit-data")


if __name__ == "__main__":
    app()
