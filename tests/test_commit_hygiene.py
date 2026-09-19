import pytest
from pathlib import Path
from core.services.commit_hygiene import CommitHygieneService

@pytest.mark.asyncio
async def test_commit_hygiene():
    service = CommitHygieneService()
    res = await service.analyze(Path("."))
    
    assert res.score >= 20.0 and res.score <= 100.0
    assert res.total_commits >= 0
    assert res.bad_commits >= 0
