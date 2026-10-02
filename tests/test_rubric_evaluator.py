"""Comprehensive tests for hardened RubricEvaluatorService and Scorecard Layer 2 integration."""

import json
from unittest.mock import MagicMock, patch

import pytest

from core.services.rubric import (
    CategoryEvidence,
    CodeSnippet,
    RubricEvaluatorService,
    RubricVerdict,
    _extract_json_payload,
)
from core.services.scorecard import ScorecardAggregatorService


def test_rubric_verdict_parse_valid():
    data = {
        "level": 9,
        "justification": "Clear architectural boundary",
        "cited_evidence": ["core/services/rubric.py"],
    }
    verdict = RubricVerdict.parse(data)
    assert verdict.evaluated is True
    assert verdict.level == 9
    assert verdict.justification == "Clear architectural boundary"
    assert verdict.cited_evidence == ["core/services/rubric.py"]


def test_rubric_verdict_parse_missing_level():
    verdict = RubricVerdict.parse({"justification": "Incomplete"})
    assert verdict.evaluated is False
    assert verdict.level is None
    assert verdict.reason == "missing_level_in_response"


def test_rubric_verdict_parse_invalid_level_type():
    verdict = RubricVerdict.parse({"level": "invalid_number"})
    assert verdict.evaluated is False
    assert verdict.level is None
    assert verdict.reason == "invalid_level_type"


def test_extract_json_payload_markdown_and_raw():
    raw_json = '{"level": 8, "justification": "Solid", "cited_evidence": []}'
    assert _extract_json_payload(raw_json)["level"] == 8

    markdown_json = 'Here is the audit result:\n```json\n{"level": 9, "justification": "Exemplary", "cited_evidence": ["file.py"]}\n```\nHope this helps.'
    assert _extract_json_payload(markdown_json)["level"] == 9

    embedded_json = 'Preamble: {"level": 7, "justification": "Good"} Postscript'
    assert _extract_json_payload(embedded_json)["level"] == 7


def test_rubric_build_prompt_calibration_rule():
    evaluator = RubricEvaluatorService()
    evidence = CategoryEvidence(
        files=["core/services/rubric.py"],
        metrics={"lines": 150},
        findings=["Prompt sanitizer active"],
    )
    prompt = evaluator._build_prompt("llm_integration", {0: "None", 9: "Advanced"}, evidence)
    assert "Category: llm_integration" in prompt
    assert "Calibration Rule:" in prompt
    assert "core/services/rubric.py" in prompt
    assert "Prompt sanitizer active" in prompt


@pytest.mark.asyncio
async def test_evaluate_unknown_category():
    evaluator = RubricEvaluatorService()
    evidence = CategoryEvidence(files=[], metrics={}, findings=[])
    verdict = await evaluator.evaluate("quantum_computing", evidence)
    assert verdict.evaluated is False
    assert verdict.level == 0
    assert verdict.reason == "unknown_category"


@pytest.mark.asyncio
async def test_evaluate_missing_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    evaluator = RubricEvaluatorService()
    evidence = CategoryEvidence(
        files=["main.py", "service.py"],
        metrics={},
        findings=["Good architecture"],
    )
    verdict = await evaluator.evaluate("api_design", evidence)
    assert verdict.evaluated is False
    assert verdict.level is None
    assert verdict.reason == "missing_api_key"
    assert "GEMINI_API_KEY not configured" in (verdict.justification or "")


