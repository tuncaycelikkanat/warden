import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)



@dataclass
class CodeSnippet:
    """A relevant source code excerpt provided as ground-truth evidence."""
    file: str
    line_start: int
    line_end: int
    code: str
    context: str


@dataclass
class CategoryEvidence:
    """Represents evidence artifacts submitted for rubric evaluation."""
    files: list[str]
    metrics: dict[str, Any]
    findings: list[str]
    code_snippets: list[CodeSnippet] = field(default_factory=list)
    evidence_collection_status: str = "ok"  # "ok" | "partial_error" | "no_evidence_found"
    collection_errors: list[str] = field(default_factory=list)


RUBRICS = {
    "architectural_discipline": {
        0: "Hiçbir mimari katmanlaşma veya modülerlik yok; tüm mantık tek yerde düzensiz.",
        3: "Katman ayrımı yok; iş mantığı, veri erişimi ve sunum aynı dosyalarda karışık.",
        6: "Katmanlar isimlendirilmiş ama sızıntı var (ör. domain katmanı doğrudan ORM/HTTP'ye bağımlı).",
        9: "Katmanlar net ayrılmış, bağımlılıklar tek yöne akıyor, domain dış dünyadan izole.",
        10: "Seviye 9'un ötesinde, tam izole domain, açık port-adapter mimarisi ve sıfır sızıntı.",
    },
    "quantitative_logic": {
        0: "Hesaplama doğrulaması, test veya istatistiksel kontrol tamamen yok.",
        3: "Sabit eşikli, doğrulanmamış hesaplamalar; geçmiş veri testi yok.",
        6: "Backtest var ama tek dönemde; aşırı uyumlama (overfitting) önlemi yok.",
        9: "Walk-forward doğrulama, parametre duyarlılık analizi ve çoklu metrikli uygunluk fonksiyonu mevcut.",
        10: "Seviye 9'un ötesinde, tam kapsamlı cross-validation, walk-forward ve risk duyarlılığı.",
    },
    "llm_integration": {
        0: "LLM entegrasyonu tamamen kontrolsüz; ham kullanıcı girdisi doğrudan modele gönderiliyor.",
        3: "Prompt'lar kodda gömülü, harici metin doğrudan prompt'a enjekte ediliyor, hata yönetimi yok.",
        6: "Prompt'lar ayrıştırılmış, temel hata yönetimi var; ancak enjeksiyon savunması veya maliyet kontrolü eksik.",
        9: "Prompt sanitizasyonu, sağlayıcı yedeklemesi (fallback), maliyet/gecikme takibi ve denetim logu mevcut.",
        10: "Seviye 9'un ötesinde, çoklu model fallback havuzu, çift yönlü prompt savunması ve tam token denetimi.",
    },
    "devops_deployment": {
        0: "Dağıtım ve ortam otomasyonu yok; manuel süreçler ve hardcoded ortamlar.",
        3: "Ortam bağımlılıkları manuel yönetiliyor, hardcoded sırlar var.",
        6: "Konteynerleştirme var (Docker), ancak ortam değişkenleri statik ve orkestrasyon zayıf.",
        9: "IaC kullanılıyor, tam otomatize pipeline, dinamik sır yönetimi (Vault/AWS Secrets) aktif.",
        10: "Seviye 9'un ötesinde, multi-stage non-root containerlar, tam IaC ve sıfır sır sızıntısı.",
    },
    "frontend_ux": {
        0: "Kullanıcı arayüzü kontrolsüz, erişilebilirlik tamamen yok ve yapısal durum kaotik.",
        3: "Erişilebilirlik standartları hiçe sayılmış, durum yönetimi (state) tamamen global ve kaotik.",
        6: "Komponentler ayrıştırılmış ancak gereksiz yeniden render'lar yaygın.",
        9: "İzole edilmiş UI bileşenleri, optimize edilmiş state ağacı, skeleton yükleyiciler ve tam erişilebilirlik.",
        10: "Seviye 9'un ötesinde, kusursuz a11y (WCAG AAA), optimize state mimarisi ve tam tip güvenliği.",
    },
    "api_design": {
        0: "API standartları yok; rastgele HTTP metodları, durum kodları ve doğrulanmamış gövdeler.",
        3: "Sürümleme yok, HTTP metodları yanlış kullanılıyor, hata kodları her zaman 200 dönüyor.",
        6: "RESTful prensiplerine kısmen uyuluyor ama yetkilendirme ve rate limiting zayıf.",
        9: "Açık OpenAPI spesifikasyonu, katı şema doğrulama, sürümleme ve standartlaştırılmış hata gövdeleri.",
        10: "Seviye 9'un ötesinde, tam OpenAPI uyumu, katı Pydantic şemaları, typed HTTPException ve rate limit.",
    },
    "concurrency_safety": {
        0: "Eşzamanlılık kontrolsüz; açık yarış durumları (race conditions) ve thread sızıntıları.",
        3: "Kilit (Lock) mekanizmaları yok, thread-unsafe veri yapıları kullanılıyor.",
        6: "Temel asenkron döngüler veya kilitler var ama deadlock veya race condition riski analiz edilmemiş.",
        9: "Aktör modeli, izole kanallar veya sıfır veri paylaşımlı tam güvenli eşzamanlılık kullanılıyor.",
        10: "Seviye 9'un ötesinde, tam asenkron kaynak izolasyonu, kilit korumalı kritik bölümler ve sıfır yarış durumu.",
    },
}


