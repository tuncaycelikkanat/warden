"""Unit tests for Warden domain exceptions hierarchy."""

from __future__ import annotations

from core.exceptions import (
    AnalyzerError,
    AnalyzerExecutionError,
    AnalyzerNotFoundError,
    AnalyzerTimeoutError,
    ConfigurationError,
    ExternalToolError,
    QualityGateError,
    SecurityGateViolationError,
    TargetPathError,
    ThresholdViolationError,
    ToolNotFoundError,
    WardenError,
)
from core.services.quality_gate import ExitCode


def test_warden_error_base_properties():
    err = WardenError("something broke", details={"foo": "bar"})
    assert str(err) == "something broke"
    assert err.exit_code == ExitCode.EXECUTION_ERROR
    assert err.details == {"foo": "bar"}
    data = err.to_dict()
    assert data["error_type"] == "WardenError"
    assert data["message"] == "something broke"
    assert data["exit_code"] == 3
    assert data["details"] == {"foo": "bar"}


def test_analyzer_error_hierarchy():
    err = AnalyzerNotFoundError("Analyzer 'custom' not found", analyzer_key="custom")
    assert isinstance(err, AnalyzerError)
    assert isinstance(err, WardenError)
    assert err.analyzer_key == "custom"
    assert err.details["analyzer_key"] == "custom"
    assert err.exit_code == ExitCode.EXECUTION_ERROR

    exec_err = AnalyzerExecutionError("Crash in lint analyzer", analyzer_key="lint")
    assert exec_err.analyzer_key == "lint"

    timeout_err = AnalyzerTimeoutError("Timeout in sec", analyzer_key="sec")
    assert timeout_err.analyzer_key == "sec"


def test_quality_gate_exceptions():
    thresh_err = ThresholdViolationError(score=72.5, min_score=80.0)
    assert isinstance(thresh_err, QualityGateError)
    assert isinstance(thresh_err, WardenError)
    assert thresh_err.exit_code == ExitCode.BELOW_THRESHOLD
    assert thresh_err.score == 72.5
    assert thresh_err.min_score == 80.0
    assert "72.5" in str(thresh_err)
    assert "80.0" in str(thresh_err)

    sec_err = SecurityGateViolationError(
        critical_count=2,
        breakdown={"secret_leaks": 1, "sast_errors": 1, "vulnerable_dependencies": 0},
    )
    assert isinstance(sec_err, QualityGateError)
    assert sec_err.exit_code == ExitCode.SECURITY_VIOLATION
    assert sec_err.critical_count == 2
    assert "2 critical finding(s)" in str(sec_err)


def test_tool_not_found_error():
    err = ToolNotFoundError("git binary not found", tool_name="git")
    assert isinstance(err, ExternalToolError)
    assert err.tool_name == "git"
    assert err.exit_code == ExitCode.EXECUTION_ERROR


def test_configuration_and_target_path_errors():
    err = TargetPathError("Directory /nonexistent does not exist")
    assert isinstance(err, ConfigurationError)
    assert isinstance(err, WardenError)
