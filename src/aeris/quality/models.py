from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


QCLevel = str  # "info" | "warning" | "error"


@dataclass(slots=True)
class QCMessage:
    code: str
    level: QCLevel
    message: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class QCCheckResult:
    validator_id: str
    passed: bool
    messages: list[QCMessage] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class QCReport:
    domain: str
    target_path: str
    passed: bool
    checks: list[QCCheckResult] = field(default_factory=list)

    def error_count(self) -> int:
        return sum(
            1
            for check in self.checks
            for msg in check.messages
            if msg.level == "error"
        )

    def warning_count(self) -> int:
        return sum(
            1
            for check in self.checks
            for msg in check.messages
            if msg.level == "warning"
        )