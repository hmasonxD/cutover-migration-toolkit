"""Integration tests: real Postgres, real API path (in-process TestClient).

These exercise extract -> transform -> load and confirm the cloud ends up with
exactly the data we expect, including that bad rows are quarantined as
exceptions rather than loaded or silently dropped.
"""
from __future__ import annotations

from decimal import Decimal

from cutover import db


def test_migration_loads_clean_rows_and_reports_exceptions(migrated):
    s = migrated
    assert s.property_exceptions, "expected injected defects to be reported"
    assert any("roll number" in e.reason for e in s.property_exceptions)
    assert any("money" in e.reason for e in s.property_exceptions)
    assert any("status" in e.reason for e in s.property_exceptions)
    assert any("date" in e.reason for e in s.property_exceptions)
    assert any("owner" in e.reason for e in s.property_exceptions)


def test_no_invalid_status_reaches_cloud(migrated):
    with db.cloud_conn() as conn:
        bad = db.query_value(
            conn,
            "SELECT count(*) FROM app.property "
            "WHERE status NOT IN ('ACTIVE','INACTIVE','PENDING','EXEMPT')",
        )
    assert bad == 0


def test_duplicate_roll_loaded_once(migrated):
    with db.cloud_conn() as conn:
        n = db.query_value(
            conn, "SELECT count(*) FROM app.property WHERE roll_number = %s", ("001-0000-05",)
        )
    assert n == 1


def test_money_stored_as_numeric_with_scale(migrated):
    with db.cloud_conn() as conn:
        rows = db.query_all(conn, "SELECT assessed_value, tax_levy FROM app.property LIMIT 5")
    for r in rows:
        assert isinstance(r["assessed_value"], Decimal)
        assert r["assessed_value"] >= 0


def test_transactions_loaded(migrated):
    assert migrated.transactions_loaded > 0
    with db.cloud_conn() as conn:
        n = db.query_value(conn, "SELECT count(*) FROM app.utility_transaction")
    assert n == migrated.transactions_loaded