"""Database connection and table initialization infrastructure."""

from sqlmodel import SQLModel, create_engine

DATABASE_URL = "sqlite:///warden.db"

engine = create_engine(DATABASE_URL, echo=False)


def create_db_and_tables() -> None:
    """Creates database tables and applies non-destructive schema migrations."""
    # Import all models here so SQLModel knows about them before creating tables
    SQLModel.metadata.create_all(engine)
    
    # Safe auto-migration for SQLite development database
    from sqlalchemy import text
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE audit_core_members ADD COLUMN weight_at_time REAL"))
            conn.commit()
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE audit_core_members ADD COLUMN catalog_version TEXT"))
            conn.commit()
        except Exception:
            pass
