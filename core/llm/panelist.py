"""Multi-Agent Panelist Evaluator for WARDEN Layer 2 rubric assessment.

Architecture
------------
Instead of a single LLM call that may hallucinate, three specialised agents
collaborate in a structured debate:

  Analyst  ──►  Defender  ──►  Judge
     │               │            │
  Findings     Counter-args   Final verdict
                               + confidence_score

This reduces false-positive rates and produces a calibrated confidence score
that the caller can use to decide how much weight to give the LLM verdict.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from core.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_json(raw: str) -> dict[str, Any]:
    """Robustly extracts the first JSON object from an LLM response."""
    text = raw.strip()
    # Try direct parse
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # Try stripping markdown fences
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Fallback: find outermost braces
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start: end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"No valid JSON object found in LLM response: {text[:300]}")


# ── Result dataclasses ─────────────────────────────────────────────────────────

@dataclass
class AnalystFindings:
    """Raw output from the Analyst agent."""
    issues: list[str] = field(default_factory=list)
    risk_level: str = "unknown"   # "low" | "medium" | "high" | "critical"
    supporting_evidence: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def parse(cls, data: dict[str, Any]) -> "AnalystFindings":
        return cls(
            issues=data.get("issues", []),
            risk_level=str(data.get("risk_level", "unknown")).lower(),
            supporting_evidence=data.get("supporting_evidence", []),
            raw=data,
        )


@dataclass
class DefenderReport:
    """Raw output from the Defender agent."""
    false_positives: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    upheld_issues: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def parse(cls, data: dict[str, Any]) -> "DefenderReport":
        return cls(
            false_positives=data.get("false_positives", []),
            missing_evidence=data.get("missing_evidence", []),
            upheld_issues=data.get("upheld_issues", []),
            raw=data,
        )


@dataclass
class PanelistVerdict:
    """Final verdict produced by the Judge agent."""
    level: int | None
    confidence_score: float          # 0.0 – 1.0
    justification: str
    dissent_notes: str = ""          # Summary of disagreements
    evaluated: bool = True
    reason: str | None = None
    analyst_findings: AnalystFindings | None = None
    defender_report: DefenderReport | None = None
    latency_sec: float = 0.0

    @classmethod
    def skipped(cls, reason: str) -> "PanelistVerdict":
        return cls(
            level=None,
            confidence_score=0.0,
            justification=f"Panelist evaluation skipped: {reason}",
            evaluated=False,
            reason=reason,
        )

    @classmethod
    def error(cls, err: Exception) -> "PanelistVerdict":
        return cls(
            level=None,
            confidence_score=0.0,
            justification=f"Panelist evaluation error: {err}",
            evaluated=False,
            reason=f"evaluation_error: {err}",
        )


# ── Prompt templates ───────────────────────────────────────────────────────────

_ANALYST_SYSTEM = (
    "You are a senior code-quality analyst. "
    "Your job is to identify issues in the provided code evidence "
    "based on the rubric anchors. Be thorough but precise. "
    "Output ONLY valid JSON matching the schema exactly."
)

_ANALYST_PROMPT_TMPL = """\
Category: {category_key}

Rubric Anchors:
{rubric_str}

Evidence (from the repository under review):
{evidence_str}

Analyse the evidence against the rubric. List ALL issues you find.

Output JSON schema (no extra keys):
{{
  "issues": ["<issue 1>", "<issue 2>"],
  "risk_level": "low|medium|high|critical",
  "supporting_evidence": ["<file or finding that supports each issue>"]
}}
"""

_DEFENDER_SYSTEM = (
    "You are a senior code-quality advocate (devil's advocate). "
    "Your job is to challenge the analyst's findings: identify false positives, "
    "point out missing context, and flag any evidence the analyst overlooked. "
    "Also list issues from the analyst that you agree are valid. "
    "Output ONLY valid JSON matching the schema exactly."
)

_DEFENDER_PROMPT_TMPL = """\
Category: {category_key}

Rubric Anchors:
{rubric_str}

Evidence (from the repository under review):
{evidence_str}

Analyst Findings:
{analyst_json}

Challenge the analyst. For each issue: is it a real problem or a false positive?
Are there strengths the analyst missed? List missing evidence if any.

Output JSON schema (no extra keys):
{{
  "false_positives": ["<issue text that is actually NOT a problem>"],
  "missing_evidence": ["<file or metric the analyst should have considered>"],
  "upheld_issues": ["<issue text from analyst that IS a genuine problem>"]
}}
"""

_JUDGE_SYSTEM = (
    "You are the chief technical auditor. "
    "You have read both the analyst's findings and the defender's counter-arguments. "
    "Your job is to weigh both sides and assign the final rubric level. "
    "You must also provide a confidence_score between 0.0 and 1.0: "
    "1.0 means analyst and defender fully agreed; values below 0.5 indicate "
    "high uncertainty. "
    "Output ONLY valid JSON matching the schema exactly."
)

_JUDGE_PROMPT_TMPL = """\
Category: {category_key}

Rubric Anchors:
{rubric_str}

Evidence (from the repository under review):
{evidence_str}

Analyst Findings:
{analyst_json}

Defender's Counter-Arguments:
{defender_json}

Weigh both sides. Assign the final rubric level (0–10) and a confidence score.

