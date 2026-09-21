"""Data models for audit reports and core member scores."""

from datetime import UTC, datetime
from typing import Any

from sqlmodel import JSON, Column, Field, SQLModel


class AuditReport(SQLModel, table=True):
    """Database model storing historical audit reports and group scores."""
    id: int | None = Field(default=None, primary_key=True)
    repo_path: str
    total_score: int
    grade: str
    profile_signature: str
    layer1_score: int
    layer2_score: int = Field(default=-1)  # -1 represents unmeasured Layer 2
    
    group_security: float | None = None
    group_code_health: float | None = None
    group_structural: float | None = None
    group_resilience: float | None = None
    group_dev_hygiene: float | None = None

    raw_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuditCoreMember(SQLModel, table=True):
    """Database model storing granular member scores per audit execution."""
    __tablename__ = "audit_core_members"
    id: int | None = Field(default=None, primary_key=True)
    report_id: int = Field(foreign_key="auditreport.id")
    group_key: str
    member_key: str
    member_label: str
    score: float
    weight_at_time: float | None = None
    catalog_version: str | None = None
    details: str | None = None  # JSON olarak detaylar