def _extract_json_payload(raw_text: str) -> dict[str, Any]:
    """Robustly extracts and parses JSON payload from model response."""
    cleaned = raw_text.strip()
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if match:
        data = json.loads(match.group(1))
        if isinstance(data, dict):
            return data

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        data = json.loads(cleaned[start : end + 1])
        if isinstance(data, dict):
            return data

    raise json.JSONDecodeError("No valid JSON object found in response", raw_text, 0)


@dataclass
class RubricVerdict:
    """Verdict output from LLM rubric evaluation."""
    level: int | None
    justification: str | None
    cited_evidence: list[str] = field(default_factory=list)
    evaluated: bool = True
    reason: str | None = None
    citation_warning: str | None = None

    @classmethod
    def parse(cls, data: dict[str, Any]) -> 'RubricVerdict':
        """Parses a dictionary into a RubricVerdict instance with robust validation."""
        raw_level = data.get("level")
        if raw_level is None:
            return cls(
                level=None,
                justification=data.get("justification"),
                cited_evidence=[],
                evaluated=False,
                reason="missing_level_in_response",
            )
        try:
            level = int(raw_level)
            level = max(0, min(10, level))
        except (ValueError, TypeError):
            return cls(
                level=None,
                justification=data.get("justification"),
                cited_evidence=[],
                evaluated=False,
                reason="invalid_level_type",
            )

        cited = data.get("cited_evidence", [])
        return cls(
            level=level,
            justification=data.get("justification", "No justification provided"),
            cited_evidence=cited if isinstance(cited, list) else [],
            evaluated=True,
        )


class InvalidRubricLevel(Exception):
    """Raised when an LLM evaluation produces a score outside 0-10."""


