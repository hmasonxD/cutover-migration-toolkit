-- Catalis cloud (target) schema: normalized, typed, constrained.
-- Also defines the `recon` schema: stored procedures and window-function
-- helpers used to validate the data after it lands.
DROP SCHEMA IF EXISTS app CASCADE;
DROP SCHEMA IF EXISTS recon CASCADE;
CREATE SCHEMA app;
CREATE SCHEMA recon;
CREATE TABLE app.property (
    id SERIAL PRIMARY KEY,
    roll_number TEXT NOT NULL UNIQUE,
    owner_name TEXT NOT NULL,
    address TEXT,
    assessed_value NUMERIC(14, 2) NOT NULL,
    tax_levy NUMERIC(14, 2) NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('ACTIVE', 'INACTIVE', 'PENDING', 'EXEMPT')
    ),
    last_payment_date DATE
);
CREATE TABLE app.utility_transaction (
    id SERIAL PRIMARY KEY,
    roll_number TEXT NOT NULL,
    txn_date DATE NOT NULL,
    txn_type TEXT NOT NULL CHECK (txn_type IN ('CHARGE', 'PAYMENT', 'ADJUST')),
    amount NUMERIC(14, 2) NOT NULL
);
CREATE INDEX ix_util_txn_roll ON app.utility_transaction (roll_number);
CREATE TABLE app.migration_exception (
    id SERIAL PRIMARY KEY,
    source_id INTEGER,
    roll_no_raw TEXT,
    entity TEXT NOT NULL CHECK (entity IN ('PROPERTY', 'TRANSACTION')),
    reason TEXT NOT NULL,
    logged_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- ---------------------------------------------------------------------------
-- recon.account_running_balances()
-- Window function: recompute each account's running ledger balance from first
-- principles, ordered chronologically. This is the source of truth we validate
-- the legacy stored balances against.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION recon.account_running_balances() RETURNS TABLE (
        roll_number TEXT,
        txn_date DATE,
        amount NUMERIC,
        running_balance NUMERIC
    ) LANGUAGE sql STABLE AS $$
SELECT roll_number,
    txn_date,
    amount,
    SUM(amount) OVER (
        PARTITION BY roll_number
        ORDER BY txn_date,
            id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_balance
FROM app.utility_transaction;
$$;
-- ---------------------------------------------------------------------------
-- recon.account_final_balances()
-- The closing balance per account (latest running_balance), via a CTE that
-- ranks transactions newest-first with a window function.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION recon.account_final_balances() RETURNS TABLE (roll_number TEXT, final_balance NUMERIC) LANGUAGE sql STABLE AS $$ WITH ranked AS (
        SELECT roll_number,
            running_balance,
            ROW_NUMBER() OVER (
                PARTITION BY roll_number
                ORDER BY txn_date DESC,
                    amount DESC
            ) AS rn
        FROM recon.account_running_balances()
    )
SELECT roll_number,
    running_balance AS final_balance
FROM ranked
WHERE rn = 1;
$$;
-- ---------------------------------------------------------------------------
-- recon.table_rowcount(schema, table)
-- Stored procedure using DYNAMIC SQL. Lets the reconciliation harness count
-- any table by name without hardcoding - used by the row-count parity check.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION recon.table_rowcount(p_schema TEXT, p_table TEXT) RETURNS BIGINT LANGUAGE plpgsql STABLE AS $$
DECLARE n BIGINT;
BEGIN EXECUTE format('SELECT count(*) FROM %I.%I', p_schema, p_table) INTO n;
RETURN n;
END;
$$;