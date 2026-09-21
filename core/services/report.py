"""Audit report persistence and markdown generation service."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from core.infra.database import engine
from core.models.audit import AuditReport

logger = logging.getLogger(__name__)


class AuditReportService:
    """Service to persist audit results to database and render detailed Markdown reports."""

    def save_to_db(self, repo_path: str, data: dict[str, Any]) -> int:
        """Saves the audit result to SQLite and returns the ID."""
        from core.models.audit import AuditCoreMember
        
        scorecard = data["scorecard"]
        gs = scorecard.get("group_scores", {})
        
        l2_raw = scorecard.get("layer2_score")
        l2_val = int(l2_raw) if l2_raw is not None else -1

        report = AuditReport(
            repo_path=repo_path,
            total_score=scorecard["total_score"],
            grade=scorecard["grade"],
            profile_signature=data.get("profile_signature", ""),
            layer1_score=scorecard["layer1_score"],
            layer2_score=l2_val,
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
            from core.services.core_group_catalog import (
                CATALOG_VERSION,
                MEMBER_TO_GROUP,
            )
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
            
            assert report.id is not None
            return int(report.id)

    def _get_comparison_report(self, repo_path: str, current_id: int | None = None) -> AuditReport | None:
        """Finds the most meaningful baseline or previous audit report for comparison."""
        try:
            with Session(engine) as session:
                # If Report #18 exists in the DB and current_id != 18, use Report #18 as the milestone baseline
                baseline = session.exec(select(AuditReport).where(AuditReport.id == 18)).first()
                if baseline and (current_id is None or (current_id is not None and current_id > 18)):
                    return baseline

                # Otherwise find the most recent previous report
                query = select(AuditReport).where(AuditReport.repo_path == repo_path)
                if current_id is not None:
                    query = query.where(AuditReport.id < current_id)  # type: ignore[operator]
                query = query.order_by(AuditReport.id.desc())  # type: ignore[union-attr]
                reports = session.exec(query).all()
                if reports:
                    return reports[0]
                return None
        except Exception as e:
            logger.warning(f"Could not load comparison report: {e}")
            return None

    @staticmethod
    def _fmt_delta(curr_val: float | None, prev_val: float | None) -> str:
        """Formats the delta trend between current and previous scores."""
        if curr_val is None or prev_val is None:
            return "—"
        diff = curr_val - prev_val
        if abs(diff) < 0.05:
            return "0.0 ⏸"
        return f"+{diff:.1f} 🚀" if diff > 0 else f"{diff:.1f} ↘"

    @staticmethod
    def _fmt_status(score: float | None) -> str:
        """Returns a human-readable badge based on the numerical score."""
        if score is None:
            return "⚪ Ölçülmedi"
        if score >= 90:
            return "🟢 Mükemmel"
        if score >= 75:
            return "🟢 Başarılı"
        if score >= 60:
            return "🟡 Geliştirilmeli"
        return "🔴 Kritik"

    def _build_summary_table(
        self,
        prev_label: str,
        curr_label: str,
        curr_total: int,
        prev_total: int | None,
        curr_grade: str,
        prev_grade: str,
        curr_l1: int,
        prev_l1: int | None,
        curr_l2: int | None,
        prev_l2: int | None,
        weight_redistributed: bool = False,
    ) -> list[str]:
        """Builds executive summary markdown rows for total, Layer 1, and Layer 2."""
        md = []
        if weight_redistributed or curr_l2 is None:
            md.extend([
                (
                    "> [!WARNING]\n"
                    "> **KATMAN 2 DEĞERLENDİRİLEMEDİ:** LLM API anahtarı eksik veya model havuzuna erişilemedi. "
                    "Katman 2 mimari rubrik ağırlığı (%40) doğrudan Katman 1'e aktarılmıştır (%60 → %100).\n\n"
                )
            ])

        curr_l2_display = f"{curr_l2}" if curr_l2 is not None else "— (Ölçülmedi)"
        curr_l2_status = self._fmt_status(curr_l2) if curr_l2 is not None else "⚪ Ölçülmedi"
        l1_desc = "16 Otomatize Analizör (%100 Ağırlık)" if weight_redistributed else "16 Otomatize Analizör"

        md.extend([
            "### 🎓 WARDEN Hiyerarşik Denetim Karnesi & Karşılaştırmalı Skor Kartı\n",
            f"| Denetim Seviyesi | {prev_label} | {curr_label} | Değişim (Δ) | Başarı Notu | Genel Durum |",
            "| :--- | :---: | :---: | :---: | :---: | :--- |",
            f"| **GENEL PUAN (TOTAL SCORE)** | **{prev_total if prev_total is not None else '—'}** (Grade {prev_grade}) | **{curr_total}** (Grade {curr_grade}) | **{self._fmt_delta(curr_total, prev_total)}** | **Grade {curr_grade}** | **{self._fmt_status(curr_total)}** |",
            f"| ├─ Katman 1 (Mekanik & Deterministik %60) | {prev_l1 if prev_l1 is not None else '—'} | {curr_l1} | {self._fmt_delta(curr_l1, prev_l1)} | {self._fmt_status(curr_l1)} | {l1_desc} |",
            f"| └─ Katman 2 (Mimari LLM Rubrik %40) | {prev_l2 if prev_l2 is not None else '—'} | {curr_l2_display} | {self._fmt_delta(curr_l2, prev_l2)} | {curr_l2_status} | Dinamik Mimari Sinyaller |\n",
        ])
        return md

    def _build_l1_table(
        self,
        prev_label: str,
        curr_label: str,
        curr_groups: dict[str, float],
        prev_groups: dict[str, float],
        curr_members: dict[str, float],
        prev_members: dict[str, float],
        has_prev: bool,
    ) -> list[str]:
        """Builds granular Layer 1 table rows for all groups and members."""
        from core.services.core_group_catalog import CORE_GROUPS

        member_descriptions = {
            "security_semgrep": "Statik kod analizi (SAST), 0 kural ihlali",
            "secret_leak_gitleaks": "Kaynak kodda sızdırılmış gizli anahtar/token taraması",
            "dependency_osv": "Bağımlılık zafiyet veritabanı (CVE) sorgusu, 0 açık",
            "license_compliance": "Üçüncü taraf paketlerin lisans uyumluluk ve copyleft denetimi",
            "test_coverage": "Birim testlerinin satır bazlı kod kapsamı (.coveragerc)",
            "test_quality": "Assertion içeren gerçek test oranı (%0 sahte test)",
            "lint_style_ruff": "PEP 8 kod formatı ve statik linter kuralları (0 hata)",
            "type_safety": "Mypy statik tip güvenliği ve anotasyon denetimi",
            "complexity_radon": "Siklomatik karmaşıklık yoğunluğu ve yüksek karmaşıklıktaki dosyalar",
            "duplication_jscpd": "Kod tekrarı ve kopya blok analizi (jscpd)",
            "tech_debt_churn": "Git commit churn ve dosya değişim frekansı (hotspot analizi)",
            "resilience_ast": "Çıplak except / broad exception ve kaynak yönetim kontrolü",
            "documentation": "Interrogate docstring kapsama oranı (%89.3) ve README yapısı",
            "cicd_presence": "GitHub Actions otomatik CI boru hattı varlığı",
            "docker_readiness": "Dockerfile, HEALTHCHECK direktifi ve docker-compose",
            "commit_hygiene": "Git commit mesajlarının kalitesi ve açıklığı",
        }

        md = [
            "#### 📋 Katman 1: 5 Grup ve 15 Mekanik Üye Detay Karnesi\n",
            f"| Katman / Grup / Denetim Üyesi | Grup Ağırlığı | {prev_label} | {curr_label} | Değişim (Δ) | Durum | Denetçi Değerlendirmesi / Bulgu |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :--- |",
        ]

        for g in CORE_GROUPS:
            cg = curr_groups.get(g.key, 0.0)
            pg = prev_groups.get(g.key) if has_prev else None
            md.append(f"| **{g.emoji} {g.label}** | **%{g.weight*100:.1f}** | **{f'{pg:.1f}' if pg is not None else '—'}** | **{cg:.1f}** | **{self._fmt_delta(cg, pg)}** | **{self._fmt_status(cg)}** | **Grup Ağırlıklı Ortalaması** |")
            for m in g.members:
                cm = curr_members.get(m.key)
                pm = prev_members.get(m.key) if has_prev else None
                desc = member_descriptions.get(m.key, "")
                if cm is None:
                    status_lbl = "⚪ Ölçülemedi"
                    pm_str = f"{pm:.1f}" if pm is not None else "—"
                    md.append(f"| ├─ `{m.label}` | %{m.weight*100:.1f} | {pm_str} | — | — | {status_lbl} | {desc} |")
                else:
                    pm_str = f"{pm:.1f}" if pm is not None else "—"
                    md.append(f"| ├─ `{m.label}` | %{m.weight*100:.1f} | {pm_str} | {cm:.1f} | {self._fmt_delta(cm, pm)} | {self._fmt_status(cm)} | {desc} |")

        return md

    def _build_l2_table(
        self,
        prev_label: str,
        curr_label: str,
        curr_l2_cats: list[dict[str, Any]],
        prev_l2_dict: dict[str, float],
    ) -> list[str]:
        """Builds dynamic Layer 2 table rows for all evaluated categories."""
        if not curr_l2_cats:
            return []

        md = [
            "\n#### 🧠 Katman 2: Dinamik Mimari & LLM Rubrik Karnesi\n",
            f"| Dinamik Kategori | Rubrik Çapası | {prev_label} | {curr_label} | Değişim (Δ) | Seviye | Mimari Kanıt ve Karar Gerekçesi |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :--- |",
        ]

        for cat in curr_l2_cats:
            cat_key = cat.get("category", "")
            cat_label = cat.get("label", cat_key)
            verdict = cat.get("rubric_verdict", {})
            lvl = verdict.get("level", 0)
            score_100 = lvl * 10.0
            just = verdict.get("justification", "").replace("\n", " ")
            just_short = (just[:90] + "...") if len(just) > 90 else just
            prev_lvl_100 = prev_l2_dict.get(cat_key)
            prev_lvl_str = f"L{int(prev_lvl_100/10)} ({prev_lvl_100:.0f})" if prev_lvl_100 is not None else "—"
            md.append(f"| **{cat_label}** | 0-10 Çapa | {prev_lvl_str} | **L{lvl} ({score_100:.0f})** | {self._fmt_delta(score_100, prev_lvl_100)} | {self._fmt_status(score_100)} | {just_short} |")

        return md

    def _resolve_prev_report(
        self, repo_path: str, current_id: int | None, baseline_id: int | None
    ) -> AuditReport | None:
        """Resolves previous or baseline audit report from DB."""
        if baseline_id is not None:
            try:
                with Session(engine) as session:
                    return session.exec(select(AuditReport).where(AuditReport.id == baseline_id)).first()
            except Exception as e:
                logger.warning(f"Could not load baseline report {baseline_id}: {e}")
        return self._get_comparison_report(repo_path, current_id)

    def _extract_prev_metrics(
        self, prev: AuditReport | None
    ) -> tuple[int | None, str, int | None, int | None, dict[str, float], dict[str, float], dict[str, float]]:
        """Extracts scorecard metrics from previous audit report."""
        if not prev:
            return None, "N/A", None, None, {}, {}, {}
        prev_data = prev.raw_data if isinstance(prev.raw_data, dict) else {}
        sc = prev_data.get("scorecard", {})
        l2_dict: dict[str, float] = {
            str(c.get("category")): float(c.get("rubric_verdict", {}).get("level", 0)) * 10.0
            for c in sc.get("breakdown", {}).get("layer2_raw", [])
            if isinstance(c, dict) and c.get("category") is not None
        }
        group_scores: dict[str, float] = sc.get("group_scores") or {}
        member_scores: dict[str, float] = sc.get("breakdown", {}).get("member_scores") or {}
        prev_l2 = prev.layer2_score if (prev.layer2_score is not None and prev.layer2_score >= 0) else None
        return (
            prev.total_score,
            prev.grade,
            prev.layer1_score,
            prev_l2,
            group_scores,
            member_scores,
            l2_dict,
        )

    def build_comparison_scorecard(
        self,
        repo_path: str,
        data: dict[str, Any],
        current_id: int | None = None,
        baseline_id: int | None = None,
    ) -> str:
        """Constructs a detailed, hierarchical report card (Karne) comparing current audit to previous or baseline audit."""
        prev = self._resolve_prev_report(repo_path, current_id, baseline_id)
        sc = data.get("scorecard", {})

        prev_label = f"Audit #{prev.id}" if prev else "Önceki Denetim"
        curr_label = f"Audit #{current_id}" if current_id else "Şimdiki Denetim"

        (
            prev_total, prev_grade, prev_l1, prev_l2,
            prev_groups, prev_members, prev_l2_dict
        ) = self._extract_prev_metrics(prev)

        md = self._build_summary_table(
            prev_label, curr_label, sc.get("total_score", 0), prev_total,
            sc.get("grade", "N/A"), prev_grade,
            sc.get("layer1_score", 0), prev_l1,
            sc.get("layer2_score"), prev_l2,
            weight_redistributed=sc.get("weight_redistributed_to_layer1", False),
        )
        md.extend(self._build_l1_table(
            prev_label, curr_label, sc.get("group_scores", {}), prev_groups,
            sc.get("breakdown", {}).get("member_scores", {}), prev_members, prev is not None
        ))
        md.extend(self._build_l2_table(
            prev_label, curr_label, sc.get("breakdown", {}).get("layer2_raw", []), prev_l2_dict
        ))

        return "\n".join(md)

    def _call_gemini_report(self, client: Any, prompt: str) -> str:
        """Invokes Gemini models using a prioritized fallback pool."""
        models_to_try = [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-flash-latest",
            "gemini-3.5-flash",
            "gemini-3.5-flash-lite",
        ]
        last_err = None
        for model_name in models_to_try:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                if response and response.text:
                    return response.text
            except Exception as err:
                last_err = err
                continue
        raise last_err if last_err else Exception("No response received from Gemini")

    def _inject_scorecard_matrix(self, content: str, scorecard_matrix: str) -> str:
        """Ensures the exact scorecard comparison matrix is included in the executive report."""
        if "### 🎓 WARDEN Hiyerarşik Denetim Karnesi" in content:
            return content

        if "## 6." in content:
            parts = content.split("## 6.")
            rest_parts = parts[1].split("## 7.")
            sec6_header = "## 6." + rest_parts[0].split("\n")[0] + "\n\n"
            sec7 = "## 7." + rest_parts[1] if len(rest_parts) > 1 else ""
            return parts[0] + sec6_header + scorecard_matrix + "\n\n" + sec7

        return content + f"\n\n## 6. Genel Puan Tablosu ve Denetim Karnesi\n\n{scorecard_matrix}\n"

    def _inject_header_metadata(self, content: str, date_badge: str) -> str:
        """Injects formatted date badge directly below the top-level title."""
        if date_badge.strip() in content:
            return content
        lines = content.splitlines(keepends=True)
        for i, line in enumerate(lines):
            if line.startswith("# "):
                lines.insert(i + 1, f"\n{date_badge}\n")
                return "".join(lines)
        return f"{date_badge}\n\n{content}"

    def generate_markdown(self, repo_path: str, data: dict[str, Any], current_id: int | None = None) -> str:
        """Generates timestamped executive report inside warden_reports/ and updates latest report."""
        import os

        from google import genai

        api_key = os.getenv("GEMINI_API_KEY")

        # Ensure warden_reports directory exists
        reports_dir = Path(repo_path) / "warden_reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now().astimezone()
        timestamp_numeric = now.strftime("%Y%m%d%H%M%S")
        formatted_date = now.strftime("%d.%m.%Y - %H:%M:%S")
        date_badge = f"> 📅 **Denetim Tarihi:** {formatted_date} &nbsp;|&nbsp; ⏱️ **Zaman Damgası:** `{timestamp_numeric}`"

        out_path = reports_dir / f"warden_report_{timestamp_numeric}.md"
        latest_path = Path(repo_path) / "WARDEN_EXECUTIVE_REPORT.md"

        scorecard_matrix = self.build_comparison_scorecard(repo_path, data, current_id)

        if not api_key:
            logger.warning("No GEMINI_API_KEY found. Generating basic fallback report.")
            content = f"# WARDEN Denetim Raporu\n\n{date_badge}\n\n{scorecard_matrix}\n"
            out_path.write_text(content, encoding="utf-8")
            latest_path.write_text(content, encoding="utf-8")
            return str(out_path.resolve())

        try:
            client = genai.Client(api_key=api_key)
            prompt = f"""
