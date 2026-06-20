"""Pure transform / cleansing logic.

No database access here on purpose. Every function is a deterministic mapping
from messy legacy text to a clean, typed value (or a precise exception). That
keeps the hard part - the business rules a municipality's data actually needs -
fully unit-testable without standing up a database.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional


class TransformError(ValueError):
    """Raised when a legacy value cannot be cleansed into a valid cloud value."""


# --- money -----------------------------------------------------------------

_MONEY_STRIP = re.compile(r"[,$\s]")


def parse_money(raw: Optional[str]) -> Decimal:
    """Parse legacy text money into a Decimal.

    Handles "$250,000.00", "250000", "  1,234.5 ", and accounting-style
    parentheses for negatives: "(1,000.00)" -> -1000.00.
    """
    if raw is None or str(raw).strip() == "":
        raise TransformError("empty money value")
    s = str(raw).strip()
    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1]
    s = _MONEY_STRIP.sub("", s)
    if s == "":
        raise TransformError(f"unparseable money value: {raw!r}")
    try:
        value = Decimal(s)
    except InvalidOperation as exc:
        raise TransformError(f"unparseable money value: {raw!r}") from exc
    if negative:
        value = -value
    return value.quantize(Decimal("0.01"))


# --- roll numbers ----------------------------------------------------------


def normalize_roll(raw: Optional[str]) -> str:
    """Canonicalize a roll number to ###-####-## (9 digits).

    Legacy stores the same roll as "001-2345-00", "001 2345 00", "0012345 00".
    We strip every non-digit, require exactly 9 digits, and reformat.
    """
    if raw is None:
        raise TransformError("missing roll number")
    digits = re.sub(r"\D", "", str(raw))
    if len(digits) != 9:
        raise TransformError(f"roll number must be 9 digits, got {raw!r} -> {digits!r}")
    return f"{digits[0:3]}-{digits[3:7]}-{digits[7:9]}"


# --- owner names -----------------------------------------------------------


def clean_owner_name(raw: Optional[str]) -> str:
    """Normalize whitespace, casing, and "LAST, FIRST" ordering.

    "SMITH, JOHN A" -> "John A Smith";  "  jane doe " -> "Jane Doe".
    """
    if raw is None or str(raw).strip() == "":
        raise TransformError("missing owner name")
    s = re.sub(r"\s+", " ", str(raw).strip())
    if "," in s:
        last, first = (part.strip() for part in s.split(",", 1))
        s = f"{first} {last}".strip()
    return s.title()


# --- dates -----------------------------------------------------------------

_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d-%b-%y", "%d-%b-%Y")


def parse_legacy_date(raw: Optional[str]) -> Optional[date]:
    """Parse legacy dates across the formats this system emits.

    Empty/None is a valid 'no payment yet' -> None. Anything non-empty that
    matches no known format is an exception, not a silent drop.
    """
    if raw is None or str(raw).strip() == "":
        return None
    s = str(raw).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise TransformError(f"unrecognized date format: {raw!r}")


# --- status codes ----------------------------------------------------------

_STATUS_MAP = {"A": "ACTIVE", "I": "INACTIVE", "P": "PENDING", "X": "EXEMPT"}


def map_status(raw: Optional[str]) -> str:
    if raw is None or str(raw).strip() == "":
        raise TransformError("missing status code")
    code = str(raw).strip().upper()
    if code not in _STATUS_MAP:
        raise TransformError(f"unknown status code: {raw!r}")
    return _STATUS_MAP[code]


# --- record-level transform ------------------------------------------------


@dataclass
class CleanProperty:
    roll_number: str
    owner_name: str
    address: Optional[str]
    assessed_value: Decimal
    tax_levy: Decimal
    status: str
    last_payment_date: Optional[date]


@dataclass
class Exception_:
    """A row that could not be migrated, with the reason - this is what feeds
    the exception report the implementation team reviews."""
    source_id: object
    roll_no_raw: Optional[str]
    reason: str


@dataclass
class TransformResult:
    clean: list[CleanProperty] = field(default_factory=list)
    exceptions: list[Exception_] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.clean) + len(self.exceptions)


def transform_property_row(row: dict) -> CleanProperty:
    """Transform one legacy tax_master row. Raises TransformError on bad data."""
    return CleanProperty(
        roll_number=normalize_roll(row.get("roll_no")),
        owner_name=clean_owner_name(row.get("owner_name")),
        address=(row.get("prop_addr") or "").strip() or None,
        assessed_value=parse_money(row.get("assessed_val")),
        tax_levy=parse_money(row.get("tax_levy")),
        status=map_status(row.get("status_cd")),
        last_payment_date=parse_legacy_date(row.get("last_pay_dt")),
    )


def transform_properties(rows: list[dict]) -> TransformResult:
    """Transform a batch, partitioning clean rows from exceptions."""
    result = TransformResult()
    for row in rows:
        try:
            result.clean.append(transform_property_row(row))
        except TransformError as exc:
            result.exceptions.append(
                Exception_(
                    source_id=row.get("rec_id"),
                    roll_no_raw=row.get("roll_no"),
                    reason=str(exc),
                )
            )
    return result