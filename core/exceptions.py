"""Domain exceptions for WARDEN.

Defines a clean, strongly-typed exception hierarchy. All exceptions inherit
from :class:`WardenError` and carry an associated :class:`ExitCode` so CLI
and API entry points can translate domain failures to stable exit codes or HTTP statuses.
"""

from __future__ import annotations

from typing import Any

from core.services.quality_gate import ExitCode


class WardenError(Exception):
    """Base exception for all domain errors raised by WARDEN."""

    default_exit_code: ExitCode = ExitCode.EXECUTION_ERROR

    def __init__(
        self,
        message: str,
        *,
        exit_code: ExitCode | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code if exit_code is not None else self.default_exit_code
        self.details = details or {}

    def __str__(self) -> str:
        return self.message

    def to_dict(self) -> dict[str, Any]:
        """Serializes the error to a machine-readable dictionary."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "exit_code": int(self.exit_code),
            "details": self.details,
        }


# ---------------------------------------------------------------------------
# Configuration & Input Validation Errors
# ---------------------------------------------------------------------------


class ConfigurationError(WardenError):
    """Raised when configuration, arguments, or environment variables are invalid."""

    default_exit_code = ExitCode.EXECUTION_ERROR


class TargetPathError(ConfigurationError):
    """Raised when an audit target directory does not exist or is inaccessible."""


# ---------------------------------------------------------------------------
# Analyzer Errors
# ---------------------------------------------------------------------------


class AnalyzerError(WardenError):
    """Base exception for Layer 1 analyzer failures."""

    default_exit_code = ExitCode.EXECUTION_ERROR

    def __init__(
        self,
        message: str,
        *,
        analyzer_key: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged_details = dict(details or {})
        if analyzer_key:
            merged_details["analyzer_key"] = analyzer_key
        super().__init__(message, details=merged_details)
        self.analyzer_key = analyzer_key


class AnalyzerNotFoundError(AnalyzerError):
    """Raised when a requested analyzer plugin is not registered."""


class AnalyzerExecutionError(AnalyzerError):
    """Raised when an analyzer crashes during execution."""


class AnalyzerTimeoutError(AnalyzerError):
    """Raised when an analyzer exceeds its configured execution timeout."""


# ---------------------------------------------------------------------------
# External Tool & Environment Errors
# ---------------------------------------------------------------------------


class ExternalToolError(WardenError):
    """Base exception for failures involving external system tools (git, semgrep, etc.)."""

    default_exit_code = ExitCode.EXECUTION_ERROR

    def __init__(
        self,
        message: str,
        *,
        tool_name: str | None = None,
        exit_code_output: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = dict(details or {})
        if tool_name:
            merged["tool_name"] = tool_name
        if exit_code_output is not None:
            merged["tool_exit_code"] = exit_code_output
        super().__init__(message, details=merged)
        self.tool_name = tool_name
        self.exit_code_output = exit_code_output


class ToolNotFoundError(ExternalToolError):
    """Raised when a required system tool (e.g. git, semgrep) is not installed on PATH."""


# ---------------------------------------------------------------------------
# Quality Gate Errors
# ---------------------------------------------------------------------------


class QualityGateError(WardenError):
    """Base exception for quality gate policy rejections."""

    default_exit_code = ExitCode.BELOW_THRESHOLD


class ThresholdViolationError(QualityGateError):
    """Raised when the computed audit score falls below the required threshold."""

    default_exit_code = ExitCode.BELOW_THRESHOLD

    def __init__(
        self,
        score: float,
        min_score: float,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        message = f"Audit score {score:.1f} is below required threshold of {min_score:.1f}"
        merged = dict(details or {})
        merged.update({"score": score, "min_score": min_score})
        super().__init__(message, exit_code=ExitCode.BELOW_THRESHOLD, details=merged)
        self.score = score
        self.min_score = min_score


class SecurityGateViolationError(QualityGateError):
    """Raised when critical security vulnerabilities are found under --fail-on-critical."""

    default_exit_code = ExitCode.SECURITY_VIOLATION

    def __init__(
        self,
        critical_count: int,
        breakdown: dict[str, int],
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        message = (
            f"Quality gate rejected: {critical_count} critical finding(s) detected "
            f"({breakdown.get('secret_leaks', 0)} secrets, "
            f"{breakdown.get('sast_errors', 0)} SAST errors, "
            f"{breakdown.get('vulnerable_dependencies', 0)} vulnerable dependencies)"
        )
        merged = dict(details or {})
        merged.update({"critical_count": critical_count, "breakdown": breakdown})
        super().__init__(message, exit_code=ExitCode.SECURITY_VIOLATION, details=merged)
        self.critical_count = critical_count
        self.breakdown = breakdown


# ---------------------------------------------------------------------------
# Storage & Reporting Errors
# ---------------------------------------------------------------------------


class StorageError(WardenError):
    """Raised when persisting audit records or database operations fail."""


class ReportExportError(WardenError):
    """Raised when generating or exporting SARIF, PDF, or Markdown reports fails."""
