"""Reconciliation SQL.

These statements showcase the set-based work the role calls for: CTEs, window
functions, and reconciliation queries. They run inside a single database; the
cross-system (legacy vs cloud) comparisons live in api_validator.py because the
two systems are independent databases.
"""

# Independently re-derive, in SQL, the set of rows that SHOULD migrate, applying
# the same validity rules the Python cleansing applies (9-digit roll, owner
# present, known status, parseable money, parseable-or-empty date), deduplicated
# by roll keeping the lowest rec_id to mirror the loader's ON CONFLICT behaviour.
# Returns the expected row count and the expected tax-levy control total. Because
# this is computed by SQL and the cloud totals come from Python-parsed values,
# agreement is a genuine two-implementation cross-check.
VALID_MIGRATABLE_SUMMARY = r"""
WITH valid AS (
    SELECT DISTINCT ON (regexp_replace(roll_no, '\D', '', 'g'))
        regexp_replace(roll_no, '\D', '', 'g') AS digits,
        CASE
            WHEN tax_levy ~ '^\(.*\)$'
                THEN -1 * replace(replace(replace(trim(both '()' from tax_levy),'$',''),',',''),' ','')::numeric
            ELSE replace(replace(replace(tax_levy,'$',''),',',''),' ','')::numeric
        END AS levy
    FROM legacy.tax_master
    WHERE length(regexp_replace(COALESCE(roll_no,''), '\D', '', 'g')) = 9
      AND COALESCE(trim(owner_name), '') <> ''
      AND upper(trim(status_cd)) IN ('A','I','P','X')
      AND assessed_val ~ '^\$?\(?-?[0-9,]+(\.[0-9]+)?\)?$'
      AND tax_levy ~ '^\$?\(?-?[0-9,]+(\.[0-9]+)?\)?$'
      AND (
            COALESCE(trim(last_pay_dt), '') = ''
            OR last_pay_dt ~ '^\d{4}-\d{2}-\d{2}$'
            OR last_pay_dt ~ '^\d{2}/\d{2}/\d{4}$'
            OR last_pay_dt ~ '^\d{2}-[A-Za-z]{3}-\d{2}$'
          )
    ORDER BY regexp_replace(roll_no, '\D', '', 'g'), rec_id
)
SELECT count(*) AS expected_count, COALESCE(SUM(levy), 0) AS expected_levy
FROM valid;
"""

# Find duplicate roll numbers in the *legacy* data before they reach the cloud,
# where roll_number is UNIQUE. CTE + ROW_NUMBER() window partitioned by the
# normalized roll exposes every collision and which row is the keeper.
DUPLICATE_ROLLS_LEGACY = r"""
WITH normalized AS (
    SELECT
        rec_id,
        regexp_replace(COALESCE(roll_no, ''), '\D', '', 'g') AS digits,
        owner_name
    FROM legacy.tax_master
),
ranked AS (
    SELECT
        rec_id,
        digits,
        owner_name,
        COUNT(*)     OVER (PARTITION BY digits) AS occurrences,
        ROW_NUMBER() OVER (PARTITION BY digits ORDER BY rec_id) AS seq
    FROM normalized
    WHERE length(digits) = 9
)
SELECT rec_id, digits AS roll_digits, owner_name, occurrences, seq
FROM ranked
WHERE occurrences > 1
ORDER BY digits, seq;
"""

# Per-account closing balance recomputed with a window function, compared to the
# legacy stored balance, to surface accounts where the stored running balance
# drifted from the truth. Legacy dates are TEXT in mixed formats, so they are
# parsed to real dates BEFORE ordering - otherwise the running total is computed
# in the wrong order and every account looks wrong.
LEGACY_BALANCE_DRIFT = r"""
WITH parsed AS (
    SELECT
        regexp_replace(COALESCE(roll_no,''), '\D', '', 'g') AS digits,
        CASE
            WHEN txn_dt ~ '^\d{4}-\d{2}-\d{2}$' THEN to_date(txn_dt, 'YYYY-MM-DD')
            WHEN txn_dt ~ '^\d{2}/\d{2}/\d{4}$' THEN to_date(txn_dt, 'MM/DD/YYYY')
            WHEN txn_dt ~ '^\d{2}-[A-Za-z]{3}-\d{2}$' THEN to_date(txn_dt, 'DD-Mon-YY')
        END AS d,
        txn_id,
        CASE
            WHEN amount ~ '^\(.*\)$'
                THEN -1 * replace(replace(trim(both '()' from amount), ',',''), '$','')::numeric
            ELSE NULLIF(regexp_replace(amount, '[^0-9.\-]', '', 'g'), '')::numeric
        END AS amt,
        NULLIF(regexp_replace(balance, '[^0-9.\-]', '', 'g'), '')::numeric AS stored_balance
    FROM legacy.util_ledger
),
running AS (
    SELECT
        digits,
        txn_id,
        stored_balance,
        SUM(amt) OVER (PARTITION BY digits ORDER BY d, txn_id
                       ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS computed_balance,
        ROW_NUMBER() OVER (PARTITION BY digits ORDER BY d DESC, txn_id DESC) AS rn
    FROM parsed
    WHERE digits <> ''
)
SELECT digits AS roll_digits, stored_balance, computed_balance
FROM running
WHERE rn = 1
  AND stored_balance IS DISTINCT FROM computed_balance
ORDER BY digits;
"""