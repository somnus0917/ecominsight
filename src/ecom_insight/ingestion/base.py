from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

Record = dict[str, Any]


@dataclass(slots=True)
class AdapterOutput:
    tables: dict[str, list[Record]]
    source_files: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def row_counts(self) -> dict[str, int]:
        return {name: len(rows) for name, rows in self.tables.items()}


class SourceAdapter(Protocol):
    def extract(self) -> AdapterOutput: ...
