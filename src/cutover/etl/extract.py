"""Extract raw rows from the legacy system. Read-only by design."""
from __future__ import annotations

from .. import db


def extract_tax_master() -> list[dict]:
    with db.legacy_conn() as conn:
        return db.query_all(conn, "SELECT * FROM legacy.tax_master ORDER BY rec_id")


def extract_util_ledger() -> list[dict]:
    with db.legacy_conn() as conn:
        return db.query_all(conn, "SELECT * FROM legacy.util_ledger ORDER BY txn_id")