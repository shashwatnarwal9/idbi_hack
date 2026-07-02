-- आय·AI Bronze — customers: raw CSV -> single typed Parquet file (small table,
-- no partitioning). Explicit casts only, no cleaning, no derived columns.
-- Ground-truth "_" columns carried through UNCHANGED (evaluation-only).
COPY (
    SELECT
        CAST(customer_id             AS VARCHAR) AS customer_id,
        CAST(name                    AS VARCHAR) AS name,
        CAST(age                     AS INTEGER) AS age,
        CAST(city                    AS VARCHAR) AS city,
        CAST(occupation_declared     AS VARCHAR) AS occupation_declared,
        CAST(declared_monthly_income AS DOUBLE)  AS declared_monthly_income,
        CAST(account_open_date       AS DATE)    AS account_open_date,
        CAST(_true_occupation        AS VARCHAR) AS _true_occupation,
        CAST(_true_monthly_income    AS DOUBLE)  AS _true_monthly_income,
        CAST(_is_good_prospect       AS BOOLEAN) AS _is_good_prospect
    FROM read_csv_auto('$raw_csv')
) TO '$out_file' (FORMAT PARQUET);
