import os

def create_fixtures():
    base = "tests/fixtures"
    os.makedirs(base, exist_ok=True)
    
    # BAD REPO
    bad = os.path.join(base, "repo_bad")
    os.makedirs(bad, exist_ok=True)
    with open(os.path.join(bad, "main.py"), "w") as f:
        f.write("""import sqlite3
import requests

def get_user(user_input):
    try:
        q = f"SELECT * FROM users WHERE id = {user_input}"
        conn = sqlite3.connect("users.db")
        conn.execute(q)
        requests.get("http://api.internal/log?q=" + q, verify=False)
        return q
    except:
        pass

def delete_user(user_input):
    try:
        q = f"DELETE FROM users WHERE name = '{user_input}'"
        return q
    except:
        pass

def deeply_nested_bad_function(a, b, c, d, e, f, g):
    if a:
        if b:
            if c:
                if d:
                    if e:
                        if f:
                            if g:
                                return 1
                            return 2
                        return 3
                    return 4
                return 5
            return 6
        return 7
    return 0
""")
    with open(os.path.join(bad, "dummy.txt"), "w") as f:
        f.write("STRIPE_KEY=sk_live_abc123deadbeef\n")
    with open(os.path.join(bad, "requirements.txt"), "w") as f:
        f.write("flask\nrequests\n")

    # MEDIUM REPO
    medium = os.path.join(base, "repo_medium")
    os.makedirs(medium, exist_ok=True)
    with open(os.path.join(medium, "main.py"), "w") as f:
        f.write("from fastapi import FastAPI\nimport requests\n\napp = FastAPI()\n\ndef fetch_data(url: str):\n    return requests.get(url)\n\n@app.get('/add')\ndef add_numbers(a: int, b: int) -> int:\n    return a + b\n\ndef untyped_calc(x):\n    if x > 10:\n        return x * 2\n    return x\n")
    os.makedirs(os.path.join(medium, "tests"), exist_ok=True)
    with open(os.path.join(medium, "tests", "test_main.py"), "w") as f:
        f.write("from main import add_numbers\n\ndef test_add():\n    assert add_numbers(1, 2) == 3\n\ndef test_placeholder():\n    pass\n")
    os.makedirs(os.path.join(medium, ".github", "workflows"), exist_ok=True)
    with open(os.path.join(medium, ".github", "workflows", "ci.yml"), "w") as f:
        f.write("name: CI\non: [push]\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n    - run: echo hello\n")
    with open(os.path.join(medium, "requirements.txt"), "w") as f:
        f.write("fastapi\nrequests\n")

    # GOOD REPO
    good = os.path.join(base, "repo_good")
    os.makedirs(good, exist_ok=True)
    with open(os.path.join(good, "main.py"), "w") as f:
        f.write('"""Math module."""\n\ndef add(a: int, b: int) -> int:\n    """Add two numbers."""\n    return a + b\n')
    os.makedirs(os.path.join(good, "tests"), exist_ok=True)
    with open(os.path.join(good, "tests", "test_main.py"), "w") as f:
        f.write('"""Tests for main."""\nfrom main import add\n\ndef test_add():\n    assert add(1, 2) == 3\n    assert add(0, 0) == 0\n')
    os.makedirs(os.path.join(good, ".github", "workflows"), exist_ok=True)
    with open(os.path.join(good, ".github", "workflows", "ci.yml"), "w") as f:
        f.write("name: CI\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n    - run: echo hello\n")
    with open(os.path.join(good, "Dockerfile"), "w") as f:
        f.write("FROM python:3.11-slim\nHEALTHCHECK CMD curl --fail http://localhost:8000/ || exit 1\n")
    with open(os.path.join(good, ".env.example"), "w") as f:
        f.write("PORT=8000\n")
    with open(os.path.join(good, "docker-compose.yml"), "w") as f:
        f.write("version: '3.8'\nservices:\n  app:\n    build: .\n")
    with open(os.path.join(good, "LICENSE"), "w") as f:
        f.write("MIT License\n")
    with open(os.path.join(good, "README.md"), "w") as f:
        f.write("# Good Project\n\n## Setup\nRun uv pip install.\n\n## Usage\nRun python main.py.\n")

if __name__ == "__main__":
    create_fixtures()