@pytest.mark.asyncio
async def test_evaluate_with_mocked_gemini_client(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-xyz")
    evaluator = RubricEvaluatorService()
    evidence = CategoryEvidence(
        files=["core/services/rubric.py"],
        metrics={},
        findings=["IaC implemented"],
    )

    mock_resp = MagicMock()
    mock_resp.text = json.dumps({
        "level": 9,
        "justification": "Verified comprehensive prompt sanitization and fallback pool.",
        "cited_evidence": ["core/services/rubric.py"]
    })
    mock_usage = MagicMock()
    mock_usage.prompt_token_count = 350
    mock_usage.candidates_token_count = 45
    mock_resp.usage_metadata = mock_usage

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_resp

    with patch("google.genai.Client", return_value=mock_client):
        verdict = await evaluator.evaluate("llm_integration", evidence)
        assert verdict.evaluated is True
        assert verdict.level == 9
        assert "Verified comprehensive" in verdict.justification
        assert verdict.citation_warning is None

        assert len(evaluator.audit_log) == 1
        entry = evaluator.audit_log[0]
        assert entry["category"] == "llm_integration"
        assert entry["level"] == 9
        assert entry["input_tokens"] == 350
        assert entry["output_tokens"] == 45


@pytest.mark.asyncio
async def test_evaluate_gemini_exception_returns_evaluated_false(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-xyz")
    evaluator = RubricEvaluatorService()
    evidence = CategoryEvidence(files=[], metrics={}, findings=[])

    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = RuntimeError("Service Unavailable 503")

    with patch("google.genai.Client", return_value=mock_client):
        verdict = await evaluator.evaluate("llm_integration", evidence)
        assert verdict.evaluated is False
        assert verdict.level is None
        assert "evaluation_error" in (verdict.reason or "")
        assert "Service Unavailable" in (verdict.justification or "")


def test_citation_validation_detects_hallucination():
    evaluator = RubricEvaluatorService()
    evidence = CategoryEvidence(
        files=["src/app.py", "src/auth.py"],
        metrics={},
        findings=["Route definitions found"],
        code_snippets=[CodeSnippet(file="src/app.py", line_start=1, line_end=5, code="", context="")],
    )

    # Legitimate citation
    v_clean = RubricVerdict(level=8, justification="Good", cited_evidence=["src/app.py", "Finding 1"], evaluated=True)
    v_validated = evaluator._validate_citations(v_clean, evidence)
    assert v_validated.citation_warning is None

    # Hallucinated citation
    v_hallucinated = RubricVerdict(
        level=8,
        justification="Good",
        cited_evidence=["src/app.py", "completely/fake/nonexistent_file.py"],
        evaluated=True
    )
    v_warned = evaluator._validate_citations(v_hallucinated, evidence)
    assert v_warned.citation_warning is not None
    assert "nonexistent_file.py" in v_warned.citation_warning


def test_scorecard_layer2_unmeasured_weight_redistribution():
    scorecard = ScorecardAggregatorService()
    layer1_data = {
        "security": [],
        "dependencies": [],
        "complexity": {},
        "lint": {},
        "leaks": [],
        "coverage": 80.0,
        "docs": {},
        "resilience": [],
        "license_compliance": 100.0,
        "type_safety": 100.0,
        "test_quality": 100.0,
        "cicd_presence": 100.0,
        "docker_readiness": 100.0,
        "commit_hygiene": 100.0,
    }
    # All Layer 2 categories unmeasured (e.g. no API key)
    layer2_data = [
        {"category": "api_design", "rubric_verdict": {"level": None, "evaluated": False, "reason": "missing_api_key"}},
        {"category": "devops_deployment", "rubric_verdict": {"level": None, "evaluated": False, "reason": "missing_api_key"}},
    ]

    result = scorecard.calculate(layer1_data, layer2_data)

    assert result.weight_redistributed_to_layer1 is True
    assert result.layer2_score is None
    # Total score should exactly match layer 1 score (100% weight)
    assert result.total_score == result.layer1_score


def test_scorecard_layer2_partial_measured():
    scorecard = ScorecardAggregatorService()
    layer1_data = {
        "security": [],
        "dependencies": [],
        "complexity": {},
        "lint": {},
        "leaks": [],
        "coverage": 80.0,
        "docs": {},
        "resilience": [],
        "license_compliance": 100.0,
        "type_safety": 100.0,
        "test_quality": 100.0,
        "cicd_presence": 100.0,
        "docker_readiness": 100.0,
        "commit_hygiene": 100.0,
    }
    # One evaluated category (level=9 -> 90 pts), one failed (evaluated=False)
    layer2_data = [
        {"category": "api_design", "rubric_verdict": {"level": 9, "evaluated": True}},
        {"category": "devops_deployment", "rubric_verdict": {"level": None, "evaluated": False, "reason": "timeout"}},
    ]

    result = scorecard.calculate(layer1_data, layer2_data)

    assert result.weight_redistributed_to_layer1 is False
    assert result.layer2_score == 90
    expected_total = round((result.layer1_score * 0.60) + (90 * 0.40))
    assert result.total_score == expected_total


# ── New tests: confidence_score field & panelist integration ───────────────────

def test_rubric_verdict_has_confidence_score_field():
    """RubricVerdict should carry an optional confidence_score field."""
    verdict = RubricVerdict(level=7, justification="Good", confidence_score=0.85)
    assert verdict.confidence_score == pytest.approx(0.85)


def test_rubric_verdict_confidence_score_defaults_to_none():
    verdict = RubricVerdict(level=7, justification="Good")
    assert verdict.confidence_score is None


def test_rubric_verdict_parse_does_not_set_confidence_score():
    """parse() originates from single-agent path and should leave confidence_score as None."""
    data = {"level": 8, "justification": "Solid", "cited_evidence": []}
    verdict = RubricVerdict.parse(data)
    assert verdict.confidence_score is None


@pytest.mark.asyncio
async def test_evaluate_panelist_mode_produces_confidence_score(monkeypatch):
    """When panelist mode is active, evaluate() returns a verdict with confidence_score set."""
    import json as _json

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-test")
    monkeypatch.setenv("WARDEN_LLM_PANELIST_MODE", "true")

    analyst_resp = _json.dumps({
        "issues": ["No timeout"], "risk_level": "medium", "supporting_evidence": ["db.py"],
    })
    defender_resp = _json.dumps({
        "false_positives": [], "missing_evidence": [], "upheld_issues": ["No timeout"],
    })
    judge_resp = _json.dumps({
        "level": 7, "confidence_score": 0.88,
        "justification": "One upheld issue", "dissent_notes": "",
    })

    async def fake_generate_json(prompt, system_instruction, **kwargs):
        call_count["n"] += 1
        responses = [analyst_resp, defender_resp, judge_resp]
        return responses[call_count["n"] - 1], "mock-model"

    call_count = {"n": 0}

    # Patch the factory to return a mock provider
    mock_provider = MagicMock()
    mock_provider.generate_json = fake_generate_json

    evidence = CategoryEvidence(
        files=["db.py"],
        metrics={"coverage": 80.0},
        findings=["No DB timeout configured"],
    )

    with patch(
        "core.llm.factory.LLMProviderFactory.create",
        return_value=mock_provider,
    ):
        evaluator = RubricEvaluatorService()
        verdict = await evaluator.evaluate("api_design", evidence, use_panelist=True)

    assert verdict.evaluated is True
    assert verdict.level == 7
    assert verdict.confidence_score is not None
    assert verdict.confidence_score == pytest.approx(0.88, abs=0.01)


@pytest.mark.asyncio
async def test_evaluate_use_panelist_false_overrides_env(monkeypatch):
    """use_panelist=False should bypass panelist even if env var is true."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setenv("WARDEN_LLM_PANELIST_MODE", "true")

    # No GEMINI_API_KEY validation needed since we mock the Gemini call
    mock_response = MagicMock()
    mock_response.text = '{"level": 8, "justification": "Fine", "cited_evidence": []}'
    mock_response.usage_metadata = None

    evidence = CategoryEvidence(files=[], metrics={}, findings=[])

    with patch(
        "core.services.rubric.RubricEvaluatorService._evaluate_single",
    ) as mock_single, patch(
        "core.services.rubric.RubricEvaluatorService._evaluate_panelist",
    ) as mock_panelist:
        mock_single.return_value = RubricVerdict(level=8, justification="Fine")
        evaluator = RubricEvaluatorService()
        await evaluator.evaluate("api_design", evidence, use_panelist=False)

    mock_single.assert_called_once()
    mock_panelist.assert_not_called()


@pytest.mark.asyncio
async def test_evaluate_use_panelist_true_overrides_env(monkeypatch):
    """use_panelist=True should engage panelist even if env var is false."""
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setenv("WARDEN_LLM_PANELIST_MODE", "false")

    evidence = CategoryEvidence(files=[], metrics={}, findings=[])

    with patch(
        "core.services.rubric.RubricEvaluatorService._evaluate_single",
    ) as mock_single, patch(
        "core.services.rubric.RubricEvaluatorService._evaluate_panelist",
    ) as mock_panelist:
        mock_panelist.return_value = RubricVerdict(level=7, justification="Panelist", confidence_score=0.8)
        evaluator = RubricEvaluatorService()
        await evaluator.evaluate("api_design", evidence, use_panelist=True)

    mock_panelist.assert_called_once()
    mock_single.assert_not_called()
