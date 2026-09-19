import os
import json
import logging
from dataclasses import dataclass
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

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
class CategoryEvidence:
    files: List[str]
    metrics: Dict[str, Any]
    findings: List[str]

@dataclass
class RubricVerdict:
    level: int
    justification: str
    cited_evidence: List[str]

    @classmethod
    def parse(cls, data: dict) -> 'RubricVerdict':
        return cls(
            level=data.get("level", 6),
            justification=data.get("justification", "No justification provided"),
            cited_evidence=data.get("cited_evidence", [])
        )

class InvalidRubricLevel(Exception):
    pass

class RubricEvaluatorService:
    async def evaluate(self, category_key: str, evidence: CategoryEvidence) -> RubricVerdict:
        import asyncio
        if category_key not in RUBRICS:
            return RubricVerdict(level=0, justification=f"No rubric for {category_key}", cited_evidence=[])
            
        rubric = RUBRICS[category_key]
        
        # If no Gemini API key, mock the result
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.warning(f"No GEMINI_API_KEY found, mocking rubric evaluation for {category_key}")
            # Mocking it to return 6
            return RubricVerdict(
                level=6,
                justification=f"Mocked justification for {category_key}. Evidence showed {len(evidence.files)} files.",
                cited_evidence=evidence.files[:2]
            )
            
        from google import genai
        from google.genai import types
        
        try:
            # We must use asyncio.to_thread because the genai client is mostly synchronous in basic usage,
            # or we can use the async client if available. Let's use standard generate_content in a thread.
            def _call_gemini():
                client = genai.Client(api_key=api_key)
                prompt = self._build_prompt(category_key, rubric, evidence)
                response = client.models.generate_content(
                    model='gemini-2.5-pro',
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction="You are an expert technical auditor. Evaluate the project based STRICTLY on the provided rubric and evidence. Output ONLY valid JSON.",
                        temperature=0.0
                    )
                )
                return response.text
                
            raw_text = await asyncio.to_thread(_call_gemini)
            
            # Basic cleanup if Gemini adds markdown formatting
            raw_json = raw_text.replace("```json", "").replace("```", "").strip()
            data = json.loads(raw_json)
            
            verdict = RubricVerdict.parse(data)
            # Allowed levels: exact rubric anchors + midpoints (4, 5, 7, 8)
            if verdict.level < 0 or verdict.level > 10:
                raise InvalidRubricLevel(f"Level {verdict.level} out of bounds")
                
            return verdict
        except Exception as e:
            logger.error(f"Rubric evaluation failed: {e}")
            return RubricVerdict(level=5, justification=f"Evaluation failed: {e}", cited_evidence=[])

    def _build_prompt(self, category_key: str, rubric: dict, evidence: CategoryEvidence) -> str:
        rubric_str = "\n".join([f"Level {k}: {v}" for k, v in rubric.items()])
        evidence_str = json.dumps({
            "files_involved": evidence.files,
            "metrics": evidence.metrics,
            "key_findings": evidence.findings
        }, indent=2)
        
        return f"""
Category: {category_key}

Rubric Anchors:
{rubric_str}

Provided Evidence (Metadata only):
{evidence_str}

Evaluate this category. Select a level between 0 and 10. You must justify your choice using ONLY the provided evidence. Cite the specific evidence.

Output format required:
{{
  "level": 6,
  "justification": "Based on the presence of ...",
  "cited_evidence": ["file_a.py", "Finding 1"]
}}
"""
