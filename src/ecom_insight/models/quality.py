from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class QualityCheck(BaseModel):
    check_id: str
    table: str
    status: Literal["pass", "warn", "fail"]
    severity: Literal["low", "medium", "high", "critical"]
    message: str
    observed: int | float | str | None = None
    expected: int | float | str | None = None


class QualityReport(BaseModel):
    generated_at: datetime
    status: Literal["pass", "warn", "fail"]
    checks: list[QualityCheck] = Field(default_factory=list)

    @property
    def failed(self) -> bool:
        return any(check.status == "fail" for check in self.checks)
