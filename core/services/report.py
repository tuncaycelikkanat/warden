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
        scorecard = data["scorecard"]
        report = AuditReport(
            repo_path=repo_path,
            total_score=scorecard["total_score"],
            grade=scorecard["grade"],
            profile_signature=data["profile_signature"],
            layer1_score=scorecard["layer1_score"],
            layer2_score=scorecard["layer2_score"],
            raw_data=data
        )
        
        with Session(engine) as session:
            session.add(report)
            session.commit()
            session.refresh(report)
            return report.id

    def generate_markdown(self, repo_path: str, data: Dict[str, Any]) -> str:
        """Generates WARDEN_SCORECARD.md and saves it to the repo root."""
        scorecard = data["scorecard"]
        
        md = []
        md.append(f"# WARDEN Audit Scorecard")
        md.append(f"**Repository:** `{repo_path}`")
        md.append(f"**Total Score:** `{scorecard['total_score']}/100`")
        md.append(f"**Grade:** `{scorecard['grade']}`")
        md.append(f"**Profile Signature:** `{data['profile_signature']}`\n")
        
        md.append(f"## Layer 1 (Mechanical Checks) - Score: {scorecard['layer1_score']}")
        l1_raw = scorecard["breakdown"]["layer1_raw"]
        md.append(f"- **Coverage:** {l1_raw['coverage']}%")
        md.append(f"- **Lint Errors:** {l1_raw['lint']['error_count']}")
        md.append(f"- **Complexity:** {l1_raw['complexity']['avg_complexity']} avg")
        md.append(f"- **Leaks:** {len(l1_raw['leaks'])}")
        md.append(f"- **Security Findings:** {len(l1_raw['security'])}")
        md.append(f"- **Resilience Findings:** {len(l1_raw['resilience'])}")
        
        vuln_deps = [d for d in l1_raw['dependencies'] if d['known_vulnerabilities'] or d['status'] != 'ok']
        md.append(f"- **Vulnerable Dependencies:** {len(vuln_deps)}")
        
        md.append(f"\n## Layer 2 (LLM Rubric Evaluator) - Score: {scorecard['layer2_score']}")
        l2_raw = scorecard["breakdown"]["layer2_raw"]
        if not l2_raw:
            md.append("*No dynamic categories matched.*")
        else:
            for cat in l2_raw:
                md.append(f"### {cat['label']}")
                verdict = cat["rubric_verdict"]
                md.append(f"- **Level:** {verdict['level']}/10")
                md.append(f"- **Justification:** {verdict['justification']}")
                md.append(f"- **Cited Evidence:** {', '.join(verdict['cited_evidence']) if verdict['cited_evidence'] else 'None'}")
                
        content = "\n".join(md)
        
        # Save to WARDEN_SCORECARD.md
        out_path = Path(repo_path) / "WARDEN_SCORECARD.md"
        out_path.write_text(content, encoding="utf-8")
        logger.info(f"Generated scorecard at {out_path.resolve()}")
        
        return str(out_path.resolve())
