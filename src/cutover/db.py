"""Thin database access layer.

We use psycopg2 directly rather than an ORM. Migration and reconciliation work is
SQL-first: CTEs, window functions, and set-based reconciliation are clearer and
faster expressed as SQL than coaxed out of an ORM.
"""
from __future__ import annotations

import contextlib
from typing import Any, Iterator

import psycopg2
import psycopg2.extras

from .config import settings


@contextlib.contextmanager
def legacy_conn() -> Iterator[psycopg2.extensions.connection]:
    conn = psycopg2.connect(settings.legacy_dsn)
    try:
        yield conn
    finally:
        conn.close()


@contextlib.contextmanager
def cloud_conn() -> Iterator[psycopg2.extensions.connection]:
    conn = psycopg2.connect(settings.cloud_dsn)
    try:
        yield conn
    finally:
        conn.close()


def query_all(conn, sql: str, params: tuple | dict | None = None) -> list[dict[str, Any]]:
    """Run a SELECT and return rows as dicts."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def query_value(conn, sql: str, params: tuple | dict | None = None) -> Any:
    """Run a scalar SELECT and return the single value."""
    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else None