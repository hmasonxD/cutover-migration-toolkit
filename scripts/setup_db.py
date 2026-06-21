"""Provision both databases from scratch: apply schemas, then seed legacy data.

Usage:  python -m scripts.setup_db
"""
from __future__ import annotations

from pathlib import Path

from cutover import db, seed

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"


def _run_sql_file(conn, path: Path) -> None:
    sql = path.read_text()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def main() -> None:
    with db.legacy_conn() as conn:
        _run_sql_file(conn, SQL_DIR / "legacy_schema.sql")
    print("Legacy schema applied.")

    with db.cloud_conn() as conn:
        _run_sql_file(conn, SQL_DIR / "cloud_schema.sql")
    print("Cloud schema applied.")

    seed.generate()
    print("Legacy data seeded. Setup complete.")


if __name__ == "__main__":
    main()