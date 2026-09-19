import os
import subprocess

def create_unseen_fixture():
    base = "tests/fixtures/repo_realworld"
    os.makedirs(base, exist_ok=True)
    
    # 1. Source code
    with open(os.path.join(base, "main.py"), "w") as f:
        f.write('''"""Task manager and text processing service."""
import requests
from typing import List, Optional, Dict

class Task:
    def __init__(self, task_id: int, title: str, priority: int = 1):
        self.task_id = task_id
        self.title = title
        self.priority = priority
        self.is_done = False

    def mark_done(self) -> None:
        self.is_done = True

def process_batch(tasks: List[Task], filter_priority: Optional[int] = None) -> List[Dict[str, any]]:
    """Process a batch of tasks with priority filtering."""
    results = []
    for t in tasks:
        if filter_priority is not None and t.priority < filter_priority:
            continue
        status = "COMPLETED" if t.is_done else "PENDING"
        results.append({"id": t.task_id, "title": t.title.strip(), "status": status})
    return results

def send_notification(webhook_url: str, message: str):
    # Missing timeout parameter (triggers resilience AST check)
    return requests.post(webhook_url, json={"msg": message})

def helper_untyped(val):
    return val * 2
''')

    # 2. Tests
    tests_dir = os.path.join(base, "tests")
    os.makedirs(tests_dir, exist_ok=True)
    with open(os.path.join(tests_dir, "test_main.py"), "w") as f:
        f.write('''"""Tests for task manager."""
from main import Task, process_batch

def test_task_creation():
    t = Task(1, "Fix bug", priority=2)
    assert t.task_id == 1
    assert t.is_done is False
    t.mark_done()
    assert t.is_done is True

def test_process_batch():
    tasks = [Task(1, "A", 1), Task(2, "B", 3)]
    res = process_batch(tasks, filter_priority=2)
    assert len(res) == 1
    assert res[0]["id"] == 2

def test_placeholder():
    # Empty test without assertions (triggers test quality notice)
    pass
''')

    # 3. Requirements & License
    with open(os.path.join(base, "requirements.txt"), "w") as f:
        f.write("requests==2.31.0\npydantic==2.6.0\n")

    with open(os.path.join(base, "LICENSE"), "w") as f:
        f.write("MIT License\n")

    # 4. Readme (Setup section only)
    with open(os.path.join(base, "README.md"), "w") as f:
        f.write("# Task Manager Service\n\n## Setup\nRun `pip install -r requirements.txt`.\n")

    # 5. .env.example
    with open(os.path.join(base, ".env.example"), "w") as f:
        f.write("WEBHOOK_URL=http://localhost:9000/webhook\n")

    # 6. Initialize git repo with realistic commits
    try:
        subprocess.run(["git", "init"], cwd=base, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Developer"], cwd=base, check=True)
        subprocess.run(["git", "config", "user.email", "dev@example.com"], cwd=base, check=True)
        subprocess.run(["git", "add", "."], cwd=base, check=True)
        subprocess.run(["git", "commit", "-m", "feat: initial task manager implementation"], cwd=base, check=True)
        # Second commit
        with open(os.path.join(base, "notes.txt"), "w") as f:
            f.write("Some developer notes\n")
        subprocess.run(["git", "add", "notes.txt"], cwd=base, check=True)
        subprocess.run(["git", "commit", "-m", "wip: add notes"], cwd=base, check=True)
    except Exception as e:
        print(f"Git init warning: {e}")

if __name__ == "__main__":
    create_unseen_fixture()
    print("Created unseen fixture at tests/fixtures/repo_realworld")
