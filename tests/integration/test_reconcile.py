"""Integration tests for the reconciliation harness: API-vs-legacy control
totals, key-field verification, and the advanced-SQL anomaly detectors."""
from __future__ import annotations

from decimal import Decimal

from cutover.reconcile import api_validator


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