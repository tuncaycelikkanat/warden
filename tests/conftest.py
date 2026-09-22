"""Global pytest configuration and fixtures for WARDEN test suite."""

import pytest
from core.infra.database import create_db_and_tables


@pytest.fixture(autouse=True, scope="session")
def setup_test_db() -> None:
    """Ensures all database tables and schema migrations are applied before running tests."""
    create_db_and_tables()
