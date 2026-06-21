"""Load cleansed records into the cloud through its API.

Loading through the API (not raw INSERTs) means the migration exercises the same
validation path the live product uses, so go-live behaviour matches the dry run.
"""
from __future__ import annotations

from decimal import Decimal

import httpx

from ..config import settings
from .transform import CleanProperty


def _serialize_property(p: CleanProperty) -> dict:
    return {
        "roll_number": p.roll_number,
        "owner_name": p.owner_name,
        "address": p.address,
        "assessed_value": str(p.assessed_value),
        "tax_levy": str(p.tax_levy),
        "status": p.status,
        "last_payment_date": p.last_payment_date.isoformat() if p.last_payment_date else None,
    }


def load_properties(props: list[CleanProperty], client: httpx.Client | None = None) -> int:
    payload = [_serialize_property(p) for p in props]
    owns_client = client is None
    client = client or httpx.Client(base_url=settings.api_base_url, timeout=30)
    try:
        resp = client.post("/properties/bulk", json=payload)
        resp.raise_for_status()
        return resp.json()["inserted"]
    finally:
        if owns_client:
            client.close()


def load_transactions(txns: list[dict], client: httpx.Client | None = None) -> int:
    payload = [
        {
            "roll_number": t["roll_number"],
            "txn_date": t["txn_date"].isoformat() if hasattr(t["txn_date"], "isoformat") else t["txn_date"],
            "txn_type": t["txn_type"],
            "amount": str(t["amount"]) if isinstance(t["amount"], Decimal) else t["amount"],
        }
        for t in txns
    ]
    owns_client = client is None
    client = client or httpx.Client(base_url=settings.api_base_url, timeout=30)
    try:
        resp = client.post("/transactions/bulk", json=payload)
        resp.raise_for_status()
        return resp.json()["inserted"]
    finally:
        if owns_client:
            client.close()