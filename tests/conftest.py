"""Shared pytest fixtures.

- `clean_db` reprovisions both schemas and reseeds legacy data before a test.
- `api_client` is an httpx client bound to the FastAPI app in-process (no live
  server needed), so integration tests run the real load + reconciliation path.
"""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from cutover import db, seed
from cutover.cloud.api import app

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"


def _run_sql_file(conn, path: Path) -> None:
    with conn.cursor() as cur:
        cur.execute(path.read_text())
    conn.commit()


@pytest.fixture
def clean_db():
    """Reprovision both databases and reseed legacy data."""
    with db.legacy_conn() as conn:
        _run_sql_file(conn, SQL_DIR / "legacy_schema.sql")
    with db.cloud_conn() as conn:
        _run_sql_file(conn, SQL_DIR / "cloud_schema.sql")
    seed.generate()
    yield


@pytest.fixture
def api_client():
    """An httpx client wired to the FastAPI app in-process."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
def migrated(clean_db, api_client):
    """A fully migrated cloud: runs the real pipeline through the test client."""
    from cutover.etl.pipeline import run_migration
    summary = run_migration(client=api_client)
    yield summary