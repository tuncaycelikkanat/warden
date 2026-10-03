"""Audit report persistence and markdown generation service."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()


from sqlmodel import Session, select

from core.infra.database import engine
from core.models.audit import AuditReport

logger = logging.getLogger(__name__)


def _make_json_safe(obj: Any) -> Any:
    """Recursively sanitizes data structure so it is guaranteed to be JSON-serializable."""
    import dataclasses
    from datetime import date, datetime
    from pathlib import Path

    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return _make_json_safe(dataclasses.asdict(obj))
    if hasattr(obj, "__dict__") and not isinstance(obj, type):
        return _make_json_safe(obj.__dict__)
    if isinstance(obj, dict):
        return {str(k): _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_make_json_safe(item) for item in obj]
    return str(obj)


class AuditReportService:
    """Service to persist audit results to database and render detailed Markdown reports."""

    def save_to_db(self, repo_path: str, data: dict[str, Any]) -> int:
        """Saves the audit result to SQLite and returns the ID."""
        from core.models.audit import AuditCoreMember
        
        scorecard = data["scorecard"]
        gs = scorecard.get("group_scores", {})
        
        l2_raw = scorecard.get("layer2_score")
        l2_val = int(l2_raw) if l2_raw is not None else -1

        safe_raw_data = _make_json_safe(data)

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
            raw_data=safe_raw_data
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
        """Finds the most meaningful baseline or previous audit report for comparison.

        Prefers a report explicitly marked as a milestone (is_milestone=True).
        Falls back to the most recent previous report for the same repo_path.
        """
        try:
            with Session(engine) as session:
                # 1. Önce bu repo için milestone işaretli raporu dene
                milestone_query = (
                    select(AuditReport)
                    .where(AuditReport.repo_path == repo_path)
                    .where(AuditReport.is_milestone == True)
                    .order_by(AuditReport.id.desc())  # type: ignore[union-attr]
                )
                if current_id is not None:
                    milestone_query = milestone_query.where(AuditReport.id < current_id)  # type: ignore[operator]
                milestone = session.exec(milestone_query).first()
                if milestone:
                    return milestone

                # 2. Milestone yoksa en son önceki raporu kullan
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
        data: dict[str, Any] | None = None,
    ) -> list[str]:
        """Builds granular Layer 1 table rows for all groups and members."""
        from core.services.core_group_catalog import CORE_GROUPS

        # ── Dynamic descriptions: pull real numbers from JSON data ───────────
        raw = data or {}
        l1_raw = (raw.get("scorecard", {}) or {}).get("breakdown", {}).get("layer1_raw", {}) or {}

        sec = l1_raw.get("security") or raw.get("security") or []
        sast_issues = len(sec) if isinstance(sec, list) else len(sec.get("issues", []) if isinstance(sec, dict) else [])

        leaks = l1_raw.get("leaks") or raw.get("leaks") or []
        leaks_count = len(leaks)

        deps = l1_raw.get("dependencies") or raw.get("dependencies") or []
        cve_count = len(deps) if isinstance(deps, list) else len(deps.get("vulnerabilities", []) if isinstance(deps, dict) else [])

        lint = l1_raw.get("lint") or raw.get("lint") or {}
        ruff_errors = lint.get("error_count", 0) if isinstance(lint, dict) else 0

        type_meta = l1_raw.get("type_safety_meta") or raw.get("type_safety") or {}
        mypy_errors = type_meta.get("error_count", 0) if isinstance(type_meta, dict) else 0

        tq_meta = l1_raw.get("test_quality_meta") or raw.get("test_quality") or {}
        test_total = tq_meta.get("total_tests", 0) if isinstance(tq_meta, dict) else 0
        fake_tests = tq_meta.get("fake_tests", 0) if isinstance(tq_meta, dict) else 0

        comp = l1_raw.get("complexity") or raw.get("complexity") or {}
        avg_cc = comp.get("avg_complexity", comp.get("average_complexity", 0)) if isinstance(comp, dict) else 0

        dup = l1_raw.get("duplication") or raw.get("duplication") or {}
        dup_pct = dup.get("duplication_pct", dup.get("percentage", 0)) if isinstance(dup, dict) else 0

        td = l1_raw.get("tech_debt") or raw.get("tech_debt") or {}
        todo_count = len(td.get("todo_markers", [])) if isinstance(td, dict) and "todo_markers" in td else (td.get("todo_count", 0) if isinstance(td, dict) else 0)
        commit_count = len(td.get("churn_entries", [])) if isinstance(td, dict) and "churn_entries" in td else (td.get("hotspot_commit_count", 0) if isinstance(td, dict) else 0)

        cov = l1_raw.get("coverage") or raw.get("coverage") or {}
        cov_pct = cov.get("line_rate", cov.get("coverage_pct")) if isinstance(cov, dict) else None

        docs = l1_raw.get("docs") or raw.get("documentation") or {}
        doc_pct = docs.get("docstring_coverage_pct", docs.get("coverage_percentage", 0)) if isinstance(docs, dict) else 0

        member_descriptions: dict[str, str] = {
            "security_semgrep": (
                f"SAST statik analiz: {sast_issues} sorun tespit edildi"
                if sast_issues else "SAST statik analiz: sorun tespit edilmedi ✓"
            ),
            "secret_leak_gitleaks": (
                f"Gizli anahtar taraması: {leaks_count} sızıntı tespit edildi 🔑"
                if leaks_count else "Gizli anahtar taraması: sızıntı bulunmadı ✓"
            ),
            "dependency_osv": (
                f"CVE zafiyet taraması: {cve_count} açık bağımlılık" if cve_count
                else "CVE zafiyet taraması: 0 açık bağımlılık ✓"
            ),
            "license_compliance": "Üçüncü taraf lisans uyumluluk ve copyleft denetimi",
            "test_coverage": (
                f"Satır bazlı kod kapsamı: %{cov_pct:.1f}" if cov_pct is not None
                else "Satır bazlı kod kapsamı (execution_timeout nedeniyle ölçülemedi)"
            ),
            "test_quality": (
                f"Test kalitesi: {test_total} test, {fake_tests} sahte/assertion-sız"
                if test_total else "Test kalitesi: gerçek assertion oranı analizi"
            ),
            "lint_style_ruff": (
                f"Ruff linter: {ruff_errors} uyarı/hata (F401, S603, S607 ağırlıklı)"
                if ruff_errors else "Ruff linter: hata/uyarı yok ✓"
            ),
            "type_safety": (
                f"Mypy statik tip analizi: {mypy_errors} uyumsuzluk"
                if mypy_errors else "Mypy statik tip analizi: tip uyumsuzluğu yok ✓"
            ),
            "complexity_radon": (
                f"Siklomatik karmaşıklık: ortalama {avg_cc:.2f}"
                if avg_cc else "Siklomatik karmaşıklık analizi"
            ),
            "duplication_jscpd": (
                f"Kopya blok analizi (jscpd): %{dup_pct:.2f} tekrar oranı"
                if dup_pct else "Kopya blok analizi (jscpd)"
            ),
            "tech_debt_churn": (
                f"Git churn analizi: {commit_count} hotspot commit, {todo_count} TODO/FIXME"
                if (commit_count or todo_count) else "Git commit churn ve hotspot analizi"
            ),
            "resilience_ast": "Çıplak except / broad exception ve kaynak yönetim kontrolü",
            "documentation": (
                f"Docstring kapsama: %{doc_pct:.1f}" if doc_pct else "Docstring kapsama oranı"
            ),
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
            verdict = cat.get("rubric_verdict") or {}
            lvl = verdict.get("level")
            prev_lvl_100 = prev_l2_dict.get(cat_key)
            just = (verdict.get("justification") or "").replace("\n", " ").strip()
            just_short = (just[:200] + "…") if len(just) > 200 else just

            if lvl is not None:
                score_100 = lvl * 10.0
                lvl_str = f"**L{lvl} ({score_100:.0f})**"
                delta_str = self._fmt_delta(score_100, prev_lvl_100)
                status_str = self._fmt_status(score_100)
            else:
                score_100 = None
                lvl_str = "— (Ölçülmedi)"
                delta_str = "—"
                status_str = "⚪ Ölçülmedi"

            prev_lvl_str = f"L{int(prev_lvl_100/10)} ({prev_lvl_100:.0f})" if prev_lvl_100 is not None else "—"
            md.append(f"| **{cat_label}** | 0-10 Çapa | {prev_lvl_str} | {lvl_str} | {delta_str} | {status_str} | {just_short} |")


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

    @staticmethod
    def _build_ascii_trend(history_scores: list[int]) -> str:
        """Renders a sparkline trend from the last audit scores."""
        if not history_scores:
            return ""
        blocks = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
        lo, hi = min(history_scores), max(history_scores)
        span = (hi - lo) or 1
        spark = "".join(blocks[min(7, int((s - lo) / span * 7))] for s in history_scores)
        trend_arrow = "↗️ Yükseliş" if history_scores[-1] >= history_scores[0] else "↘️ Düşüş"
        return (
            f"\n---\n\n## 📈 Tarihsel Skor Trendi (Son {len(history_scores)} Denetim)\n\n"
            f"```\n"
            f"Skor Eğrisi  : {spark}\n"
            f"Skor Aralığı : {lo} – {hi}  |  Son Skor: {history_scores[-1]}  |  Trend: {trend_arrow}\n"
            f"```\n"
        )

    @staticmethod
    def _build_vibe_coding_section(data: dict[str, Any]) -> str:
        """Renders a vibe-coding & AI style drift summary block."""
        vc = data.get("vibe_coding") or data.get("ai_slop") or {}
        if not vc:
            return ""

        ratio = vc.get("ratio", vc.get("ai_ratio", 0))
        risk = vc.get("risk_level", "UNKNOWN")
        indicators = vc.get("indicator_count", vc.get("total_indicators", 0))
        style_drift = vc.get("style_drift") or data.get("style_drift") or {}
        drift_score = style_drift.get("overall_drift_score", None)
        drift_risk  = style_drift.get("risk_level", None)

        risk_icon = {"LOW": "🟢", "MODERATE": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"}.get(risk, "⚪")
        drift_icon = {"LOW": "🟢", "MODERATE": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"}.get(drift_risk or "", "⚪")

        lines = [
            "\n---\n",
            "## 🤖 Vibe-Coding & Yapay Zeka Stil Analizi\n",
            "| Metrik | Değer | Risk Seviyesi |",
            "| :--- | :---: | :---: |",
            f"| **AI Üretimi İz Oranı** | **%{ratio:.1f}** | {risk_icon} {risk} |",
            f"| **Tespit Edilen Gösterge Sayısı** | {indicators} | — |",
        ]
        if drift_score is not None:
            lines.append(f"| **Kod Stili Drift Skoru** | %{drift_score:.1f} | {drift_icon} {drift_risk or '—'} |")
        lines.append("")
        if ratio > 30:
            lines.append("> [!CAUTION]\n> Yüksek AI iz oranı tespit edildi. Didaktik yorumlar, LLM tarafından üretilen markdown blokları ve prompt kalıntıları kod tabanını kirletiyor olabilir.\n")
        elif ratio > 15:
            lines.append("> [!WARNING]\n> Orta düzeyde AI iz oranı. Commit bazlı inceleme önerilir.\n")
        return "\n".join(lines)

    @staticmethod
    def _build_security_insights_section(data: dict[str, Any]) -> str:
        """Renders a structured security findings block."""
        l1_raw = (data.get("scorecard", {}) or {}).get("breakdown", {}).get("layer1_raw", {}) or {}
        leaks = l1_raw.get("leaks") or data.get("leaks") or []
        sec = l1_raw.get("security") or data.get("security") or []
        issues = sec if isinstance(sec, list) else sec.get("issues", [])
        if not leaks and not issues:
            return ""

        lines = [
            "\n---\n",
            "## 🔐 Güvenlik Bulguları Detayı\n",
        ]

        if issues:
            lines.append("### 🛡️ SAST Taint & Statik Analiz Bulguları\n")
            lines.append("| Önem | Kural | Dosya | Satır |")
            lines.append("| :---: | :--- | :--- | :---: |")
            for issue in issues[:10]:
                sev = issue.get("severity", "ERROR")
                sev_icon = {"ERROR": "🔴", "WARNING": "🟡", "INFO": "🔵"}.get(sev, "⚪")
                rule = issue.get("rule_id", issue.get("check_id", issue.get("rule", "—")))
                path = issue.get("path", issue.get("file", "—"))
                line = issue.get("line", issue.get("start", {}).get("line", "—"))
                lines.append(f"| {sev_icon} {sev} | `{rule}` | `{path}` | {line} |")
            lines.append("")

        if leaks:
            lines.append("### 🔑 Gizli Anahtar & Token Sızıntıları\n")
            lines.append(f"> [!CAUTION]\n> Toplam **{len(leaks)}** gizli anahtar/token sızıntısı tespit edildi.\n")
            lines.append("| Dosya | Satır | Tür | Maskeli Değer |")
            lines.append("| :--- | :---: | :--- | :--- |")
            for leak in leaks[:8]:
                path = leak.get("File", leak.get("file", "—"))
                line = leak.get("StartLine", leak.get("line", "—"))
                rule = leak.get("RuleID", leak.get("type", "—"))
                secret = str(leak.get("Secret", leak.get("value", "—")))
                masked = secret[:4] + "****" + secret[-4:] if len(secret) > 10 else "****"
                lines.append(f"| `{path}` | {line} | `{rule}` | `{masked}` |")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _build_ck_summary_section(data: dict[str, Any]) -> str:
        """Renders a CK metrics God Class summary block."""
        ck = data.get("ck_metrics") or {}
        if not ck:
            return ""

        god_classes = ck.get("god_classes") or []
        total_classes = ck.get("total_classes", 0)
        avg_wmc = ck.get("average_wmc", 0)

        if not god_classes and not total_classes:
            return ""

        lines = [
            "\n---\n",
            "## 🏛️ Mimari Karmaşıklık (CK OO Metrikleri)\n",
            "| Metrik | Değer |",
            "| :--- | :---: |",
            f"| Analiz Edilen Sınıf | {total_classes} |",
            f"| Ortalama WMC | {avg_wmc:.1f} |",
            f"| God Class Sayısı | **{len(god_classes)}** |",
            "",
        ]

        if god_classes:
            lines.append("> [!WARNING]\n> Aşağıdaki sınıflar Tek Sorumluluk Prensibini (SRP) ihlal ediyor. Refactoring öncelikli.\n")
            lines.append("| Sınıf | WMC | CBO | LCOM4 |")
            lines.append("| :--- | :---: | :---: | :---: |")
            for gc in god_classes[:5]:
                name = gc.get("class_name", "—")
                wmc = gc.get("wmc", "—")
                cbo = gc.get("cbo", "—")
                lcom4 = gc.get("lcom4", "—")
                lines.append(f"| `{name}` | {wmc} | {cbo} | {lcom4} |")
            lines.append("")

        return "\n".join(lines)

    def build_comparison_scorecard(
        self,
        repo_path: str,
        data: dict[str, Any],
        current_id: int | None = None,
        baseline_id: int | None = None,
    ) -> str:
        """Constructs a detailed, hierarchical report card comparing current audit to previous or baseline."""
        prev = self._resolve_prev_report(repo_path, current_id, baseline_id)
        sc = data.get("scorecard", {})

        prev_label = f"Audit #{prev.id}" if prev else "Önceki Denetim"
        curr_label = f"Audit #{current_id}" if current_id else "Şimdiki Denetim"

        (
            prev_total, prev_grade, prev_l1, prev_l2,
            prev_groups, prev_members, prev_l2_dict
        ) = self._extract_prev_metrics(prev)

        # ── Load historical scores for sparkline ────────────────────────────
        history_scores: list[int] = []
        try:
            with __import__("sqlmodel").Session(engine) as session:
                from sqlmodel import select as _select
                rows = session.exec(
                    _select(AuditReport)
                    .where(AuditReport.repo_path == repo_path)
                    .order_by(AuditReport.id.asc())  # type: ignore[union-attr]
                ).all()
                history_scores = [r.total_score for r in rows[-10:] if r.total_score is not None]
        except Exception:
            pass

        md = self._build_summary_table(
            prev_label, curr_label, sc.get("total_score", 0), prev_total,
            sc.get("grade", "N/A"), prev_grade,
            sc.get("layer1_score", 0), prev_l1,
            sc.get("layer2_score"), prev_l2,
            weight_redistributed=sc.get("weight_redistributed_to_layer1", False),
        )
        md.extend(self._build_l1_table(
            prev_label, curr_label, sc.get("group_scores", {}), prev_groups,
            sc.get("breakdown", {}).get("member_scores", {}), prev_members,
            prev is not None, data=data,
        ))
        md.extend(self._build_l2_table(
            prev_label, curr_label, sc.get("breakdown", {}).get("layer2_raw", []), prev_l2_dict
        ))

        result = "\n".join(md)

        # ── Append rich contextual sections ─────────────────────────────────
        result += self._build_ascii_trend(history_scores)
        result += self._build_vibe_coding_section(data)
        result += self._build_security_insights_section(data)
        result += self._build_ck_summary_section(data)

        return result

    def _call_gemini_report(self, client: Any, prompt: str) -> str:
        """Invokes Gemini models using a prioritized fallback pool."""
        from core.config.llm_config import DEFAULT_GEMINI_MODELS
        models_to_try = list(DEFAULT_GEMINI_MODELS)
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
        """Reliably injects the official deterministic scorecard matrix into Section 6."""
        if "### 🎓 WARDEN Hiyerarşik Denetim Karnesi" in content:
            return content

        if "<!-- SCORECARD_MATRIX_PLACEHOLDER -->" in content:
            return content.replace("<!-- SCORECARD_MATRIX_PLACEHOLDER -->", scorecard_matrix)

        if "## 6." in content:
            parts = content.split("## 6.")
            rest_parts = parts[1].split("## 7.")
            sec6_header = "## 6." + rest_parts[0].split("\n")[0] + "\n\n"
            sec7 = "## 7." + rest_parts[1] if len(rest_parts) > 1 else ""
            return parts[0] + sec6_header + scorecard_matrix + "\n\n" + sec7

        return content + f"\n\n## 6. Genel Puan Tablosu ve Denetim Karnesi\n\n{scorecard_matrix}\n"

    def _inject_header_metadata(self, content: str, date_badge: str) -> str:
        """Injects formatted date badge directly below the top-level title (dedup-safe)."""
        if date_badge.strip() in content:
            return content

        import re

        # Remove ALL pre-existing date badge variants (LLM sometimes writes its own)
        content = re.sub(r"\n?> \*?\*?Denetim (Tarihi|Zaman Bilgisi)\*?\*?:.*\n?", "", content)
        content = re.sub(r"\n?> \*?\*?Zaman Damgası\*?\*?:.*\n?", "", content)
        content = re.sub(r"\n?> 📅 \*\*Denetim Tarihi:\*\*.*\n?", "", content)
        content = re.sub(r"\n?> \*?\*?Baş Denetçi\*?\*?:.*\n?", "", content)
        content = re.sub(r"\n?> \*?\*?Hedef Skor\*?\*?:.*\n?", "", content)

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
Görevin, bu JSON verilerini analiz edip üst düzey, analitik, GÖRSEL, İKONLU ve YÖNETİCİ ÖZETİ (Executive Summary) niteliğinde bir Markdown raporu yazmaktır.
Rapor dili tamamen TÜRKÇE olmalıdır. İngilizce terimler yalnızca parantez içinde teknik referans olarak kalabilir.

Raporun başlığı: "# WARDEN — Kapsamlı Proje İnceleme ve Denetim Raporu"
Başlığın hemen altına tarih veya üst bilgi bloğu YAZMA (sistem otomatik ekleyecektir).

İçinde şu ana başlıklar olmalıdır:
## 1. Yönetici Özeti
Projenin genel notu, Layer 1 ve Layer 2 dengesi, en güçlü ve en kırılgan yönleri özetle.

## 2. Mimari ve Güvenlik Durumu
Proje iskeleti, framework kullanımı, asenkronluk, thread-safety ve LLM koruma mekanizmaları.

## 3. Zafiyetler ve Teknik Borçlar
JSON'daki `security`, `leaks` ve `tech_debt` verilerine dayan. Asla uydurma veri yazma. Gerçek dosya ve satır referansları ver.

## 4. Kod Kalitesi ve Test Kapsamı
Test kalitesi, sahte test oranı, ortalama karmaşıklık, tip hataları (mypy) ve linter (ruff) bulguları.

## 5. Kategori Bazlı LLM Değerlendirmesi (Layer 2)
Katman 2 mimari rubrik değerlendirmesini detaylandır. Her kategori için mimari gerekçeyi Türkçe, yapıcı ve derinlemesine açıkla.

## 6. Genel Puan Tablosu ve Denetim Karnesi
Bu başlığın hemen altına yalnızca şu satırı koy, başka tablo veya metin ekleme:
<!-- SCORECARD_MATRIX_PLACEHOLDER -->

## 7. Gelecek Yol Haritası ve Somut Aksiyon Önerileri
Bulguları önem derecesine göre önceliklendir:
- 🔴 **[CRITICAL]** Hemen çözülmesi gerekenler (SQL injection, credential leak, vb.) -> [Beklenen Etki: ...]
- 🟠 **[HIGH]** Kısa vadeli mimari refactoring (God function, döngüsel bağımlılık) -> [Beklenen Etki: ...]
- 🟡 **[MEDIUM]** Kod hijyeni ve tip güvenliği (Mypy, Ruff, Docstring) -> [Beklenen Etki: ...]
- 🟢 **[LOW]** Dokümantasyon ve test kapsamı artırımları -> [Beklenen Etki: ...]

JSON Verisi:
{json.dumps(data, indent=2)}

Sadece Markdown metnini döndür. Asla markdown tagleri (```markdown) kullanma, doğrudan başlıkla (#) başla.
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
