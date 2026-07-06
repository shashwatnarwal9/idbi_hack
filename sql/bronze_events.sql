-- आय·AI Bronze — events: raw CSV -> typed, partitioned Parquet, same pattern as
-- transactions. Immutable and raw: explicit casts only, no cleaning, and no new
-- columns except the year/month partition keys derived from "timestamp".
-- The ground-truth "_intent_propensity" column is carried through UNCHANGED
-- (evaluation-only; carrying it is allowed, reading it as an input is not).
COPY (
    SELECT
        CAST(event_id        AS VARCHAR)   AS event_id,
        CAST(customer_id     AS VARCHAR)   AS customer_id,
        CAST("timestamp"     AS TIMESTAMP) AS "timestamp",
        CAST(event_type      AS VARCHAR)   AS event_type,
        CAST(channel         AS VARCHAR)   AS channel,
        CAST(product         AS VARCHAR)   AS product,
        CAST(session_id      AS VARCHAR)   AS session_id,
        TRY_CAST(duration_sec AS INTEGER)  AS duration_sec,
        TRY_CAST(_intent_propensity AS DOUBLE) AS _intent_propensity,
        CAST(year("timestamp") AS VARCHAR)                AS year,
        lpad(CAST(month("timestamp") AS VARCHAR), 2, '0') AS month
    FROM read_csv_auto('$raw_csv')
) TO '$out_dir' (FORMAT PARQUET, PARTITION_BY (year, month));
