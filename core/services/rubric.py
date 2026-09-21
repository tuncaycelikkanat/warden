"""Rubric-based dynamic category evaluator powered by LLMs."""

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

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
        3: "Katman ayrımı yok; iş mantığı, veri erişimi ve sunum aynı dosyalarda karışık.",
        6: "Katmanlar isimlendirilmiş ama sızıntı var (ör. domain katmanı doğrudan ORM/HTTP'ye bağımlı).",
        9: "Katmanlar net ayrılmış, bağımlılıklar tek yöne akıyor, domain dış dünyadan izole.",
    },
    "quantitative_logic": {
        3: "Sabit eşikli, doğrulanmamış hesaplamalar; geçmiş veri testi yok.",
        6: "Backtest var ama tek dönemde; aşırı uyumlama (overfitting) önlemi yok.",
        9: "Walk-forward doğrulama, parametre duyarlılık analizi ve çoklu metrikli uygunluk fonksiyonu mevcut.",
    },
    "llm_integration": {
        3: "Prompt'lar kodda gömülü, harici metin doğrudan prompt'a enjekte ediliyor, hata yönetimi yok.",
        6: "Prompt'lar ayrıştırılmış, temel hata yönetimi var; ancak enjeksiyon savunması veya maliyet kontrolü eksik.",
        9: "Prompt sanitizasyonu, sağlayıcı yedeklemesi (fallback), maliyet/gecikme takibi ve denetim logu mevcut.",
    },
    "devops_deployment": {
        3: "Ortam bağımlılıkları manuel yönetiliyor, hardcoded sırlar var.",
        6: "Konteynerleştirme var (Docker), ancak ortam değişkenleri statik ve orkestrasyon zayıf.",
        9: "IaC kullanılıyor, tam otomatize pipeline, dinamik sır yönetimi (Vault/AWS Secrets) aktif.",
    },
    "frontend_ux": {
        3: "Erişilebilirlik standartları hiçe sayılmış, durum yönetimi (state) tamamen global ve kaotik.",
        6: "Komponentler ayrıştırılmış ancak gereksiz yeniden render'lar yaygın.",
        9: "İzole edilmiş UI bileşenleri, optimize edilmiş state ağacı, skeleton yükleyiciler ve tam erişilebilirlik.",
    },
    "api_design": {
        3: "Sürümleme yok, HTTP metodları yanlış kullanılıyor, hata kodları her zaman 200 dönüyor.",
        6: "RESTful prensiplerine kısmen uyuluyor ama yetkilendirme ve rate limiting zayıf.",
        9: "Açık OpenAPI spesifikasyonu, katı şema doğrulama, sürümleme ve standartlaştırılmış hata gövdeleri.",
    },
    "concurrency_safety": {
        3: "Kilit (Lock) mekanizmaları yok, thread-unsafe veri yapıları kullanılıyor.",
        6: "Temel asenkron döngüler veya kilitler var ama deadlock veya race condition riski analiz edilmemiş.",
        9: "Aktör modeli, izole kanallar veya sıfır veri paylaşımlı tam güvenli eşzamanlılık kullanılıyor.",
    }
}


@dataclass
class RubricVerdict:
    """Verdict output from LLM rubric evaluation."""
    level: int
    justification: str
    cited_evidence: list[str]

    @classmethod
    def parse(cls, data: dict) -> 'RubricVerdict':
        """Parses a dictionary into a RubricVerdict instance."""
        return cls(
            level=data.get("level", 6),
            justification=data.get("justification", "No justification provided"),
            cited_evidence=data.get("cited_evidence", [])
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

    async def evaluate(self, category_key: str, evidence: CategoryEvidence) -> RubricVerdict:
        """Evaluates a dynamic category against rubrics using provided evidence."""
        import asyncio
        import time

        if category_key not in RUBRICS:
            return RubricVerdict(level=0, justification=f"No rubric for {category_key}", cited_evidence=[])

        rubric = RUBRICS[category_key]
        start_time = time.time()

        # If no Gemini API key, mock the result
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.warning(f"No GEMINI_API_KEY found, mocking rubric evaluation for {category_key}")
            return RubricVerdict(
                level=6,
                justification=f"Mocked justification for {category_key}. Evidence showed {len(evidence.files)} files.",
                cited_evidence=evidence.files[:2]
            )

        from google import genai
        from google.genai import types

        try:
            def _call_gemini() -> tuple[str, str]:
                client = genai.Client(api_key=api_key)
                raw_prompt = self._build_prompt(category_key, rubric, evidence)
                sanitized_res = self.sanitizer.sanitize(raw_prompt)
                prompt = sanitized_res.sanitized_text

                models_to_try = [
                    "gemini-2.5-flash", "gemini-2.5-flash-lite",
                    "gemini-flash-latest", "gemini-3.5-flash", "gemini-3.5-flash-lite"
                ]
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
                                    "Output ONLY valid JSON."
                                ),
                                temperature=0.0
                            )
                        )
                        if response and response.text:
                            return response.text, model_name
                    except Exception as err:
                        last_err = err
                        continue
                raise last_err if last_err else Exception("No response received from Gemini pool")

            raw_text, used_model = await asyncio.to_thread(_call_gemini)
            latency = time.time() - start_time

            # Basic cleanup if Gemini adds markdown formatting
            raw_json = raw_text.replace("```json", "").replace("```", "").strip()
            data = json.loads(raw_json)

            verdict = RubricVerdict.parse(data)
            if verdict.level < 0 or verdict.level > 10:
                raise InvalidRubricLevel(f"Level {verdict.level} out of bounds")

            # Structured Audit Logging & Latency Tracking
            audit_entry = {
                "category": category_key,
                "model": used_model,
                "latency_sec": round(latency, 3),
                "prompt_tokens_est": len(raw_text) // 4,
                "level": verdict.level,
            }
            self.audit_log.append(audit_entry)
            logger.info(f"[LLM AUDIT] {audit_entry}")

            return verdict
        except Exception as e:
            logger.error(f"Rubric evaluation failed: {e}")
            return RubricVerdict(level=5, justification=f"Evaluation failed: {e}", cited_evidence=[])

    def _build_prompt(self, category_key: str, rubric: dict, evidence: CategoryEvidence) -> str:
        rubric_str = "\n".join([f"Level {k}: {v}" for k, v in rubric.items()])
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

Provided Evidence (Inspected from target repository):
{evidence_str}

Evaluate this category. Select a level between 0 and 10. You must justify your choice using ONLY the provided evidence. Cite the specific evidence.

Output format required:
{{
  "level": 6,
  "justification": "Based on the presence of ...",
  "cited_evidence": ["file_a.py", "Finding 1"]
}}
"""
