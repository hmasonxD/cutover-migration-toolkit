"""The Catalis cloud target, as an API.

In the real platform the cloud is reached over HTTP, so the migration loads
through this API and the reconciliation harness validates through it too -
exactly the "API-based tooling to query cloud data and validate against legacy
SQL" the role centers on. Persistence is PostgreSQL.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Optional

import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import db

app = FastAPI(title="Catalis Cloud (simulated)", version="1.0.0")

_STATIC = Path(__file__).resolve().parents[3] / "static"


class PropertyIn(BaseModel):
    roll_number: str
    owner_name: str
    address: Optional[str] = None
    assessed_value: Decimal
    tax_levy: Decimal
    status: str
    last_payment_date: Optional[str] = None  # ISO date string or None


class TransactionIn(BaseModel):
    roll_number: str
    txn_date: str
    txn_type: str
    amount: Decimal


class BulkResult(BaseModel):
    inserted: int = Field(..., description="rows written")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/properties/bulk", response_model=BulkResult)
def ingest_properties(items: list[PropertyIn]) -> BulkResult:
    rows = [
        (
            i.roll_number, i.owner_name, i.address, i.assessed_value,
            i.tax_levy, i.status, i.last_payment_date or None,
        )
        for i in items
    ]
    with db.cloud_conn() as conn:
        with conn.cursor() as cur:
            returned = psycopg2.extras.execute_values(
                cur,
                """INSERT INTO app.property
                   (roll_number, owner_name, address, assessed_value,
                    tax_levy, status, last_payment_date)
                   VALUES %s
                   ON CONFLICT (roll_number) DO NOTHING
                   RETURNING id""",
                rows,
                page_size=len(rows) or 1,
                fetch=True,
            )
            inserted = len(returned)
        conn.commit()
    return BulkResult(inserted=inserted)


@app.post("/transactions/bulk", response_model=BulkResult)
def ingest_transactions(items: list[TransactionIn]) -> BulkResult:
    rows = [(i.roll_number, i.txn_date, i.txn_type, i.amount) for i in items]
    with db.cloud_conn() as conn:
        with conn.cursor() as cur:
            returned = psycopg2.extras.execute_values(
                cur,
                """INSERT INTO app.utility_transaction
                   (roll_number, txn_date, txn_type, amount) VALUES %s
                   RETURNING id""",
                rows,
                page_size=len(rows) or 1,
                fetch=True,
            )
            inserted = len(returned)
        conn.commit()
    return BulkResult(inserted=inserted)


@app.get("/properties/count")
def property_count() -> dict:
    with db.cloud_conn() as conn:
        n = db.query_value(conn, "SELECT count(*) FROM app.property")
    return {"count": n}


@app.get("/properties/{roll_number}")
def get_property(roll_number: str) -> dict:
    with db.cloud_conn() as conn:
        rows = db.query_all(
            conn,
            "SELECT * FROM app.property WHERE roll_number = %s",
            (roll_number,),
        )
    if not rows:
        raise HTTPException(status_code=404, detail="not found")
    return rows[0]


@app.get("/levy/total")
def levy_total() -> dict:
    """Total tax levy across all migrated properties - the financial control
    total reconciled against the legacy sum."""
    with db.cloud_conn() as conn:
        total = db.query_value(
            conn, "SELECT COALESCE(SUM(tax_levy), 0) FROM app.property"
        )
    return {"total_tax_levy": str(total)}


@app.get("/accounts/balances")
def account_balances() -> dict:
    """Closing ledger balance per account, computed in-cloud via the
    window-function stored procedure."""
    with db.cloud_conn() as conn:
        rows = db.query_all(
            conn,
            "SELECT roll_number, final_balance FROM recon.account_final_balances() "
            "ORDER BY roll_number",
        )
    return {"balances": {r["roll_number"]: str(r["final_balance"]) for r in rows}}

@app.get("/recon/summary")
def recon_summary() -> dict:
    """Live reconciliation summary for the dashboard: the control checks plus
    counts of duplicates and balance exceptions found in the legacy data."""
    from ..reconcile import api_validator

    checks = api_validator.run_all_checks()
    duplicates = api_validator.find_duplicate_rolls()
    balance_exc = api_validator.find_balance_exceptions()
    return {
        "checks": [
            {
                "name": c.name,
                "passed": c.passed,
                "legacy": str(c.legacy_value),
                "cloud": str(c.cloud_value),
                "detail": c.detail,
            }
            for c in checks
        ],
        "all_passed": all(c.passed for c in checks),
        "duplicate_count": len({d["roll_digits"] for d in duplicates}),
        "balance_exception_count": len(balance_exc),
    }

@app.get("/")
def dashboard() -> FileResponse:
    return FileResponse(_STATIC / "dashboard.html")