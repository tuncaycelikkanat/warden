from sqlmodel import SQLModel, create_engine

DATABASE_URL = "sqlite:///warden.db"

engine = create_engine(DATABASE_URL, echo=False)

def create_db_and_tables():
    # Import all models here so SQLModel knows about them before creating tables
    from core.models.scan import ScanResult
    SQLModel.metadata.create_all(engine)
