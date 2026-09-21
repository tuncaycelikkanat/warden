"""Data models for individual file security scans."""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class ScanResult(SQLModel, table=True):
    """Database model for storing individual file scan findings."""
    __tablename__ = "scan_results"

    id: int | None = Field(default=None, primary_key=True)
    repo_path: str
    file_path: str
    commit_hash: str | None = None
    risk_level: str | None = None
    findings_json: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
