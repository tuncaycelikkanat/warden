from datetime import UTC, datetime

from sqlmodel import Session, select

from core.infra.database import engine
from core.models.audit import AuditCoreMember, AuditReport


def test_audit_report_creation():
    report = AuditReport(
        repo_path="/path/to/repo",
        total_score=96,
        grade="A+",
        profile_signature="web_api:fastapi",
        layer1_score=58,
        layer2_score=38,
        group_security=100.0,
        group_code_health=95.0,
        group_structural=90.0,
        group_resilience=100.0,
        group_dev_hygiene=95.0,
        raw_data={"test": "data"},
        created_at=datetime.now(UTC),
    )
    assert report.total_score == 96
    assert report.grade == "A+"
    assert report.group_security == 100.0
    assert report.raw_data == {"test": "data"}


def test_audit_report_db_persistence():
    report = AuditReport(
        repo_path="/test/repo/db",
        total_score=85,
        grade="B",
        profile_signature="cli",
        layer1_score=50,
        layer2_score=35,
    )
    with Session(engine) as session:
        session.add(report)
        session.commit()
        session.refresh(report)

        assert report.id is not None
        fetched = session.exec(select(AuditReport).where(AuditReport.id == report.id)).first()
        assert fetched is not None
        assert fetched.repo_path == "/test/repo/db"

        # Cleanup
        session.delete(fetched)
        session.commit()


def test_audit_core_member_db_persistence():
    member = AuditCoreMember(
        report_id=999,
        group_key="security_supply_chain",
        member_key="security_semgrep",
        member_label="Semgrep SAST",
        score=100.0,
        weight_at_time=0.4375,
        catalog_version="1.0.0",
        details='{"violations": 0}',
    )
    with Session(engine) as session:
        session.add(member)
        session.commit()
        session.refresh(member)

        assert member.id is not None
        fetched = session.exec(select(AuditCoreMember).where(AuditCoreMember.id == member.id)).first()
        assert fetched is not None
        assert fetched.member_label == "Semgrep SAST"
        assert fetched.score == 100.0

        # Cleanup
        session.delete(fetched)
        session.commit()
