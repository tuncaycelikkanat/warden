from pathlib import Path

import pytest

from core.services.docker_readiness import DockerReadinessService
from core.services.scorecard import ScorecardAggregatorService


@pytest.mark.asyncio
async def test_docker_readiness_current_repo():
    service = DockerReadinessService()
    res = await service.analyze(Path("."))

    assert 0.0 <= res.score <= 100.0
    assert isinstance(res.has_dockerfile, bool)
    assert isinstance(res.has_healthcheck, bool)
    assert isinstance(res.has_non_root_user, bool)
    assert isinstance(res.has_multistage, bool)


@pytest.mark.asyncio
async def test_dockerfile_missing_when_applicable(tmp_path: Path):
    # Web project with FastAPI dependency but no Dockerfile
    req = tmp_path / "requirements.txt"
    req.write_text("fastapi>=0.110.0\nuvicorn>=0.28.0\n")

    service = DockerReadinessService()
    res = await service.analyze(tmp_path)

    assert res.score == 0.0
    assert res.has_dockerfile is False
    assert res.applicable is True
    assert res.measured is True
    assert res.reason == "dockerfile_missing"


@pytest.mark.asyncio
async def test_dockerfile_pure_library_not_applicable(tmp_path: Path):
    # Pure Python library with pyproject.toml and no web framework
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("""
[project]
name = "math-helpers"
version = "0.1.0"
dependencies = ["numpy", "scipy"]
""")

    service = DockerReadinessService()
    res = await service.analyze(tmp_path)

    assert res.applicable is False
    assert res.measured is False
    assert res.reason == "pure_library_containerization_not_applicable"
    assert res.has_dockerfile is False


@pytest.mark.asyncio
async def test_healthcheck_none_rejected(tmp_path: Path):
    # HEALTHCHECK NONE should not count as a valid healthcheck
    df = tmp_path / "Dockerfile"
    df.write_text("""
FROM python:3.12-slim
HEALTHCHECK NONE
USER nobody
""")

    service = DockerReadinessService()
    res = await service.analyze(tmp_path)

    assert res.has_dockerfile is True
    assert res.has_healthcheck is False
    assert res.has_non_root_user is True


@pytest.mark.asyncio
async def test_healthcheck_comment_rejected(tmp_path: Path):
    # Commented out HEALTHCHECK should not count
    df = tmp_path / "Dockerfile"
    df.write_text("""
FROM python:3.12-slim
# HEALTHCHECK --interval=30s CMD curl -f http://localhost:8000/ || exit 1
USER appuser
""")

    service = DockerReadinessService()
    res = await service.analyze(tmp_path)

    assert res.has_dockerfile is True
    assert res.has_healthcheck is False
    assert res.has_non_root_user is True


@pytest.mark.asyncio
async def test_valid_healthcheck_accepted(tmp_path: Path):
    df = tmp_path / "Dockerfile"
    df.write_text("""
FROM python:3.12-slim
HEALTHCHECK --interval=30s --timeout=5s CMD curl -f http://localhost:8000/health || exit 1
USER appuser
""")

    service = DockerReadinessService()
    res = await service.analyze(tmp_path)

    assert res.has_dockerfile is True
    assert res.has_healthcheck is True


@pytest.mark.asyncio
async def test_user_root_rejected(tmp_path: Path):
    df = tmp_path / "Dockerfile"
    df.write_text("""
FROM python:3.12-slim
USER root
""")

    service = DockerReadinessService()
    res = await service.analyze(tmp_path)

    assert res.has_non_root_user is False


@pytest.mark.asyncio
async def test_user_non_root_accepted(tmp_path: Path):
    df = tmp_path / "Dockerfile"
    df.write_text("""
FROM python:3.12-slim
USER 10001:10001
""")

    service = DockerReadinessService()
    res = await service.analyze(tmp_path)

    assert res.has_non_root_user is True


@pytest.mark.asyncio
async def test_multistage_detection(tmp_path: Path):
    df = tmp_path / "Dockerfile"
    df.write_text("""
FROM python:3.12 AS builder
WORKDIR /app
RUN pip install poetry

FROM python:3.12-slim
COPY --from=builder /app /app
USER appuser
""")

    service = DockerReadinessService()
    res = await service.analyze(tmp_path)

    assert res.has_multistage is True


@pytest.mark.asyncio
async def test_empty_env_example_rejected(tmp_path: Path):
    df = tmp_path / "Dockerfile"
    df.write_text("FROM python:3.12-slim\n")
    env_ex = tmp_path / ".env.example"
    env_ex.write_text("   \n\n  ")  # whitespace only

    service = DockerReadinessService()
    res = await service.analyze(tmp_path)

    assert res.has_env_example is False


@pytest.mark.asyncio
async def test_full_production_docker_setup(tmp_path: Path):
    df = tmp_path / "Dockerfile"
    df.write_text("""
FROM python:3.12 AS builder
WORKDIR /build

FROM python:3.12-slim
WORKDIR /app
HEALTHCHECK --interval=15s CMD curl -f http://localhost:8000/ || exit 1
USER 1001
CMD ["uvicorn", "main:app"]
""")
    (tmp_path / ".env.example").write_text("APP_ENV=production\nDATABASE_URL=sqlite:///app.db\n")
    (tmp_path / "docker-compose.yml").write_text("version: '3.8'\nservices:\n  web:\n    build: .\n")

    service = DockerReadinessService()
    res = await service.analyze(tmp_path)

    assert res.has_dockerfile is True
    assert res.has_healthcheck is True
    assert res.has_non_root_user is True
    assert res.has_multistage is True
    assert res.has_env_example is True
    assert res.has_docker_compose is True
    assert res.score == 100.0


@pytest.mark.asyncio
async def test_subdirectory_dockerfile_discovery(tmp_path: Path):
    docker_dir = tmp_path / "docker"
    docker_dir.mkdir(parents=True, exist_ok=True)
    df = docker_dir / "Dockerfile"
    df.write_text("""
FROM python:3.12-slim
USER nonroot
""")

    service = DockerReadinessService()
    res = await service.analyze(tmp_path)

    assert res.has_dockerfile is True
    assert res.has_non_root_user is True
    assert res.dockerfile_path == "docker/Dockerfile"


def test_scorecard_redistribution_when_not_applicable():
    aggregator = ScorecardAggregatorService()
    # If docker_readiness is not measured (e.g. pure library), its 1/7 weight is redistributed
    raw_data = {
        "documentation": 80.0,
        "cicd_presence": 100.0,
        "commit_hygiene": 90.0,
        "docker_readiness": {
            "score": 100.0,
            "applicable": False,
            "measured": False,
        },
    }
    member_scores = aggregator._extract_member_scores(raw_data)
    assert "docker_readiness" not in member_scores
    group_scores = aggregator._calc_group_scores(member_scores)

    # dev_hygiene_devops group has 4 members:
    # documentation (3/7), cicd_presence (2/7), docker_readiness (1/7), commit_hygiene (1/7)
    # Active weights: 3/7 + 2/7 + 1/7 = 6/7
    # Expected weighted score: (80*(3/7) + 100*(2/7) + 90*(1/7)) / (6/7) = (240 + 200 + 90)/6 = 530/6 = 88.33
    assert group_scores["dev_hygiene_devops"] == 88.33

