from typing import Optional
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field

class ScanResult(SQLModel, table=True):
    __tablename__ = "scan_results"

    id: Optional[int] = Field(default=None, primary_key=True)
    repo_path: str
    file_path: str
    commit_hash: Optional[str] = None
    risk_level: Optional[str] = None
    findings_json: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
