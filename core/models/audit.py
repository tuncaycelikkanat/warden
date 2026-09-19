from typing import Optional, Dict, Any
from sqlmodel import SQLModel, Field, Column, JSON
from datetime import datetime, timezone

class AuditReport(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    repo_path: str
    total_score: int
    grade: str
    profile_signature: str
    layer1_score: int
    layer2_score: int
    
    group_security: Optional[float] = None
    group_code_health: Optional[float] = None
    group_structural: Optional[float] = None
    group_resilience: Optional[float] = None
    group_dev_hygiene: Optional[float] = None

    raw_data: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class AuditCoreMember(SQLModel, table=True):
    __tablename__ = "audit_core_members"
    id: Optional[int] = Field(default=None, primary_key=True)
    report_id: int = Field(foreign_key="auditreport.id")
    group_key: str
    member_key: str
    member_label: str
    score: float
    weight_at_time: Optional[float] = None
    catalog_version: Optional[str] = None
    details: Optional[str] = None  # JSON olarak detaylar
