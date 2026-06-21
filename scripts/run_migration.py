"""Execute a full migration run against the live cloud API.

Prereqs: databases provisioned (scripts.setup_db) and the API running
(uvicorn cutover.cloud.api:app).  Usage:  python -m scripts.run_migration
"""
from __future__ import annotations

from cutover.etl.pipeline import run_migration


def main() -> None:
    s = run_migration()
    print("MIGRATION SUMMARY")
    print(f"  properties: extracted={s.properties_extracted} loaded={s.properties_loaded} "
          f"exceptions={len(s.property_exceptions)}")
    for e in s.property_exceptions:
        print(f"    ! rec {e.source_id} ({e.roll_no_raw}): {e.reason}")
    print(f"  transactions: extracted={s.transactions_extracted} loaded={s.transactions_loaded} "
          f"exceptions={len(s.transaction_exceptions)}")
    for e in s.transaction_exceptions:
        print(f"    ! txn {e.source_id} ({e.roll_no_raw}): {e.reason}")


if __name__ == "__main__":
    main()