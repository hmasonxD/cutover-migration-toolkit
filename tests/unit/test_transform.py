"""Unit tests for the pure transform layer. No database required."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from cutover.etl import transform as t


class TestParseMoney:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("$250,000.00", Decimal("250000.00")),
            ("250000", Decimal("250000.00")),
            ("  1,234.5 ", Decimal("1234.50")),
            ("(1,000.00)", Decimal("-1000.00")),
            ("$0.00", Decimal("0.00")),
            ("-45.00", Decimal("-45.00")),
        ],
    )
    def test_parses_known_formats(self, raw, expected):
        assert t.parse_money(raw) == expected

    def test_always_two_decimal_places(self):
        assert t.parse_money("100").as_tuple().exponent == -2

    @pytest.mark.parametrize("raw", ["", "   ", None, "N/A", "abc", "()"])
    def test_rejects_garbage(self, raw):
        with pytest.raises(t.TransformError):
            t.parse_money(raw)


class TestNormalizeRoll:
    @pytest.mark.parametrize(
        "raw",
        ["001-2345-00", "001 2345 00", "0012345 00", "001234500", "001-2345 00"],
    )
    def test_equivalent_formats_collapse_to_canonical(self, raw):
        assert t.normalize_roll(raw) == "001-2345-00"

    def test_rejects_wrong_digit_count(self):
        with pytest.raises(t.TransformError):
            t.normalize_roll("12-34")

    def test_rejects_none(self):
        with pytest.raises(t.TransformError):
            t.normalize_roll(None)


class TestCleanOwnerName:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("SMITH, JOHN A", "John A Smith"),
            ("  jane doe ", "Jane Doe"),
            ("Tremblay,  Marie", "Marie Tremblay"),
            ("robert  macdonald", "Robert Macdonald"),
        ],
    )
    def test_cleans_and_reorders(self, raw, expected):
        assert t.clean_owner_name(raw) == expected

    @pytest.mark.parametrize("raw", ["", "   ", None])
    def test_rejects_missing(self, raw):
        with pytest.raises(t.TransformError):
            t.clean_owner_name(raw)


class TestParseLegacyDate:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("2024-03-01", date(2024, 3, 1)),
            ("03/01/2024", date(2024, 3, 1)),
            ("01-MAR-24", date(2024, 3, 1)),
        ],
    )
    def test_parses_each_format(self, raw, expected):
        assert t.parse_legacy_date(raw) == expected

    @pytest.mark.parametrize("raw", ["", "   ", None])
    def test_empty_is_none_not_error(self, raw):
        assert t.parse_legacy_date(raw) is None

    def test_rejects_unknown_format(self):
        with pytest.raises(t.TransformError):
            t.parse_legacy_date("someday")


class TestMapStatus:
    @pytest.mark.parametrize(
        "raw,expected",
        [("A", "ACTIVE"), ("a", "ACTIVE"), ("I", "INACTIVE"),
         ("P", "PENDING"), ("X", "EXEMPT"), (" x ", "EXEMPT")],
    )
    def test_maps_codes(self, raw, expected):
        assert t.map_status(raw) == expected

    @pytest.mark.parametrize("raw", ["Z", "", None, "active"])
    def test_rejects_unknown(self, raw):
        with pytest.raises(t.TransformError):
            t.map_status(raw)


class TestTransformBatch:
    def test_partitions_clean_from_exceptions(self):
        rows = [
            {"rec_id": 1, "roll_no": "001-2345-00", "owner_name": "SMITH, JOHN",
             "prop_addr": "1 Main", "assessed_val": "$100,000.00", "tax_levy": "$1,250.00",
             "status_cd": "A", "last_pay_dt": "2024-01-01"},
            {"rec_id": 2, "roll_no": "bad", "owner_name": "X",
             "prop_addr": "", "assessed_val": "$1.00", "tax_levy": "$1.00",
             "status_cd": "A", "last_pay_dt": ""},
        ]
        result = t.transform_properties(rows)
        assert len(result.clean) == 1
        assert len(result.exceptions) == 1
        assert result.total == 2
        assert result.exceptions[0].source_id == 2

    def test_empty_address_becomes_none(self):
        rows = [{"rec_id": 1, "roll_no": "001234500", "owner_name": "A B",
                 "prop_addr": "   ", "assessed_val": "1", "tax_levy": "1",
                 "status_cd": "A", "last_pay_dt": ""}]
        result = t.transform_properties(rows)
        assert result.clean[0].address is None