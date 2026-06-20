"""Generate realistic, deliberately-dirty legacy data.

Deterministic (fixed seed) so reconciliation results are reproducible across
runs and CI. Includes clean rows plus a controlled set of defects: inconsistent
roll formatting, duplicates, bad money/date/status values, and ledger accounts
whose stored balance drifted from the truth.
"""
from __future__ import annotations

import random

from . import db

random.seed(42)

_FIRST = ["John", "Jane", "Robert", "Mary", "David", "Susan", "James", "Linda", "Michael", "Karen"]
_LAST = ["Smith", "Johnson", "Tremblay", "Cardinal", "Gagnon", "Nguyen", "Macdonald", "Cote", "Singh", "Bouchard"]
_STREETS = ["Main St", "Railway Ave", "1st Ave", "Lakeshore Dr", "Centre St", "5 Range Rd", "Township Rd 540"]


def _fmt_roll(n: int) -> str:
    """Produce a 9-digit roll with a randomly chosen legacy formatting style."""
    digits = f"{n:09d}"
    style = random.choice(["dash", "space", "mixed", "plain"])
    a, b, c = digits[:3], digits[3:7], digits[7:]
    if style == "dash":
        return f"{a}-{b}-{c}"
    if style == "space":
        return f"{a} {b} {c}"
    if style == "mixed":
        return f"{a}-{b} {c}"
    return digits


def _money(v: float) -> str:
    style = random.choice(["dollar", "plain", "comma"])
    if style == "dollar":
        return f"${v:,.2f}"
    if style == "comma":
        return f"{v:,.2f}"
    return f"{v:.2f}"


def _date(y: int, m: int, d: int) -> str:
    import datetime
    dt = datetime.date(y, m, d)
    style = random.choice(["iso", "us", "oracle"])
    if style == "iso":
        return dt.strftime("%Y-%m-%d")
    if style == "us":
        return dt.strftime("%m/%d/%Y")
    return dt.strftime("%d-%b-%y").upper()


def generate(num_clean: int = 120) -> None:
    with db.legacy_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE legacy.tax_master RESTART IDENTITY")
            cur.execute("TRUNCATE legacy.util_ledger RESTART IDENTITY")

            tax_rows = []
            ledger_rows = []
            base_roll = 1_000_000  # ensures 7+ digits; padded to 9

            for i in range(num_clean):
                roll_n = base_roll + i
                roll = _fmt_roll(roll_n)
                owner = (
                    f"{random.choice(_LAST).upper()}, {random.choice(_FIRST)}"
                    if random.random() < 0.5
                    else f"{random.choice(_FIRST)} {random.choice(_LAST)}"
                )
                addr = f"{random.randint(1, 9999)} {random.choice(_STREETS)}"
                assessed = round(random.uniform(80_000, 650_000), 2)
                levy = round(assessed * 0.0125, 2)
                status = random.choice(["A", "A", "A", "I", "P", "X", "a", "i"])
                pay = _date(2024, random.randint(1, 12), random.randint(1, 28)) if random.random() < 0.8 else ""
                tax_rows.append((roll, owner, addr, _money(assessed), _money(levy), status, pay))

                # ledger: a charge then a payment; stored balance usually correct
                roll_digits = f"{roll_n:09d}"
                charge = round(random.uniform(200, 1200), 2)
                payment = round(charge * random.choice([0.0, 0.5, 1.0]), 2)
                ledger_rows.append((roll, _date(2024, 1, 15), "CHARGE", _money(charge), _money(charge)))
                running = charge - payment
                ledger_rows.append((roll, _date(2024, 6, 15), "PAYMENT", _money(-payment), _money(running)))

            # --- injected defects (exceptions the migration must surface) ---
            # 1. duplicate roll (same digits, different formatting)
            dup_digits = base_roll + 5
            tax_rows.append((f"{dup_digits:09d}", "DUPLICATE, Owner", "1 Main St", "$100,000.00", "$1,250.00", "A", "2024-02-02"))
            # 2. bad roll number (too few digits)
            tax_rows.append(("12-34", "BADROLL, Person", "2 Main St", "$100,000.00", "$1,250.00", "A", "2024-02-02"))
            # 3. unparseable money
            tax_rows.append(("002000000", "BADMONEY, Person", "3 Main St", "N/A", "$1,250.00", "A", "2024-02-02"))
            # 4. unknown status code
            tax_rows.append(("002000001", "BADSTATUS, Person", "4 Main St", "$100,000.00", "$1,250.00", "Z", "2024-02-02"))
            # 5. unrecognized date
            tax_rows.append(("002000002", "BADDATE, Person", "5 Main St", "$100,000.00", "$1,250.00", "A", "someday"))
            # 6. missing owner name
            tax_rows.append(("002000003", "", "6 Main St", "$100,000.00", "$1,250.00", "A", "2024-02-02"))

            # 7. ledger balance drift: stored balance is wrong on purpose
            drift_roll_n = base_roll + 10
            drift_roll = f"{drift_roll_n:09d}"
            ledger_rows.append((drift_roll, _date(2024, 3, 1), "ADJUST", _money(50.00), _money(99999.00)))  # bogus stored bal

            from psycopg2.extras import execute_values
            execute_values(
                cur,
                "INSERT INTO legacy.tax_master (roll_no, owner_name, prop_addr, assessed_val, tax_levy, status_cd, last_pay_dt) VALUES %s",
                tax_rows,
            )
            execute_values(
                cur,
                "INSERT INTO legacy.util_ledger (roll_no, txn_dt, txn_type, amount, balance) VALUES %s",
                ledger_rows,
            )
        conn.commit()


if __name__ == "__main__":
    generate()
    print("Legacy data seeded.")