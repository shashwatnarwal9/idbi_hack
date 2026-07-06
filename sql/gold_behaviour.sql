-- आय·AI Gold — behavioural signals: one row per customer from silver
-- transactions ONLY. Ground-truth firewall: this reads no "_" column; only the
-- derived category / is_income / counterparty_norm and the amount/timestamp.
-- All continuous signals are normalised 0-1 across the book with percent_rank
-- (RFM-style decile ranking); booleans and natural ratios stay 0-1 as-is.

CREATE OR REPLACE TEMP TABLE _txn AS
SELECT customer_id,
       category,
       direction,
       amount,
       is_income,
       counterparty_norm,
       (year || '-' || month) AS ym
FROM $silver_read;

-- per-customer month span
CREATE OR REPLACE TEMP TABLE _hist AS
SELECT customer_id, count(DISTINCT ym) AS months_history
FROM _txn
GROUP BY 1;

-- monthly net-flow and income series, most-recent-first
CREATE OR REPLACE TEMP TABLE _monthly AS
SELECT customer_id, ym,
       sum(CASE WHEN direction = 'credit' THEN amount ELSE -amount END) AS net,
       sum(CASE WHEN is_income THEN amount ELSE 0 END) AS income_net,
       row_number() OVER (PARTITION BY customer_id ORDER BY ym DESC) AS rn
FROM _txn
GROUP BY 1, 2;

-- the customer's 2nd-most-recent month (defines "the most recent 2 months")
CREATE OR REPLACE TEMP TABLE _second_recent AS
SELECT customer_id, ym AS second_recent_ym FROM _monthly WHERE rn = 2;

-- last-3 vs prior-3 month aggregates for the trend signals
CREATE OR REPLACE TEMP TABLE _trend AS
SELECT customer_id,
       avg(CASE WHEN rn <= 3 THEN net END) AS net_last3,
       avg(CASE WHEN rn > 3 AND rn <= 6 THEN net END) AS net_prior3,
       avg(CASE WHEN rn <= 3 THEN income_net END) AS inc_last3,
       avg(CASE WHEN rn > 3 AND rn <= 6 THEN income_net END) AS inc_prior3
FROM _monthly
GROUP BY 1;

-- per-counterparty EMI streams: presence and amount stability
CREATE OR REPLACE TEMP TABLE _emi AS
SELECT customer_id, counterparty_norm,
       count(DISTINCT ym) AS present_months,
       avg(amount) AS mean_amt,
       coalesce(stddev_pop(amount), 0) AS sd_amt,
       max(ym) AS last_ym
FROM _txn
WHERE category = 'emi' AND counterparty_norm IS NOT NULL
GROUP BY 1, 2;

-- the dominant EMI stream per customer (most months present)
CREATE OR REPLACE TEMP TABLE _emi_main AS
SELECT e.customer_id, e.counterparty_norm, e.present_months, e.last_ym,
       -- amount stability: 1 - coefficient of variation, clamped to [0, 1]
       greatest(0.0, least(1.0, 1.0 - (e.sd_amt / nullif(e.mean_amt, 0)))) AS stability
FROM _emi e
QUALIFY row_number() OVER (
    PARTITION BY e.customer_id ORDER BY e.present_months DESC, e.counterparty_norm
) = 1;

-- recurring rent and SIP presence
CREATE OR REPLACE TEMP TABLE _rent AS
SELECT customer_id, count(DISTINCT ym) AS rent_months, avg(amount) AS rent_avg
FROM _txn WHERE category = 'rent' GROUP BY 1;

CREATE OR REPLACE TEMP TABLE _sip AS
SELECT customer_id, count(DISTINCT ym) AS sip_months
FROM _txn WHERE category = 'sip' GROUP BY 1;

-- raw per-customer signals (pre-normalisation)
CREATE OR REPLACE TEMP TABLE _raw AS
SELECT h.customer_id,
       h.months_history,
       coalesce((em.present_months * 1.0 / nullif(h.months_history, 0)) * em.stability, 0.0)
           AS emi_regularity_raw,
       -- EMI ending: a regular stream (>=3 months, >=50% coverage) whose last
       -- activity predates the customer's most-recent-2-month window
       CASE
           WHEN em.present_months >= 3
                AND em.present_months * 1.0 / nullif(h.months_history, 0) >= 0.5
                AND sr.second_recent_ym IS NOT NULL
                AND em.last_ym < sr.second_recent_ym
           THEN 1 ELSE 0 END AS emi_ending,
       em.counterparty_norm AS ending_stream_all,
       CASE WHEN coalesce(r.rent_months, 0) >= 3 THEN 1 ELSE 0 END AS is_renter,
       coalesce(r.rent_months, 0) AS rent_months,
       r.rent_avg,
       least(1.0, coalesce(s.sip_months, 0) * 1.0 / nullif(h.months_history, 0)) AS sip_discipline,
       coalesce(t.net_last3, 0) - coalesce(t.net_prior3, 0) AS surplus_trend_raw,
       (coalesce(t.inc_last3, 0) - coalesce(t.inc_prior3, 0))
           / nullif(abs(t.inc_prior3), 0) AS income_growth_raw
FROM _hist h
LEFT JOIN _emi_main em USING (customer_id)
LEFT JOIN _second_recent sr USING (customer_id)
LEFT JOIN _rent r USING (customer_id)
LEFT JOIN _sip s USING (customer_id)
LEFT JOIN _trend t USING (customer_id);

-- normalise the continuous signals across the whole book and write gold
COPY (
    SELECT customer_id,
           months_history,
           round(percent_rank() OVER (ORDER BY emi_regularity_raw), 4) AS emi_regularity,
           emi_ending,
           CASE WHEN emi_ending = 1 THEN ending_stream_all END AS ending_stream,
           is_renter,
           rent_months,
           round(coalesce(rent_avg, 0), 2) AS rent_avg,
           round(sip_discipline, 4) AS sip_discipline,
           round(percent_rank() OVER (ORDER BY coalesce(surplus_trend_raw, 0)), 4) AS surplus_trend,
           round(percent_rank() OVER (ORDER BY coalesce(income_growth_raw, 0)), 4) AS income_growth
    FROM _raw
) TO '$out_file' (FORMAT PARQUET);
