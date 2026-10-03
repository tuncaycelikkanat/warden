"""Executive PDF report generator service for WARDEN audits.

Creates professional, corporate-ready PDF executive summaries using ReportLab.
"""

import io
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

logger = logging.getLogger(__name__)


class NumberedCanvas(canvas.Canvas):
    """Custom canvas tracking two-pass total page counts and adding running footers."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int) -> None:
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))

        # Footer
        footer_text = f"WARDEN Autonomous Governance Engine • Page {self._pageNumber} of {page_count}"
        self.drawRightString(A4[0] - 40, 25, footer_text)
        self.drawString(40, 25, "CONFIDENTIAL & PROPRIETARY • FOR INTERNAL QA GOVERNANCE USE ONLY")

        # Subtle bottom rule
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(40, 35, A4[0] - 40, 35)

        self.restoreState()


class PdfReportService:
    """Generates corporate PDF executive summaries from WARDEN audit results."""

    def __init__(self) -> None:
        self.styles = getSampleStyleSheet()
        self._init_custom_styles()

    def _init_custom_styles(self) -> None:
        """Configures typography styles for the PDF report."""
        self.title_style = ParagraphStyle(
            "DocTitle",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#0f172a"),
        )
        self.subtitle_style = ParagraphStyle(
            "DocSubTitle",
            parent=self.styles["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=15,
            textColor=colors.HexColor("#475569"),
        )
        self.section_header = ParagraphStyle(
            "SectionHeader",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=colors.HexColor("#1e293b"),
            spaceBefore=12,
            spaceAfter=6,
        )
        self.body_style = ParagraphStyle(
            "ReportBody",
            parent=self.styles["Normal"],
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#334155"),
        )
        self.cell_bold = ParagraphStyle(
            "CellBold",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#0f172a"),
        )
        self.badge_style = ParagraphStyle(
            "BadgeStyle",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            alignment=1,  # Center
            textColor=colors.white,
        )

    def generate_pdf_bytes(self, audit_data: dict[str, Any], repo_path: str = "") -> bytes:
        """Renders the executive summary directly into in-memory PDF bytes."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=40,
            rightMargin=40,
            topMargin=40,
            bottomMargin=50,
        )

        story = self._build_story(audit_data, repo_path)
        doc.build(story, canvasmaker=NumberedCanvas)
        return buffer.getvalue()

    def generate_pdf(self, audit_data: dict[str, Any], output_path: Path, repo_path: str = "") -> Path:
        """Renders the executive summary into a PDF file on disk."""
        pdf_bytes = self.generate_pdf_bytes(audit_data, repo_path=repo_path)
        output_path = output_path.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(pdf_bytes)
        return output_path

    def _build_story(self, data: dict[str, Any], repo_path: str) -> list[Any]:
        """Constructs Flowable story elements for the executive report."""
        story: list[Any] = []

        scorecard = data.get("scorecard", {})
        total_score = int(scorecard.get("total_score", 0))
        grade = str(scorecard.get("grade", "F")).upper()
        l1 = scorecard.get("layer1_score", 0)
        l2 = scorecard.get("layer2_score")
        l2_display = f"{l2}/100" if l2 is not None and l2 != -1 else "N/A"

        # Accent colors based on total score
        if total_score >= 80:
            badge_color = colors.HexColor("#16a34a")  # Green
            gate_label = "PASSED (Quality Gate Satisfied)"
        elif total_score >= 60:
            badge_color = colors.HexColor("#ca8a04")  # Amber
            gate_label = "NEEDS IMPROVEMENT"
        else:
            badge_color = colors.HexColor("#dc2626")  # Red
            gate_label = "FAILED (Quality Gate Violation)"

        # 1. Header Banner
        target_name = repo_path or data.get("repo_path") or "Target Repository"
        now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        profile = data.get("profile_signature", "General Python Application")

        header_table_data = [
            [
                Paragraph("🛡️ WARDEN GOVERNANCE AUDIT", self.title_style),
                Paragraph(f"<font size=14><b>{grade}</b></font><br/>{total_score}/100", self.badge_style),
            ],
            [
                Paragraph(
                    f"<b>Repository:</b> {target_name}<br/>"
                    f"<b>Audit Date:</b> {now_str} • <b>Profile:</b> {profile}<br/>"
                    f"<b>Gate Status:</b> <font color='{badge_color.hexval()}'><b>{gate_label}</b></font>",
                    self.subtitle_style,
                ),
                "",
            ],
        ]

        header_table = Table(header_table_data, colWidths=[400, 115])
        header_table.setStyle(
            TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (1, 0), (1, 0), badge_color),
                ("PADDING", (1, 0), (1, 0), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        story.append(header_table)
        story.append(Spacer(1, 14))

        # 2. Key Dimensions Table
        story.append(Paragraph("1. Executive Summary & Quality Dimensions", self.section_header))

        # Extract tech debt estimate if present
        td_data = data.get("layer1", {}).get("tech_debt", {})
        rem_hours = td_data.get("remediation_estimate", {}).get("total_hours", 0.0)
        rem_days = td_data.get("remediation_estimate", {}).get("total_days", 0.0)
        debt_str = f"{rem_hours:.1f} hours (~{rem_days:.1f} dev-days)" if rem_hours > 0 else "0.0 hours (Minimal)"

        # Extract Vibe score
        vibe_score = data.get("layer1_5", {}).get("vibe_score") or data.get("vibe_score")
        vibe_str = f"{vibe_score:.1f}/100" if vibe_score is not None else "N/A"

        dim_data = [
            [
                Paragraph("Evaluation Metric", self.cell_bold),
                Paragraph("Score / Status", self.cell_bold),
                Paragraph("Benchmark / Standard", self.cell_bold),
            ],
            [
                Paragraph("Overall Quality Score", self.body_style),
                Paragraph(f"<b>{total_score}/100 ({grade})</b>", self.body_style),
                Paragraph("Target >= 80 (Grade A or B)", self.body_style),
            ],
            [
                Paragraph("Layer 1: Mechanical Health (AST/SAST)", self.body_style),
                Paragraph(f"{l1}/100", self.body_style),
                Paragraph("14 Automated Analyzers", self.body_style),
            ],
            [
                Paragraph("Layer 2: LLM Architectural Rubric", self.body_style),
                Paragraph(l2_display, self.body_style),
                Paragraph("7 Architectural Evaluation Categories", self.body_style),
            ],
            [
                Paragraph("Layer 1.5: Vibe & AI Slop Health", self.body_style),
                Paragraph(vibe_str, self.body_style),
                Paragraph("Anti-slop / Style Drift Detection", self.body_style),
            ],
            [
                Paragraph("Estimated Technical Debt Remediation", self.body_style),
                Paragraph(debt_str, self.body_style),
                Paragraph("SQALE Empirical Effort Model", self.body_style),
            ],
        ]

        dim_table = Table(dim_data, colWidths=[200, 140, 175])
        dim_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ])
        )
        story.append(dim_table)
        story.append(Spacer(1, 14))

        # 3. Core Member Scorecard Breakdown Table
        story.append(Paragraph("2. Layer 1 Group Category Breakdown", self.section_header))
        gs = scorecard.get("group_scores", {})

        group_data = [
            [
                Paragraph("Group Category", self.cell_bold),
                Paragraph("Calculated Score", self.cell_bold),
                Paragraph("Evaluation Focus Area", self.cell_bold),
            ],
            [
                Paragraph("Security & Supply Chain", self.body_style),
                Paragraph(f"{gs.get('security_supply_chain', 0):.1f}/100", self.body_style),
                Paragraph("Semgrep, Gitleaks, Shannon Entropy, SBOM, Typosquatting", self.body_style),
            ],
            [
                Paragraph("Code Health & Testing", self.body_style),
                Paragraph(f"{gs.get('code_health_test', 0):.1f}/100", self.body_style),
                Paragraph("Pytest Coverage, Fake Tests, Hypothesis Property Tests", self.body_style),
            ],
            [
                Paragraph("Structural & Architecture", self.body_style),
                Paragraph(f"{gs.get('structural_health', 0):.1f}/100", self.body_style),
                Paragraph("Circular Imports, AST Couplings, PageRank Centrality", self.body_style),
            ],
            [
                Paragraph("Resilience & Performance", self.body_style),
                Paragraph(f"{gs.get('resilience_performance', 0):.1f}/100", self.body_style),
                Paragraph("Hotspot Profiling, Complexity, Exception Safety", self.body_style),
            ],
            [
                Paragraph("DevOps & Developer Hygiene", self.body_style),
                Paragraph(f"{gs.get('dev_hygiene_devops', 0):.1f}/100", self.body_style),
                Paragraph("License Compliance, Docstring Coverage, Style Drift", self.body_style),
            ],
        ]

        group_table = Table(group_data, colWidths=[175, 115, 225])
        group_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ])
        )
        story.append(group_table)
        story.append(Spacer(1, 14))

        # 4. Critical Findings & Highlights
        story.append(Paragraph("3. Governance & Risk Highlights", self.section_header))

        highlights = []
        # Check secrets
        entropy_findings = data.get("layer1", {}).get("entropy", {}).get("findings", [])
        if entropy_findings:
            highlights.append(
                f"🚨 <b>Secret Exposure:</b> {len(entropy_findings)} high-entropy string literals detected. "
                "Immediate credential rotation and secret manager migration required."
            )
        else:
            highlights.append("✅ <b>Secret Detection:</b> No high-entropy API keys or credentials detected in scanned files.")

        # Check circular dependencies
        cycles = data.get("layer1", {}).get("circular_dependencies", {}).get("cycles", [])
        if cycles:
            highlights.append(
                f"⚠️ <b>Circular Dependency:</b> {len(cycles)} recursive import cycles identified. "
                "Refactor shared models to establish an Acyclic DAG."
            )
        else:
            highlights.append("✅ <b>Architecture Cleanliness:</b> Zero circular import cycles (clean Acyclic DAG).")

        # Check regression
        regression = data.get("regression_warning") or data.get("regression")
        if regression:
            highlights.append(f"⚠️ <b>Regression Alert:</b> {regression}")

        for h in highlights:
            story.append(Paragraph(f"• {h}", self.body_style))
            story.append(Spacer(1, 3))

        story.append(Spacer(1, 10))

        # 5. Strategic Recommendations
        story.append(Paragraph("4. Recommended Next Actions", self.section_header))
        recs = [
            "Enforce WARDEN pre-commit and pre-push quality gates across all active engineering branches.",
            "Address cyclomatic complexity hotspots where CC > 10 using guard clauses and sub-routine decomposition.",
            "Upload generated SARIF artifacts (<code>warden-results.sarif</code>) into GitHub Security Code Scanning tab.",
            "Verify all external supply chain packages against typosquatting indices before deployment to staging.",
        ]
        for r in recs:
            story.append(Paragraph(f"1. {r}", self.body_style))
            story.append(Spacer(1, 3))

        return story
