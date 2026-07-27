from __future__ import annotations

from typing import Any, Protocol


class StructuredLLMClient(Protocol):
    """Provider-neutral client; implementations must return parsed JSON."""

    @property
    def model_name(self) -> str: ...

    def generate_structured(
        self,
        *,
        system_prompt: str,
        payload: dict[str, Any],
        json_schema: dict[str, Any],
    ) -> dict[str, Any]: ...

