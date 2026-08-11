from fastapi import FastAPI

app = FastAPI(title="warden API")

@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok"}
