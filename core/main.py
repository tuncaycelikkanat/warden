from fastapi import FastAPI
from contextlib import asynccontextmanager
from core.infra.database import create_db_and_tables

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield

app = FastAPI(title="warden API", lifespan=lifespan)

@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok"}
