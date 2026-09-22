"""Database connection, multi-dialect support (SQLite + PostgreSQL), and connection pooling."""

import logging
import os
from typing import Any

from sqlalchemy import text
from sqlmodel import SQLModel, create_engine

logger = logging.getLogger(__name__)

RAW_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///warden.db").strip()

# Normalize legacy postgres:// to postgresql:// (Heroku/Render/Supabase compatibility)
if RAW_DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = RAW_DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    DATABASE_URL = RAW_DATABASE_URL

# Multi-dialect engine configuration
_engine_kwargs: dict[str, Any] = {"echo": False}

if DATABASE_URL.startswith("sqlite"):
    # SQLite-specific connection arguments for multi-threaded FastAPI access
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
elif DATABASE_URL.startswith("postgresql"):
    # PostgreSQL production connection pooling configuration
    _engine_kwargs.update({
        "pool_size": int(os.getenv("DB_POOL_SIZE", "10")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "20")),
        "pool_pre_ping": True,
        "pool_recycle": 300,
    })

engine = create_engine(DATABASE_URL, **_engine_kwargs)


def create_db_and_tables() -> None:
    """Creates database tables and applies non-destructive schema migrations."""
    # Import all models here so SQLModel knows about them before creating tables
    from core.models.audit import AuditCoreMember, AuditReport  # noqa: F401
    SQLModel.metadata.create_all(engine)

    # Safe auto-migration for SQLite development database
    if engine.dialect.name == "sqlite":
        _safe_migrations = [
            # audit_core_members columns
            "ALTER TABLE audit_core_members ADD COLUMN weight_at_time REAL",
            "ALTER TABLE audit_core_members ADD COLUMN catalog_version TEXT",
            "ALTER TABLE audit_core_members ADD COLUMN created_at TIMESTAMP",
            # auditreport milestone columns (added in Phase 0 refactor)
            "ALTER TABLE auditreport ADD COLUMN is_milestone INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE auditreport ADD COLUMN milestone_label TEXT",
        ]

        with engine.connect() as conn:
            for sql in _safe_migrations:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                except Exception:
                    pass  # Column already exists — safe to ignore
