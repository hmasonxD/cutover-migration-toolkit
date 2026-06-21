"""Orchestrate a full migration run: extract -> transform -> load, with the
utility ledger cleansed alongside the tax roll. Returns a summary the caller can
log or surface in the dashboard."""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from ..config import settings
from . import extract, load
from .transform import (
    Exception_,
    TransformError,
    normalize_roll,
    parse_legacy_date,
    parse_money,
    transform_properties,
)


@dataclass
class MigrationSummary:
    properties_extracted: int
    properties_loaded: int
    property_exceptions: list[Exception_]
    transactions_extracted: int
    transactions_loaded: int
    transaction_exceptions: list[Exception_]


_TXN_TYPES = {"CHARGE", "PAYMENT", "ADJUST"}


def _transform_transactions(rows: list[dict]):
    clean, exceptions = [], []
    for row in rows:
        try:
            roll = normalize_roll(row.get("roll_no"))
            txn_type = (row.get("txn_type") or "").strip().upper()
            if txn_type not in _TXN_TYPES:
                raise TransformError(f"unknown txn_type: {row.get('txn_type')!r}")
            txn_date = parse_legacy_date(row.get("txn_dt"))
            if txn_date is None:
                raise TransformError("missing transaction date")
            amount = parse_money(row.get("amount"))
            clean.append(
                {"roll_number": roll, "txn_date": txn_date, "txn_type": txn_type, "amount": amount}
            )
        except TransformError as exc:
            exceptions.append(
                Exception_(source_id=row.get("txn_id"), roll_no_raw=row.get("roll_no"), reason=str(exc))
            )
    return clean, exceptions


def run_migration(client: httpx.Client | None = None) -> MigrationSummary:
    owns_client = client is None
    client = client or httpx.Client(base_url=settings.api_base_url, timeout=60)
    try:
        tax_rows = extract.extract_tax_master()
        result = transform_properties(tax_rows)
        loaded_props = load.load_properties(result.clean, client=client)

        ledger_rows = extract.extract_util_ledger()
        clean_txns, txn_exc = _transform_transactions(ledger_rows)
        loaded_txns = load.load_transactions(clean_txns, client=client)

        return MigrationSummary(
            properties_extracted=len(tax_rows),
            properties_loaded=loaded_props,
            property_exceptions=result.exceptions,
            transactions_extracted=len(ledger_rows),
            transactions_loaded=loaded_txns,
            transaction_exceptions=txn_exc,
        )
    finally:
        if owns_client:
            client.close()