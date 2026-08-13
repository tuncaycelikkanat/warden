from fastapi import FastAPI

app = FastAPI()

@app.post("/users")
def create_user(payload: dict):
    return payload
