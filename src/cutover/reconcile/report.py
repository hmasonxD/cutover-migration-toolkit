"""Render a reconciliation report - the artifact the implementation team reviews
before sign-off."""
from __future__ import annotations

from tabulate import tabulate

from .api_validator import CheckResult


def render_report(checks: list[CheckResult], duplicates: list[dict], balance_exc: list[dict]) -> str:
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append(" CUTOVER RECONCILIATION REPORT")
    lines.append("=" * 64)

    rows = [
        [c.name, "PASS" if c.passed else "FAIL", c.legacy_value, c.cloud_value, c.detail]
        for c in checks
    ]
    lines.append(
        tabulate(rows, headers=["Check", "Result", "Legacy", "Cloud", "Detail"], tablefmt="github")
    )

    all_pass = all(c.passed for c in checks)
    lines.append("")
    lines.append(f"CONTROL CHECKS: {'ALL PASS - cleared for go-live' if all_pass else 'FAILURES PRESENT - hold'}")
    lines.append("")

    lines.append(f"Duplicate roll numbers in legacy (cleansing required): {len(duplicates)}")
    for d in duplicates[:10]:
        lines.append(f"  - roll {d['roll_digits']} appears {d['occurrences']}x (rec_id {d['rec_id']}, seq {d['seq']})")

    lines.append("")
    lines.append(f"Ledger balance exceptions (legacy stored != recomputed): {len(balance_exc)}")
    for b in balance_exc[:10]:
        lines.append(
            f"  - roll {b['roll_digits']}: stored={b['stored_balance']} computed={b['computed_balance']}"
        )

    lines.append("=" * 64)
    return "\n".join(lines)