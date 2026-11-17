# Source-to-Target Mapping Specification

Legacy system: `legacy_muni` (flat, text-typed tax and utility tables)
Target system: `catalis_cloud` (typed, constrained, loaded through the API)

Rows that fail a rule are never dropped silently: they go to
`app.migration_exception` with the source id and the reason.

## legacy.tax_master → app.property

| Legacy field   | Target field                   | Rule                                                                          | Failure → exception            |
| -------------- | ------------------------------ | ----------------------------------------------------------------------------- | ------------------------------ |
| `rec_id`       | _(not migrated)_               | Kept as `source_id` in the exception log for lineage                          | –                              |
| `roll_no`      | `roll_number`                  | Strip all non-digits, require exactly 9, format `###-####-##`                 | "roll number must be 9 digits" |
| `owner_name`   | `owner_name`                   | Collapse spaces; `LAST, FIRST` → `First Last`; title case                     | "missing owner name"           |
| `prop_addr`    | `address`                      | Trim; empty → NULL                                                            | –                              |
| `assessed_val` | `assessed_value` NUMERIC(14,2) | Remove `$`, commas, spaces; `(x)` = negative; round to cents                  | "unparseable money value"      |
| `tax_levy`     | `tax_levy` NUMERIC(14,2)       | Same money rule                                                               | "unparseable money value"      |
| `status_cd`    | `status`                       | Case-insensitive: A→ACTIVE, I→INACTIVE, P→PENDING, X→EXEMPT                   | "unknown status code"          |
| `last_pay_dt`  | `last_payment_date`            | Accept `YYYY-MM-DD`, `MM/DD/YYYY`, `DD-MON-YY`; empty → NULL (no payment yet) | "unrecognized date format"     |

**Duplicates:** the same 9 digits in two rows → the lowest `rec_id` wins;
the other is reported in the duplicate-roll section of the reconciliation report.

## legacy.util_ledger → app.utility_transaction

| Legacy field | Target field           | Rule                                                                                          | Failure → exception            |
| ------------ | ---------------------- | --------------------------------------------------------------------------------------------- | ------------------------------ |
| `txn_id`     | _(not migrated)_       | Lineage only                                                                                  | –                              |
| `roll_no`    | `roll_number`          | Same roll rule as above                                                                       | "roll number must be 9 digits" |
| `txn_dt`     | `txn_date`             | Same date formats; **required**                                                               | "missing transaction date"     |
| `txn_type`   | `txn_type`             | Upper-case; must be CHARGE, PAYMENT or ADJUST                                                 | "unknown txn_type"             |
| `amount`     | `amount` NUMERIC(14,2) | Same money rule                                                                               | "unparseable money value"      |
| `balance`    | _(not migrated)_       | Derived data: the target recomputes balances from transactions. Used only for the drift check | –                              |

## Reconciliation controls

| Check                  | Pass condition                                                    |
| ---------------------- | ----------------------------------------------------------------- |
| Record-count parity    | Valid legacy rows (re-derived in SQL) = cloud rows                |
| Tax-levy control total | SQL-derived levy total = cloud levy total, variance 0.00          |
| Key-field verification | Sampled roll numbers exist in the cloud                           |
| Duplicate rolls        | Every collision reported with its keeper                          |
| Ledger balance drift   | Stored legacy balance vs recomputed balance; differences reported |

## Open questions for the client

| #   | Question                                                          | Current assumption                             |
| --- | ----------------------------------------------------------------- | ---------------------------------------------- |
| 1   | Is `03/04/2024` March 4 or April 3?                               | US order (MM/DD/YYYY)                          |
| 2   | In `DD-MON-YY`, does `24` mean 2024? Could any dates be pre-1969? | Python's default: 00–68 → 2000s, 69–99 → 1900s |
| 3   | Do parentheses always mean a credit?                              | Yes                                            |
| 4   | When a roll appears twice, which record is correct?               | The first entered (lowest `rec_id`)            |
| 5   | Does status X always mean tax-exempt?                             | Yes                                            |
