"""Quality gate evaluation and CI exit-code contract.

The CLI exit code is a public API consumed by CI pipelines, so it is defined
in one place and derived from a pure function that is trivially testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class ExitCode(IntEnum):
    """Stable process exit codes returned by ``warden audit``."""

    PASSED = 0
    BELOW_THRESHOLD = 1
    SECURITY_VIOLATION = 2
    EXECUTION_ERROR = 3


@dataclass(frozen=True)
class CriticalFindings:
    """Counts of findings severe enough to fail a security-strict gate."""

    secret_leaks: int = 0
    sast_errors: int = 0
    vulnerable_dependencies: int = 0

    @property
    def total(self) -> int:
        return self.secret_leaks + self.sast_errors + self.vulnerable_dependencies

    @classmethod
    def from_layer1(cls, layer1: dict[str, Any]) -> CriticalFindings:
        """Derives critical finding counts from raw Layer 1 scanner output."""
        sast = layer1.get("security") or []
        deps = layer1.get("dependencies") or []
        return cls(
            secret_leaks=len(layer1.get("leaks") or []),
            sast_errors=sum(
                1 for f in sast if (f.get("extra") or {}).get("severity", "").upper() == "ERROR"
            ),
            vulnerable_dependencies=sum(1 for d in deps if d.get("known_vulnerabilities")),
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "secret_leaks": self.secret_leaks,
            "sast_errors": self.sast_errors,
            "vulnerable_dependencies": self.vulnerable_dependencies,
            "total": self.total,
        }


@dataclass(frozen=True)
class GateDecision:
    """Outcome of a quality gate evaluation."""

    exit_code: ExitCode
    reasons: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.exit_code is ExitCode.PASSED


def evaluate_gate(
    total_score: float,
    critical: CriticalFindings,
    min_score: float | None = None,
    fail_on_critical: bool = False,
) -> GateDecision:
    """Evaluates the quality gate.

    Security violations take precedence over score thresholds, so a pipeline
    can distinguish "code got worse" (1) from "code is unsafe to ship" (2).
    """
    if fail_on_critical and critical.total > 0:
        return GateDecision(
            ExitCode.SECURITY_VIOLATION,
            [
                (
                    f"{critical.total} critical finding(s): "
                    f"{critical.secret_leaks} secret leak(s), "
                    f"{critical.sast_errors} SAST error(s), "
                    f"{critical.vulnerable_dependencies} vulnerable dependenc(ies)"
                )
            ],
        )
    if min_score is not None and total_score < min_score:
        return GateDecision(
            ExitCode.BELOW_THRESHOLD,
            [f"score {total_score} is below threshold {min_score}"],
        )
    return GateDecision(ExitCode.PASSED)
