"""Run the full reconciliation suite and print the report.

Usage:  python -m scripts.run_reconciliation
"""
from __future__ import annotations

from cutover.reconcile import api_validator, report


def main() -> None:
    checks = api_validator.run_all_checks()
    duplicates = api_validator.find_duplicate_rolls()
    balance_exc = api_validator.find_balance_exceptions()
    print(report.render_report(checks, duplicates, balance_exc))


if __name__ == "__main__":
    main()