Output JSON schema (no extra keys):
{{
  "level": 7,
  "confidence_score": 0.85,
  "justification": "<why you chose this level>",
  "dissent_notes": "<brief summary of unresolved disagreements, or empty string>"
}}
"""


# ── PanelistEvaluator ──────────────────────────────────────────────────────────

class PanelistEvaluator:
    """Orchestrates the Analyst → Defender → Judge debate chain.

    Parameters
    ----------
    provider:
        Any configured ``BaseLLMProvider`` instance.
    confidence_threshold:
        Verdicts with ``confidence_score`` below this value are marked
        ``evaluated=False`` so the caller can fall back to Layer 1.
    timeout_sec:
        Per-agent call timeout in seconds.
    """

    def __init__(
        self,
        provider: BaseLLMProvider,
        confidence_threshold: float = 0.5,
        timeout_sec: int = 60,
    ) -> None:
        self._provider = provider
        self._confidence_threshold = max(0.0, min(1.0, confidence_threshold))
        self._timeout_sec = timeout_sec

    # ── Public API ─────────────────────────────────────────────────────────────

    async def run(
        self,
        category_key: str,
        rubric: dict[int, str],
        evidence_str: str,
    ) -> PanelistVerdict:
        """Runs the full Analyst → Defender → Judge chain.

        Parameters
        ----------
        category_key:
            Rubric category identifier (e.g. ``"api_design"``).
        rubric:
            Dictionary mapping level (int) to description (str).
        evidence_str:
            Pre-serialised JSON evidence string (same as used in single-agent mode).

        Returns
        -------
        PanelistVerdict
            Final verdict with level, confidence_score, and chain metadata.
        """
        t0 = time.monotonic()
        rubric_str = "\n".join(f"Level {k}: {v}" for k, v in sorted(rubric.items()))

        try:
            # ── Step 1: Analyst ──────────────────────────────────────────────
            analyst_findings = await self._call_analyst(category_key, rubric_str, evidence_str)

            # ── Step 2: Defender ─────────────────────────────────────────────
            defender_report = await self._call_defender(
                category_key, rubric_str, evidence_str, analyst_findings
            )

            # ── Step 3: Judge ────────────────────────────────────────────────
            verdict = await self._call_judge(
                category_key, rubric_str, evidence_str, analyst_findings, defender_report
            )

        except Exception as exc:
            logger.error("PanelistEvaluator chain failed for '%s': %s", category_key, exc)
            return PanelistVerdict.error(exc)

        verdict.latency_sec = round(time.monotonic() - t0, 3)
        verdict.analyst_findings = analyst_findings
        verdict.defender_report = defender_report

        # Apply confidence threshold
        if verdict.confidence_score < self._confidence_threshold:
            verdict.evaluated = False
            verdict.reason = (
                f"confidence_below_threshold: {verdict.confidence_score:.2f} "
                f"< {self._confidence_threshold:.2f}"
            )
            logger.warning(
                "[Panelist] '%s' verdict has low confidence %.2f — marking as unevaluated.",
                category_key,
                verdict.confidence_score,
            )
        else:
            logger.info(
                "[Panelist] '%s' → level=%s confidence=%.2f latency=%.2fs",
                category_key,
                verdict.level,
                verdict.confidence_score,
                verdict.latency_sec,
            )

        return verdict

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _call_analyst(
        self, category_key: str, rubric_str: str, evidence_str: str
    ) -> AnalystFindings:
        prompt = _ANALYST_PROMPT_TMPL.format(
            category_key=category_key,
            rubric_str=rubric_str,
            evidence_str=evidence_str,
        )
        raw, model = await self._provider.generate_json(
            prompt=prompt,
            system_instruction=_ANALYST_SYSTEM,
            timeout_sec=self._timeout_sec,
        )
        logger.debug("[Panelist/Analyst] model=%s raw=%s", model, raw[:200])
        return AnalystFindings.parse(_extract_json(raw))

    async def _call_defender(
        self,
        category_key: str,
        rubric_str: str,
        evidence_str: str,
        analyst: AnalystFindings,
    ) -> DefenderReport:
        prompt = _DEFENDER_PROMPT_TMPL.format(
            category_key=category_key,
            rubric_str=rubric_str,
            evidence_str=evidence_str,
            analyst_json=json.dumps(analyst.raw, indent=2),
        )
        raw, model = await self._provider.generate_json(
            prompt=prompt,
            system_instruction=_DEFENDER_SYSTEM,
            timeout_sec=self._timeout_sec,
        )
        logger.debug("[Panelist/Defender] model=%s raw=%s", model, raw[:200])
        return DefenderReport.parse(_extract_json(raw))

    async def _call_judge(
        self,
        category_key: str,
        rubric_str: str,
        evidence_str: str,
        analyst: AnalystFindings,
        defender: DefenderReport,
    ) -> PanelistVerdict:
        prompt = _JUDGE_PROMPT_TMPL.format(
            category_key=category_key,
            rubric_str=rubric_str,
            evidence_str=evidence_str,
            analyst_json=json.dumps(analyst.raw, indent=2),
            defender_json=json.dumps(defender.raw, indent=2),
        )
        raw, model = await self._provider.generate_json(
            prompt=prompt,
            system_instruction=_JUDGE_SYSTEM,
            timeout_sec=self._timeout_sec,
        )
        logger.debug("[Panelist/Judge] model=%s raw=%s", model, raw[:200])
        data = _extract_json(raw)

        raw_level = data.get("level")
        try:
            level = int(raw_level)
            level = max(0, min(10, level))
        except (TypeError, ValueError):
            level = None

        raw_conf = data.get("confidence_score", 0.5)
        try:
            confidence = float(raw_conf)
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.5

        return PanelistVerdict(
            level=level,
            confidence_score=confidence,
            justification=str(data.get("justification", "No justification provided")),
            dissent_notes=str(data.get("dissent_notes", "")),
            evaluated=level is not None,
            reason=None if level is not None else "missing_level_in_judge_response",
        )