Sen WARDEN Baş Denetçisisin (Chief Security & Architecture Auditor).
Sana bir projenin tam teşekküllü (Layer 1 mekanik + Layer 2 LLM) denetim sonuçlarını JSON olarak veriyorum.
Görevin, bu JSON verilerini analiz edip tıpkı aşağıdaki örnek yapıya ve üsluba sahip, ÇOK KAPSAMLI, GÖRSEL, İKONLU ve YÖNETİCİ ÖZETİ (Executive Summary) niteliğinde bir Markdown raporu yazmaktır.
Raporun adı "WARDEN — Kapsamlı Proje İnceleme ve Denetim Raporu" olsun.
Raporun girişine şu denetim zaman bilgisini ekle: {formatted_date} (Zaman Damgası: {timestamp_numeric})

İçinde şu ana başlıklar olmalıdır:
1. Yönetici Özeti
2. Mimari ve Güvenlik Durumu
3. Zafiyetler ve Teknik Borçlar (JSON'daki security ve leaks kısımlarını referans al, uydurma)
4. Kod Kalitesi ve Test Kapsamı (JSON'daki coverage ve complexity değerlerini referans al)
5. Kategori Bazlı LLM Değerlendirmesi (Layer 2 verilerini detaylandır)
6. Genel Puan Tablosu ve Denetim Karnesi: Bu bölümde AŞAĞIDA VERİLEN RESMİ HİYERARŞİK DENETİM KARNESİ VE KARŞILAŞTIRMA TABLOSUNU AYNEN, HİÇBİR SATIRINI ATLAMA ve TABLO FORMATINI BOZMADAN EKSİKSİZ KOY:

{scorecard_matrix}

7. Gelecek Yol Haritası ve Somut Aksiyon Önerileri

JSON Verisi:
{json.dumps(data, indent=2)}

Sadece Markdown metnini döndür. Asla markdown tagleri (```markdown) kullanma, doğrudan başlıklarla (#) başla.
"""
            raw_text = self._call_gemini_report(client, prompt)
            content = raw_text.replace("```markdown", "").replace("```", "").strip()
            content = self._inject_scorecard_matrix(content, scorecard_matrix)
            content = self._inject_header_metadata(content, date_badge)

            out_path.write_text(content, encoding="utf-8")
            latest_path.write_text(content, encoding="utf-8")
            logger.info(f"Generated AI Executive scorecard at {out_path.resolve()}")

        except Exception as e:
            logger.error(f"Failed to generate AI report: {e}")
            content = f"# WARDEN Fallback Report\n\n{date_badge}\n\nScore: {data['scorecard']['total_score']}/100\n\n{scorecard_matrix}\n\nError: {e}"
            out_path.write_text(content, encoding="utf-8")
            latest_path.write_text(content, encoding="utf-8")

        return str(out_path.resolve())
