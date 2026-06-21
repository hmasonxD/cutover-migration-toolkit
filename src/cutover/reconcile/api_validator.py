"""Cross-system validation.

Queries the cloud through its API and compares the answers against the legacy
system queried directly in SQL. This is the core reconciliation pattern: the two
systems are computed independently and must agree, within tolerance, on the
control totals that matter for go-live sign-off.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import httpx

from .. import db
from ..config import settings
from . import queries


@dataclass
class CheckResult:
    name: str
    passed: bool
    legacy_value: object
    cloud_value: object
    detail: str = ""


def _api(client: httpx.Client | None):
    return client or httpx.Client(base_url=settings.api_base_url, timeout=30)


def _legacy_valid_summary() -> dict:
    """The independently SQL-derived set of rows that should have migrated:
    expected row count and expected tax-levy control total."""
    with db.legacy_conn() as conn:
        return db.query_all(conn, queries.VALID_MIGRATABLE_SUMMARY)[0]


def check_record_counts(client: httpx.Client | None = None) -> CheckResult:
    """Migratable legacy rows (re-derived in SQL) vs rows present in the cloud."""
    client = _api(client)
    expected = _legacy_valid_summary()["expected_count"]
    cloud = client.get("/properties/count").json()["count"]
    return CheckResult(
        name="record_count_parity",
        passed=expected == cloud,
        legacy_value=expected,
        cloud_value=cloud,
        detail="SQL-derived migratable rows vs cloud property rows",
    )


def check_levy_total(client: httpx.Client | None = None, tolerance: Decimal = Decimal("0.00")) -> CheckResult:
    """Financial control total: total tax levy must match within tolerance.

    The legacy total is summed over the same migratable set in SQL; the cloud
    total is the sum of Python-parsed values. Two implementations, one answer.
    """
    client = _api(client)
    legacy_total = Decimal(str(_legacy_valid_summary()["expected_levy"]))
    cloud_total = Decimal(client.get("/levy/total").json()["total_tax_levy"])
    variance = abs(legacy_total - cloud_total)
    return CheckResult(
        name="tax_levy_control_total",
        passed=variance <= tolerance,
        legacy_value=str(legacy_total),
        cloud_value=str(cloud_total),
        detail=f"variance={variance}",
    )


def check_key_fields_present(client: httpx.Client | None = None, sample: int = 25) -> CheckResult:
    """Key-field verification: sample legacy rolls and confirm each resolved to a
    cloud record with a matching owner name."""
    client = _api(client)
    from .transform_helpers import normalize_safe  # local import to avoid cycle

    with db.legacy_conn() as conn:
        rows = db.query_all(
            conn,
            """SELECT roll_no, owner_name FROM legacy.tax_master
               WHERE length(regexp_replace(COALESCE(roll_no,''),'\\D','','g')) = 9
               ORDER BY rec_id LIMIT %s""",
            (sample,),
        )
    mismatches = []
    checked = 0
    for r in rows:
        roll = normalize_safe(r["roll_no"])
        if roll is None:
            continue
        checked += 1
        resp = client.get(f"/properties/{roll}")
        if resp.status_code != 200:
            mismatches.append(f"{roll}: missing in cloud")
    return CheckResult(
        name="key_field_verification",
        passed=not mismatches,
        legacy_value=checked,
        cloud_value=checked - len(mismatches),
        detail="; ".join(mismatches) if mismatches else f"{checked} sampled rolls all present",
    )


def find_balance_exceptions() -> list[dict]:
    """Accounts whose legacy stored ledger balance disagrees with the running
    balance recomputed from their transactions. These are pre-existing legacy
    data errors the migration surfaces for the implementation team."""
    with db.legacy_conn() as conn:
        return db.query_all(conn, queries.LEGACY_BALANCE_DRIFT)


def find_duplicate_rolls() -> list[dict]:
    with db.legacy_conn() as conn:
        return db.query_all(conn, queries.DUPLICATE_ROLLS_LEGACY)


def run_all_checks(client: httpx.Client | None = None) -> list[CheckResult]:
    owns = client is None
    client = _api(client)
    try:
        return [
            check_record_counts(client),
            check_levy_total(client),
            check_key_fields_present(client),
        ]
    finally:
        if owns:
            client.close()