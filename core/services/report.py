import json
import logging
from pathlib import Path
from typing import Dict, Any
from sqlmodel import Session

from core.infra.database import engine
from core.models.audit import AuditReport

logger = logging.getLogger(__name__)

class AuditReportService:
    def save_to_db(self, repo_path: str, data: Dict[str, Any]) -> int:
        """Saves the audit result to SQLite and returns the ID."""
        from core.models.audit import AuditCoreMember
        
        scorecard = data["scorecard"]
        gs = scorecard.get("group_scores", {})
        
        report = AuditReport(
            repo_path=repo_path,
            total_score=scorecard["total_score"],
            grade=scorecard["grade"],
            profile_signature=data.get("profile_signature", ""),
            layer1_score=scorecard["layer1_score"],
            layer2_score=scorecard["layer2_score"],
            group_security=gs.get("security_supply_chain"),
            group_code_health=gs.get("code_health_test"),
            group_structural=gs.get("structural_health"),
            group_resilience=gs.get("resilience_performance"),
            group_dev_hygiene=gs.get("dev_hygiene_devops"),
            raw_data=data
        )
        
        with Session(engine) as session:
            session.add(report)
            session.commit()
            session.refresh(report)
            
            # Save member scores
            from core.services.core_group_catalog import MEMBER_TO_GROUP, CATALOG_VERSION
            ms = scorecard.get("breakdown", {}).get("member_scores", {})
            for key, score in ms.items():
                grp = MEMBER_TO_GROUP.get(key)
                group_key = grp.key if grp else "unknown"
                member_label = key
                member_weight = None
                if grp:
                    for m in grp.members:
                        if m.key == key:
                            member_label = m.label
                            member_weight = m.weight
                            break
                member = AuditCoreMember(
                    report_id=report.id,
                    group_key=group_key,
                    member_key=key,
                    member_label=member_label,
                    score=float(score),
                    weight_at_time=member_weight,
                    catalog_version=CATALOG_VERSION
                )
                session.add(member)
            session.commit()
            
            return report.id

    def generate_markdown(self, repo_path: str, data: Dict[str, Any]) -> str:
        """Generates WARDEN_EXECUTIVE_REPORT.md using Gemini and saves it to the repo root."""
        import os
        from google import genai
        
        api_key = os.getenv("GEMINI_API_KEY")
        out_path = Path(repo_path) / "WARDEN_EXECUTIVE_REPORT.md"
        
        # Base fallback if no API key
        if not api_key:
            logger.warning("No GEMINI_API_KEY found. Generating basic fallback report.")
            content = f"# WARDEN Basic Report\nScore: {data['scorecard']['total_score']}/100"
            out_path.write_text(content, encoding="utf-8")
            return str(out_path.resolve())
            
        try:
            client = genai.Client(api_key=api_key)
            prompt = f"""
Sen WARDEN Baş Denetçisisin (Chief Security & Architecture Auditor).
Sana bir projenin tam teşekküllü (Layer 1 mekanik + Layer 2 LLM) denetim sonuçlarını JSON olarak veriyorum.
Görevin, bu JSON verilerini analiz edip tıpkı aşağıdaki örnek yapıya ve üsluba sahip, ÇOK KAPSAMLI, GÖRSEL, İKONLU ve YÖNETİCİ ÖZETİ (Executive Summary) niteliğinde bir Markdown raporu yazmaktır.
Raporun adı "WARDEN — Kapsamlı Proje İnceleme ve Denetim Raporu" olsun.
İçinde:
1. Yönetici Özeti
2. Mimari ve Güvenlik Durumu
3. Zafiyetler ve Teknik Borçlar (JSON'daki security ve leaks kısımlarını referans al, uydurma)
4. Kod Kalitesi ve Test Kapsamı (JSON'daki coverage ve complexity değerlerini referans al)
5. Kategori Bazlı LLM Değerlendirmesi (Layer 2 verilerini detaylandır)
6. Genel Puan Tablosu (Total Score, Grade ve Layer 1 Grup Puanları: group_scores)
7. Gelecek Yol Haritası ve Somut Aksiyon Önerileri

JSON Verisi:
{json.dumps(data, indent=2)}

Sadece Markdown metnini döndür. Asla markdown tagleri (```markdown) kullanma, doğrudan başlıklarla (#) başla.
"""
            models_to_try = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-3.5-flash', 'gemini-3.6-flash']
            response = None
            last_err = None
            
            for model_name in models_to_try:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt
                    )
                    if response and response.text:
                        break
                except Exception as err:
                    last_err = err
                    continue
                    
            if not response or not response.text:
                raise last_err if last_err else Exception("No response received from Gemini")
            
            content = response.text.replace("```markdown", "").replace("```", "").strip()
            out_path.write_text(content, encoding="utf-8")
            logger.info(f"Generated AI Executive scorecard at {out_path.resolve()}")
            
        except Exception as e:
            logger.error(f"Failed to generate AI report: {e}")
            content = f"# WARDEN Fallback Report\nScore: {data['scorecard']['total_score']}/100\nError: {e}"
            out_path.write_text(content, encoding="utf-8")
            
        return str(out_path.resolve())
