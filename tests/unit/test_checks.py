"""Unit tests for utility-transaction cleansing (no DB required).

Covers _transform_transactions: roll normalization, money parsing (including
negative/parenthesized amounts), txn-type validation, date parsing, and the
partitioning of clean rows from exceptions.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from cutover.etl.pipeline import _transform_transactions


class TestTransactionHappyPath:
    def test_clean_transactions_pass_through(self):
        rows = [
            {"txn_id": 1, "roll_no": "001-2345-00", "txn_dt": "2024-01-15",
             "txn_type": "CHARGE", "amount": "$500.00", "balance": "$500.00"},
            {"txn_id": 2, "roll_no": "001 2345 00", "txn_dt": "06/15/2024",
             "txn_type": "payment", "amount": "(250.00)", "balance": "$250.00"},
        ]
        clean, exc = _transform_transactions(rows)
        assert len(clean) == 2
        assert not exc
        assert clean[0]["amount"] == Decimal("500.00")
        assert clean[1]["amount"] == Decimal("-250.00")
        assert clean[1]["txn_type"] == "PAYMENT"
        assert clean[1]["txn_date"] == date(2024, 6, 15)

    def test_normalizes_roll_formatting_variants(self):
        rows = [
            {"txn_id": 1, "roll_no": "001-2345-00", "txn_dt": "2024-01-15",
             "txn_type": "CHARGE", "amount": "$100.00", "balance": "$100.00"},
            {"txn_id": 2, "roll_no": "001 2345 00", "txn_dt": "2024-02-15",
             "txn_type": "CHARGE", "amount": "$50.00", "balance": "$150.00"},
        ]
        clean, exc = _transform_transactions(rows)
        assert not exc
        assert clean[0]["roll_number"] == clean[1]["roll_number"] == "001-2345-00"

    def test_parses_negative_payment_amount(self):
        rows = [{"txn_id": 1, "roll_no": "001234500", "txn_dt": "2024-01-15",
                 "txn_type": "PAYMENT", "amount": "(250.00)", "balance": "0.00"}]
        clean, exc = _transform_transactions(rows)
        assert not exc
        assert clean[0]["amount"] == Decimal("-250.00")

    def test_txn_type_is_uppercased(self):
        rows = [{"txn_id": 1, "roll_no": "001234500", "txn_dt": "2024-01-15",
                 "txn_type": "charge", "amount": "$1.00", "balance": "$1.00"}]
        clean, exc = _transform_transactions(rows)
        assert clean[0]["txn_type"] == "CHARGE"

    def test_adjust_type_is_valid(self):
        rows = [{"txn_id": 1, "roll_no": "001234500", "txn_dt": "2024-01-15",
                 "txn_type": "ADJUST", "amount": "$10.00", "balance": "$10.00"}]
        clean, exc = _transform_transactions(rows)
        assert not exc
        assert clean[0]["txn_type"] == "ADJUST"


class TestTransactionExceptions:
    def test_unknown_txn_type_is_exception(self):
        rows = [{"txn_id": 9, "roll_no": "001234500", "txn_dt": "2024-01-15",
                 "txn_type": "REFUND", "amount": "$1.00", "balance": "$1.00"}]
        clean, exc = _transform_transactions(rows)
        assert not clean
        assert len(exc) == 1
        assert "txn_type" in exc[0].reason

    def test_missing_date_is_exception(self):
        rows = [{"txn_id": 9, "roll_no": "001234500", "txn_dt": "",
                 "txn_type": "CHARGE", "amount": "$1.00", "balance": "$1.00"}]
        clean, exc = _transform_transactions(rows)
        assert not clean
        assert len(exc) == 1
        assert "date" in exc[0].reason.lower()

    def test_bad_roll_is_exception_with_source_id(self):
        rows = [{"txn_id": 77, "roll_no": "12-34", "txn_dt": "2024-01-15",
                 "txn_type": "CHARGE", "amount": "$1.00", "balance": "$1.00"}]
        clean, exc = _transform_transactions(rows)
        assert not clean
        assert len(exc) == 1
        assert exc[0].source_id == 77
        assert "roll" in exc[0].reason.lower()

    def test_unparseable_amount_is_exception(self):
        rows = [{"txn_id": 1, "roll_no": "001234500", "txn_dt": "2024-01-15",
                 "txn_type": "CHARGE", "amount": "N/A", "balance": "$1.00"}]
        clean, exc = _transform_transactions(rows)
        assert not clean
        assert len(exc) == 1
        assert "money" in exc[0].reason

    def test_mixed_batch_partitions_correctly(self):
        rows = [
            {"txn_id": 1, "roll_no": "001234500", "txn_dt": "2024-01-15",
             "txn_type": "CHARGE", "amount": "$100.00", "balance": "$100.00"},
            {"txn_id": 2, "roll_no": "bad", "txn_dt": "2024-01-15",
             "txn_type": "CHARGE", "amount": "$1.00", "balance": "$1.00"},
            {"txn_id": 3, "roll_no": "001234500", "txn_dt": "garbage",
             "txn_type": "CHARGE", "amount": "$1.00", "balance": "$1.00"},
        ]
        clean, exc = _transform_transactions(rows)
        assert len(clean) == 1
        assert len(exc) == 2