class RubricEvaluatorService:
    """Evaluates architectural qualities against anchored rubrics using Gemini LLM."""

    def __init__(self) -> None:
        """Initializes the prompt sanitizer and audit log registry."""
        from core.utils.prompt_sanitizer import PromptSanitizer
        self.sanitizer = PromptSanitizer()
        self.audit_log: list[dict[str, Any]] = []

    def _has_valid_api_key(self) -> bool:
        """Checks if a non-empty GEMINI_API_KEY is configured in the environment."""
        key = os.getenv("GEMINI_API_KEY")
        return bool(key and key.strip())



    def _validate_citations(
        self, verdict: RubricVerdict, evidence: CategoryEvidence
    ) -> RubricVerdict:
        """Validates that cited evidence references actually exist in the supplied evidence."""
        if not verdict.evaluated or not verdict.cited_evidence:
            return verdict

        valid_files = set(evidence.files)
        valid_basenames = {Path(f).name for f in evidence.files}
        snippet_files = {s.file for s in evidence.code_snippets}
        snippet_basenames = {Path(s.file).name for s in evidence.code_snippets}
        valid_findings = {f"Finding {i+1}" for i in range(len(evidence.findings))}

        unverified: list[str] = []
        for cite in verdict.cited_evidence:
            cite_str = str(cite).strip()
            if (
                cite_str in valid_files
                or cite_str in valid_basenames
                or cite_str in snippet_files
                or cite_str in snippet_basenames
                or cite_str in valid_findings
                or any(f in cite_str or cite_str in f for f in evidence.files)
                or any(f in cite_str or cite_str in f for f in evidence.findings)
            ):
                continue
            unverified.append(cite_str)

        if unverified:
            verdict.citation_warning = (
                f"{len(unverified)} cited reference(s) could not be matched to supplied evidence: {unverified}"
            )
            logger.warning(f"Possible citation hallucination for {verdict.level}: {unverified}")

        return verdict

    async def evaluate(self, category_key: str, evidence: CategoryEvidence) -> RubricVerdict:
        """Evaluates a dynamic category against rubrics using provided evidence."""
        if category_key not in RUBRICS:
            return RubricVerdict(
                level=0,
                justification=f"No rubric for {category_key}",
                cited_evidence=[],
                evaluated=False,
                reason="unknown_category",
            )

        rubric = RUBRICS[category_key]
        start_time = time.time()

        if not self._has_valid_api_key():
            logger.warning(
                f"No GEMINI_API_KEY found — category '{category_key}' cannot be evaluated"
            )
            return RubricVerdict(
                level=None,
                justification="Evaluation skipped: GEMINI_API_KEY not configured",
                cited_evidence=[],
                evaluated=False,
                reason="missing_api_key",
            )

        api_key = os.getenv("GEMINI_API_KEY")

        from google import genai
        from google.genai import types

        try:
            def _call_gemini() -> tuple[str, str, Any]:
                client = genai.Client(api_key=api_key)
                raw_prompt = self._build_prompt(category_key, rubric, evidence)
                sanitized_res = self.sanitizer.sanitize(raw_prompt)
                prompt = sanitized_res.sanitized_text

                from core.config.llm_config import LLMConfig
                llm_cfg = LLMConfig.from_env()
                models_to_try = llm_cfg.models

                last_err = None
                for model_name in models_to_try:
                    try:
                        response = client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                system_instruction=(
                                    "You are an expert technical auditor. "
                                    "Evaluate the project based STRICTLY on the provided rubric and evidence. "
                                    "For intermediate levels between defined anchors, calibrate proportionally. "
                                    "Output ONLY valid JSON matching the schema."
                                ),
                                temperature=llm_cfg.temperature,
                                response_mime_type="application/json",
                            ),
                        )
                        if response and response.text:
                            return response.text, model_name, response
                    except Exception as err:
                        logger.warning(f"Model '{model_name}' başarısız: {err}")
                        last_err = err
                        continue
                raise last_err if last_err else Exception("No response received from Gemini pool")

            raw_text, used_model, response_obj = await asyncio.to_thread(_call_gemini)
            latency = time.time() - start_time

            data = _extract_json_payload(raw_text)
            verdict = RubricVerdict.parse(data)

            if verdict.evaluated and verdict.level is not None:
                if verdict.level < 0 or verdict.level > 10:
                    raise InvalidRubricLevel(f"Level {verdict.level} out of bounds")

            # Extract real token usage if available
            input_tokens = None
            output_tokens = None
            if hasattr(response_obj, "usage_metadata") and response_obj.usage_metadata:
                input_tokens = getattr(response_obj.usage_metadata, "prompt_token_count", None)
                output_tokens = getattr(response_obj.usage_metadata, "candidates_token_count", None)

            # Structured Audit Logging & Latency Tracking
            audit_entry = {
                "category": category_key,
                "model": used_model,
                "latency_sec": round(latency, 3),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "prompt_tokens_est": len(raw_text) // 4,
                "level": verdict.level,
                "evaluated": verdict.evaluated,
            }
            self.audit_log.append(audit_entry)
            logger.info(f"[LLM AUDIT] {audit_entry}")

            return self._validate_citations(verdict, evidence)
        except Exception as e:
            logger.error(f"Rubric evaluation failed for {category_key}: {e}")
            return RubricVerdict(
                level=None,
                justification=f"Evaluation failed: {e}",
                cited_evidence=[],
                evaluated=False,
                reason=f"evaluation_error: {e}",
            )

    def _build_prompt(self, category_key: str, rubric: dict[int, str], evidence: CategoryEvidence) -> str:
        """Constructs LLM prompt with rubric anchors, proportional calibration rule, and evidence."""
        rubric_str = "\n".join([f"Level {k}: {v}" for k, v in sorted(rubric.items())])
        snippets_payload = [
            {
                "file": s.file,
                "lines": f"{s.line_start}-{s.line_end}",
                "context": s.context,
                "code": s.code,
            }
            for s in evidence.code_snippets
        ]
        evidence_dict = {
            "status": evidence.evidence_collection_status,
            "errors": evidence.collection_errors,
            "files_involved": evidence.files,
            "metrics": evidence.metrics,
            "key_findings": evidence.findings,
            "code_snippets": snippets_payload,
        }
        evidence_str = json.dumps(evidence_dict, indent=2)

        return f"""
Category: {category_key}

Rubric Anchors:
{rubric_str}

Calibration Rule:
- Defined anchors provide canonical baseline descriptions.
- For intermediate levels (e.g. 1, 2, 4, 5, 7, 8), calibrate proportionally between the closest anchors.

Provided Evidence (Inspected from target repository):
{evidence_str}

Evaluate this category. Select an integer level between 0 and 10. You must justify your choice using ONLY the provided evidence. Cite the specific evidence.

Output format required (valid JSON):
{{
  "level": 6,
  "justification": "Based on the presence of ...",
  "cited_evidence": ["file_a.py", "Finding 1"]
}}
"""
