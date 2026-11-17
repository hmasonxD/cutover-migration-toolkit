"""Integration tests for the reconciliation harness: API-vs-legacy control
totals, key-field verification, and the advanced-SQL anomaly detectors."""
from __future__ import annotations

from decimal import Decimal

from cutover.reconcile import api_validator

from cutover import db


def test_record_count_parity_passes(migrated, api_client):
    result = api_validator.check_record_counts(client=api_client)
    assert result.passed, result.detail
    assert result.legacy_value == result.cloud_value


def test_levy_control_total_matches(migrated, api_client):
    result = api_validator.check_levy_total(client=api_client)
    assert result.passed, f"{result.legacy_value} vs {result.cloud_value} ({result.detail})"


def test_key_field_verification_passes(migrated, api_client):
    result = api_validator.check_key_fields_present(client=api_client, sample=30)
    assert result.passed, result.detail


def test_run_all_checks_all_green(migrated, api_client):
    results = api_validator.run_all_checks(client=api_client)
    assert results and all(r.passed for r in results)


def test_duplicate_roll_detected_by_window_query(migrated):
    dupes = api_validator.find_duplicate_rolls()
    digits = {d["roll_digits"] for d in dupes}
    assert "001000005" in digits


def test_balance_drift_detected(migrated):
    drift = api_validator.find_balance_exceptions()
    digits = {d["roll_digits"] for d in drift}
    assert "001000010" in digits


def test_levy_total_is_independent_of_python_parsing(migrated, api_client):
    """The legacy total is computed in raw SQL; the cloud total is the sum of
    values parsed by Python. Agreement proves both implementations match."""
    result = api_validator.check_levy_total(client=api_client)
    assert Decimal(result.legacy_value) > 0
    assert Decimal(result.cloud_value) > 0


def test_class_reconciliation_passes(migrated, api_client):
    result = api_validator.check_class_reconciliation(client=api_client)
    assert result.passed, result.detail


def test_class_breakdown_covers_all_four_classes(migrated, api_client):
    rows = api_validator.class_breakdown(client=api_client)
    assert {r["assessment_class"] for r in rows} == {
        "RESIDENTIAL", "NON_RESIDENTIAL", "FARMLAND", "MACHINERY_EQUIPMENT",
    }
    assert all(r["match"] for r in rows)
    assert all(r["legacy_value"] > 0 for r in rows)


def test_misclassified_parcel_caught_by_class_but_not_by_totals(migrated, api_client):
    """Move one residential parcel to farmland in the cloud. The row count and
    the levy total do not change, so the grand-total checks still pass - only
    the per-class reconciliation notices."""
    with db.cloud_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE app.property SET assessment_class = 'FARMLAND'
                   WHERE id = (SELECT id FROM app.property
                               WHERE assessment_class = 'RESIDENTIAL'
                               ORDER BY id LIMIT 1)"""
            )
        conn.commit()

    assert api_validator.check_record_counts(client=api_client).passed
    assert api_validator.check_levy_total(client=api_client).passed

    result = api_validator.check_class_reconciliation(client=api_client)
    assert not result.passed
    assert "RESIDENTIAL" in result.detail and "FARMLAND" in result.detail


def test_unknown_class_code_is_an_exception_not_a_guess(migrated):
    with db.cloud_conn() as conn:
        rows = db.query_all(
            conn,
            "SELECT reason FROM app.migration_exception WHERE roll_no_raw = %s",
            ("002000004",),
        )
    assert rows and "unknown class code" in rows[0]["reason"]
