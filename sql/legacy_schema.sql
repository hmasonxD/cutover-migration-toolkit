-- Legacy municipal system schema.
-- Deliberately flat, weakly typed, and inconsistent - the way data actually
-- arrives from an aging on-prem tax/utility system. Money is stored as text,
-- dates use several formats, roll numbers are formatted inconsistently, and a
-- handful of rows are malformed. The migration has to cope with all of it.
DROP SCHEMA IF EXISTS legacy CASCADE;
CREATE SCHEMA legacy;
CREATE TABLE legacy.tax_master (
    rec_id SERIAL PRIMARY KEY,
    roll_no TEXT,
    -- "001-2345-00", "001 2345 00", "0012345 00"
    owner_name TEXT,
    -- "SMITH, JOHN A", "  jane doe ", mixed case
    prop_addr TEXT,
    assessed_val TEXT,
    -- "$250,000.00", "250000", "(1,000.00)" = credit
    tax_levy TEXT,
    status_cd TEXT,
    -- A / I / P / X (+ lowercase, nulls, junk)
    last_pay_dt TEXT -- ISO, US, Oracle DD-MON-YY, or empty
);
CREATE TABLE legacy.util_ledger (
    txn_id SERIAL PRIMARY KEY,
    roll_no TEXT,
    txn_dt TEXT,
    txn_type TEXT,
    -- CHARGE / PAYMENT / ADJUST
    amount TEXT,
    -- signed text money
    balance TEXT -- legacy running balance (occasionally wrong)
);
CREATE INDEX ix_tax_master_roll ON legacy.tax_master (roll_no);
CREATE INDEX ix_util_ledger_roll ON legacy.util_ledger (roll_no);