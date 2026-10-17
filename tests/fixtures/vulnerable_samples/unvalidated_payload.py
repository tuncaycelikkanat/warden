"""Dummy validation test file for schema checking."""

from fastapi import FastAPI

app = FastAPI()


@app.post("/users")
def create_user(payload: dict):
    """Endpoint with raw dict payload for validator tests."""
    return payload
