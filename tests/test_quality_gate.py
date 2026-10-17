"""Tests for the quality gate exit-code contract."""

import pytest

from core.services.quality_gate import CriticalFindings, ExitCode, evaluate_gate


def test_exit_codes_are_stable_public_contract() -> None:
    assert [e.value for e in ExitCode] == [0, 1, 2, 3]


def test_critical_findings_from_layer1() -> None:
    layer1 = {
        "leaks": [{"file": "a"}, {"file": "b"}],
        "security": [
            {"extra": {"severity": "ERROR"}},
            {"extra": {"severity": "WARNING"}},
            {"extra": {}},
        ],
        "dependencies": [
            {"name": "x", "known_vulnerabilities": [{"cve_id": "CVE-1"}]},
            {"name": "y", "known_vulnerabilities": []},
        ],
    }
    c = CriticalFindings.from_layer1(layer1)
    assert (c.secret_leaks, c.sast_errors, c.vulnerable_dependencies, c.total) == (2, 1, 1, 4)


def test_critical_findings_tolerates_missing_keys() -> None:
    assert CriticalFindings.from_layer1({}).total == 0


@pytest.mark.parametrize(
    ("score", "critical", "min_score", "fail_on_critical", "expected"),
    [
        (90, 0, 80, False, ExitCode.PASSED),
        (70, 0, 80, False, ExitCode.BELOW_THRESHOLD),
        (70, 0, None, False, ExitCode.PASSED),
        (90, 1, 80, False, ExitCode.PASSED),  # criticals ignored unless opted in
        (90, 1, 80, True, ExitCode.SECURITY_VIOLATION),
        (70, 1, 80, True, ExitCode.SECURITY_VIOLATION),  # security takes precedence
        (80, 0, 80, False, ExitCode.PASSED),  # threshold is inclusive
    ],
)
def test_evaluate_gate(score, critical, min_score, fail_on_critical, expected) -> None:
    decision = evaluate_gate(score, CriticalFindings(secret_leaks=critical), min_score, fail_on_critical)
    assert decision.exit_code is expected
    assert decision.passed is (expected is ExitCode.PASSED)
    assert bool(decision.reasons) is (expected is not ExitCode.PASSED)
