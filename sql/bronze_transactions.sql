-- आय·AI Bronze — transactions: raw CSV -> typed, partitioned Parquet.
-- Bronze is immutable and raw: explicit casts only, NO cleaning, and NO new
-- columns except the year/month partition keys derived from "timestamp".
-- Ground-truth "_" columns are carried through UNCHANGED (evaluation-only;
-- carrying them is allowed, reading them as a transform input is not).
-- Athena note: year(), month() and lpad() all exist in Athena (Trino) too;
-- read_csv_auto is DuckDB-only — on AWS the CSV would land via a Glue crawler
-- or an Athena external table instead.
COPY (
    SELECT
        CAST(txn_id         AS VARCHAR)   AS txn_id,
        CAST(customer_id    AS VARCHAR)   AS customer_id,
        CAST("timestamp"    AS TIMESTAMP) AS "timestamp",
        CAST(txn_type       AS VARCHAR)   AS txn_type,
        CAST(amount         AS DOUBLE)    AS amount,
        CAST(balance        AS DOUBLE)    AS balance,
        CAST(narration      AS VARCHAR)   AS narration,
        CAST(_true_category AS VARCHAR)   AS _true_category,
        CAST(_is_income     AS BOOLEAN)   AS _is_income,
        -- partition keys, zero-padded so folders sort as year=YYYY/month=MM
        CAST(year("timestamp") AS VARCHAR)                AS year,
        lpad(CAST(month("timestamp") AS VARCHAR), 2, '0') AS month
    FROM read_csv_auto('$raw_csv')
) TO '$out_dir' (FORMAT PARQUET, PARTITION_BY (year, month));
