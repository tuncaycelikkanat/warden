"""Unit tests for the Multi-Agent PanelistEvaluator."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.llm.panelist import (
    AnalystFindings,
    DefenderReport,
    PanelistEvaluator,
    PanelistVerdict,
    _extract_json,
)

# ── _extract_json helper ───────────────────────────────────────────────────────

def test_extract_json_direct():
    raw = '{"level": 8, "confidence_score": 0.9}'
    data = _extract_json(raw)
    assert data["level"] == 8


def test_extract_json_with_markdown_fence():
    raw = '```json\n{"level": 5}\n```'
    data = _extract_json(raw)
    assert data["level"] == 5


def test_extract_json_with_surrounding_text():
    raw = 'Here is my answer: {"level": 3, "confidence_score": 0.7} done.'
    data = _extract_json(raw)
    assert data["level"] == 3


def test_extract_json_raises_on_invalid():
    with pytest.raises(ValueError, match="No valid JSON"):
        _extract_json("This is not JSON at all")


# ── Dataclass parsing ──────────────────────────────────────────────────────────

def test_analyst_findings_parse():
    data = {
        "issues": ["No timeout on DB calls", "Bare except"],
        "risk_level": "high",
        "supporting_evidence": ["db.py", "utils.py"],
    }
    findings = AnalystFindings.parse(data)
    assert findings.risk_level == "high"
    assert len(findings.issues) == 2
    assert "db.py" in findings.supporting_evidence


def test_analyst_findings_parse_defaults():
    findings = AnalystFindings.parse({})
    assert findings.issues == []
    assert findings.risk_level == "unknown"


def test_defender_report_parse():
    data = {
        "false_positives": ["Bare except is intentional here"],
        "missing_evidence": ["tests/test_db.py"],
        "upheld_issues": ["No timeout on DB calls"],
    }
    report = DefenderReport.parse(data)
    assert len(report.false_positives) == 1
    assert "No timeout on DB calls" in report.upheld_issues


def test_defender_report_parse_defaults():
    report = DefenderReport.parse({})
    assert report.false_positives == []
    assert report.upheld_issues == []


# ── PanelistVerdict factory methods ───────────────────────────────────────────

def test_panelist_verdict_skipped():
    v = PanelistVerdict.skipped("missing_api_key")
    assert v.evaluated is False
    assert v.level is None
    assert v.confidence_score == 0.0
    assert "missing_api_key" in (v.reason or "")


def test_panelist_verdict_error():
    v = PanelistVerdict.error(RuntimeError("boom"))
    assert v.evaluated is False
    assert v.level is None


# ── PanelistEvaluator.run() ────────────────────────────────────────────────────

def _make_provider(analyst_json: str, defender_json: str, judge_json: str):
    """Builds a mock BaseLLMProvider that returns fixed responses per call order."""
    provider = MagicMock()
    responses = [
        (analyst_json, "mock-model"),
        (defender_json, "mock-model"),
        (judge_json, "mock-model"),
    ]
    call_count = {"n": 0}

    async def fake_generate_json(prompt, system_instruction, **kwargs):
        idx = call_count["n"]
        call_count["n"] += 1
        return responses[idx]

    provider.generate_json = fake_generate_json
    return provider


ANALYST_RESPONSE = json.dumps({
    "issues": ["No timeout on DB calls", "Bare except in main loop"],
    "risk_level": "high",
    "supporting_evidence": ["db.py", "main.py"],
})

DEFENDER_RESPONSE = json.dumps({
    "false_positives": ["Bare except in main loop"],  # defender disputes this
    "missing_evidence": ["tests/test_db.py"],
    "upheld_issues": ["No timeout on DB calls"],
})

JUDGE_RESPONSE = json.dumps({
    "level": 6,
    "confidence_score": 0.82,
    "justification": "One real issue found, one false positive removed by defender.",
    "dissent_notes": "Defender correctly identified bare except as intentional catch-all.",
})


@pytest.mark.asyncio
async def test_panelist_full_chain_success():
    provider = _make_provider(ANALYST_RESPONSE, DEFENDER_RESPONSE, JUDGE_RESPONSE)
    evaluator = PanelistEvaluator(provider=provider, confidence_threshold=0.5)

    verdict = await evaluator.run(
        category_key="api_design",
        rubric={0: "None", 5: "Partial", 10: "Full"},
        evidence_str='{"files": ["db.py"], "metrics": {}}',
    )

    assert verdict.evaluated is True
    assert verdict.level == 6
    assert abs(verdict.confidence_score - 0.82) < 0.01
    assert "false positive" in verdict.justification.lower()
    assert verdict.analyst_findings is not None
    assert verdict.defender_report is not None
    assert verdict.latency_sec >= 0.0


@pytest.mark.asyncio
async def test_panelist_confidence_below_threshold_marks_unevaluated():
    low_confidence_judge = json.dumps({
        "level": 4,
        "confidence_score": 0.3,  # below default 0.5 threshold
        "justification": "Highly uncertain",
        "dissent_notes": "Major disagreement between analyst and defender.",
    })
    provider = _make_provider(ANALYST_RESPONSE, DEFENDER_RESPONSE, low_confidence_judge)
    evaluator = PanelistEvaluator(provider=provider, confidence_threshold=0.5)

    verdict = await evaluator.run(
        category_key="api_design",
        rubric={0: "None", 10: "Full"},
        evidence_str="{}",
    )

    assert verdict.evaluated is False
    assert "confidence_below_threshold" in (verdict.reason or "")
    assert verdict.confidence_score == pytest.approx(0.3, abs=0.01)


@pytest.mark.asyncio
async def test_panelist_confidence_exactly_at_threshold_passes():
    judge_at_threshold = json.dumps({
        "level": 7,
        "confidence_score": 0.5,
        "justification": "Borderline case",
        "dissent_notes": "",
    })
    provider = _make_provider(ANALYST_RESPONSE, DEFENDER_RESPONSE, judge_at_threshold)
    evaluator = PanelistEvaluator(provider=provider, confidence_threshold=0.5)

    verdict = await evaluator.run(
        category_key="api_design",
        rubric={0: "None", 10: "Full"},
        evidence_str="{}",
    )

    # Exactly at threshold → evaluated (threshold is a strict lower bound)
    assert verdict.evaluated is True
    assert verdict.level == 7


@pytest.mark.asyncio
async def test_panelist_level_clamped_to_0_10():
    judge_out_of_bounds = json.dumps({
        "level": 15,  # out of range
        "confidence_score": 0.9,
        "justification": "Model went rogue",
        "dissent_notes": "",
    })
    provider = _make_provider(ANALYST_RESPONSE, DEFENDER_RESPONSE, judge_out_of_bounds)
    evaluator = PanelistEvaluator(provider=provider, confidence_threshold=0.5)

    verdict = await evaluator.run(
        category_key="api_design",
        rubric={0: "None", 10: "Full"},
        evidence_str="{}",
    )

    assert verdict.level == 10  # clamped


@pytest.mark.asyncio
async def test_panelist_handles_provider_exception():
    provider = MagicMock()
    provider.generate_json = AsyncMock(side_effect=RuntimeError("LLM unreachable"))

    evaluator = PanelistEvaluator(provider=provider, confidence_threshold=0.5)
    verdict = await evaluator.run(
        category_key="api_design",
        rubric={0: "None", 10: "Full"},
        evidence_str="{}",
    )

    assert verdict.evaluated is False
    assert "evaluation_error" in (verdict.reason or "")


@pytest.mark.asyncio
async def test_panelist_handles_malformed_json_from_judge():
    bad_judge = "This is not JSON"
    provider = _make_provider(ANALYST_RESPONSE, DEFENDER_RESPONSE, bad_judge)
    evaluator = PanelistEvaluator(provider=provider, confidence_threshold=0.5)

    verdict = await evaluator.run(
        category_key="api_design",
        rubric={0: "None", 10: "Full"},
        evidence_str="{}",
    )

    # Should not raise; should return error verdict
    assert verdict.evaluated is False


@pytest.mark.asyncio
async def test_panelist_custom_confidence_threshold():
    judge_mid = json.dumps({
        "level": 5,
        "confidence_score": 0.65,
        "justification": "Moderate certainty",
        "dissent_notes": "",
    })
    provider = _make_provider(ANALYST_RESPONSE, DEFENDER_RESPONSE, judge_mid)

    # High threshold → should be unevaluated
    evaluator = PanelistEvaluator(provider=provider, confidence_threshold=0.8)
    verdict = await evaluator.run("api_design", {0: "None", 10: "Full"}, "{}")
    assert verdict.evaluated is False

    # Reset provider call count by recreating it
    provider2 = _make_provider(ANALYST_RESPONSE, DEFENDER_RESPONSE, judge_mid)
    # Low threshold → should pass
    evaluator2 = PanelistEvaluator(provider=provider2, confidence_threshold=0.5)
    verdict2 = await evaluator2.run("api_design", {0: "None", 10: "Full"}, "{}")
    assert verdict2.evaluated is True


@pytest.mark.asyncio
async def test_panelist_missing_level_in_judge_response():
    judge_no_level = json.dumps({
        "confidence_score": 0.9,
        "justification": "Forgot to include level",
        "dissent_notes": "",
    })
    provider = _make_provider(ANALYST_RESPONSE, DEFENDER_RESPONSE, judge_no_level)
    evaluator = PanelistEvaluator(provider=provider, confidence_threshold=0.5)

    verdict = await evaluator.run("api_design", {0: "None", 10: "Full"}, "{}")

    assert verdict.level is None
    assert verdict.evaluated is False
    assert "missing_level" in (verdict.reason or "")
