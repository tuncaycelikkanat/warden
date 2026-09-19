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
    raw_data: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
