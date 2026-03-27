from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RetrievedDocument:
    text: str
    metadata: dict[str, Any]
    score: float | None = None
