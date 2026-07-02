-- आय·AI Gold — the income engine. One row per customer: reconstructed true
-- monthly income, essentials, EMI/SIP load, investable surplus, stability and
-- risk capacity. Everything derives from silver's DERIVED fields only.
--
-- GROUND-TRUTH FIREWALL: silver_input / customers_input whitelist columns, so
-- no feature expression can reference a "_" column. Ground truth is attached
-- ONLY in the EVAL-PASSTHROUGH block of the final SELECT.
--
-- Athena notes: quantile_cont -> approx_percentile, regexp_matches ->
-- regexp_like, stddev_samp/corr/greatest/least/row_number are all standard.

COPY (
WITH silver_input AS (
    -- whitelist: derived fields only, never "_" ground truth
    SELECT customer_id, direction, amount, narration, channel, category,
           is_income, parse_confidence, counterparty_norm, year, month
    FROM $silver_read
),
customers_input AS (
    SELECT customer_id, city, occupation_declared, declared_monthly_income
    FROM read_parquet('$customers_file')
),

-- month spine: every month the customer was observed transacting
months AS (SELECT DISTINCT customer_id, year, month FROM silver_input),
hist   AS (SELECT customer_id, count(*) AS months_history FROM months GROUP BY 1),

-- ------------------------------------------------ monthly rollups
flows AS (
    SELECT customer_id, year, month,
        sum(CASE WHEN is_income AND direction = 'credit' THEN amount ELSE 0 END) AS income_gross,
        sum(CASE WHEN category = 'salary' AND direction = 'credit' THEN amount ELSE 0 END) AS salary_inflow,
        sum(CASE WHEN category = 'gig_income' THEN amount ELSE 0 END)      AS gig_inflow,
        sum(CASE WHEN category = 'business_income' THEN amount ELSE 0 END) AS business_inflow,
        sum(CASE WHEN direction = 'debit' AND category IN ('rent', 'utility', 'groceries')
                 THEN amount ELSE 0 END) AS essentials_m,
        sum(CASE WHEN direction = 'debit' AND category = 'emi' THEN amount ELSE 0 END) AS emi_m,
        sum(CASE WHEN direction = 'debit' AND category = 'sip' THEN amount ELSE 0 END) AS sip_m,
        sum(CASE WHEN direction = 'debit' THEN amount ELSE 0 END) AS debit_m,
        -- business netting: trade-worded bank-transfer debits are working-capital
        -- outflows (supplier payments), not personal spend. Netting them against
        -- gross receipts is what turns merchant turnover into income.
        sum(CASE WHEN direction = 'debit' AND category = 'p2p_out'
                  AND channel IN ('NEFT', 'OTHER')   -- bank rails; RTGS folds to OTHER
                  AND regexp_matches(upper(narration),
                      'TRADERS|ENTERPRISES|DISTRIBUTORS|AGENCIES|WHOLESALE|SUPPLIES|INVOICE')
                 THEN amount ELSE 0 END) AS biz_expense_m
    FROM silver_input
    GROUP BY 1, 2, 3
),

monthly AS (
    -- left join onto the spine so quiet months count as zero income
    SELECT m.customer_id, m.year, m.month,
        COALESCE(f.income_gross, 0) - COALESCE(f.biz_expense_m, 0) AS income_net,
        COALESCE(f.income_gross, 0) - COALESCE(f.salary_inflow, 0)
            - COALESCE(f.biz_expense_m, 0)                         AS other_income_m,
        COALESCE(f.gig_inflow, 0)      AS gig_inflow,
        COALESCE(f.business_inflow, 0) AS business_inflow,
        COALESCE(f.essentials_m, 0)    AS essentials_m,
        COALESCE(f.emi_m, 0)           AS emi_m,
        COALESCE(f.sip_m, 0)           AS sip_m,
        COALESCE(f.debit_m, 0) - COALESCE(f.sip_m, 0)
            - COALESCE(f.biz_expense_m, 0)                         AS personal_spend_m
    FROM months m
    LEFT JOIN flows f USING (customer_id, year, month)
),
monthly_s AS (
    SELECT *, income_net - essentials_m - emi_m AS surplus_m FROM monthly
),

-- ------------------------------------------------ salary recurrence detection
salary_streams AS (
    -- one stream = one paying counterparty ('?' groups narration styles where
    -- no counterparty could be parsed, e.g. treasury pension credits)
    SELECT customer_id, COALESCE(counterparty_norm, '?') AS stream_key,
           year, month, sum(amount) AS stream_amt
    FROM silver_input
    WHERE category = 'salary' AND direction = 'credit'
    GROUP BY 1, 2, 3, 4
),
stream_stats AS (
    SELECT customer_id, stream_key,
        count(*) AS months_present,
        quantile_cont(stream_amt, 0.5) AS stream_median,  -- Athena: approx_percentile
        COALESCE(stddev_samp(stream_amt) / NULLIF(avg(stream_amt), 0), 0) AS stream_cv
    FROM salary_streams
    GROUP BY 1, 2
),
recurring AS (
    -- "the salary": paid in >=60% of observed months, amount stable (cv<=0.25);
    -- largest qualifying stream wins
    SELECT s.customer_id, s.stream_median,
           row_number() OVER (PARTITION BY s.customer_id
                              ORDER BY s.stream_median DESC) AS rn
    FROM stream_stats s
    JOIN hist h USING (customer_id)
    WHERE s.months_present >= 0.6 * h.months_history
      AND s.stream_cv <= 0.25
),
salary_pick AS (SELECT customer_id, stream_median FROM recurring WHERE rn = 1),

-- ------------------------------------------------ per-customer aggregates
rollup AS (
    SELECT customer_id,
        quantile_cont(income_net, 0.25)     AS income_p25,       -- reliable floor
        quantile_cont(other_income_m, 0.25) AS other_income_p25, -- floor of side income
        COALESCE(stddev_samp(income_net) / NULLIF(avg(income_net), 0), 0) AS income_cv,
        avg(essentials_m)     AS essentials_avg,
        avg(emi_m)            AS emi_avg,
        avg(sip_m)            AS sip_avg,
        avg(personal_spend_m) AS spend_avg,
        avg(surplus_m)        AS surplus_mean,
        COALESCE(stddev_samp(surplus_m) / NULLIF(avg(surplus_m), 0), 0) AS surplus_cv,
        sum(gig_inflow)       AS gig_total,
        sum(business_inflow)  AS business_total
    FROM monthly_s
    GROUP BY 1
),
pct AS (
    SELECT customer_id,
           avg(CASE WHEN parse_confidence >= 0.8 THEN 1.0 ELSE 0.0 END) AS pct_categorized
    FROM silver_input
    GROUP BY 1
),

-- ------------------------------------------------ profile assembly
profile AS (
    SELECT r.customer_id,
        CASE WHEN sp.customer_id IS NOT NULL         THEN 'salaried'
             WHEN r.gig_total >= r.business_total    THEN 'gig'
             ELSE 'business' END AS income_type,
        -- salaried: recurring salary + a floor on side income.
        -- gig/business: p25 of monthly net inflow — a floor, not a naive mean.
        CASE WHEN sp.customer_id IS NOT NULL
             THEN sp.stream_median + GREATEST(r.other_income_p25, 0)
             ELSE GREATEST(r.income_p25, 0) END AS true_monthly_income,
        r.income_cv AS income_volatility,
        r.essentials_avg, r.emi_avg, r.sip_avg, r.spend_avg,
        CASE WHEN r.surplus_mean <= 0 THEN 0.0
             ELSE GREATEST(0.0, LEAST(1.0, 1.0 - r.surplus_cv)) END AS surplus_stability
    FROM rollup r
    LEFT JOIN salary_pick sp USING (customer_id)
),
profile_rates AS (
    SELECT *,
        GREATEST(0.0, LEAST(1.0, (true_monthly_income - spend_avg)
                                 / NULLIF(true_monthly_income, 0))) AS savings_rate,
        -- headline: what is safely investable each month. Buffer = 15% of income
        -- held back for irregular/lumpy expenses (tunable).
        true_monthly_income - essentials_avg - emi_avg
            - 0.15 * true_monthly_income AS investable_surplus
    FROM profile
),
profile_risk AS (
    SELECT *,
        -- capacity from cashflow behaviour only (no quiz, no ground truth):
        -- steady income + steady surplus + real savings habit -> high
        CASE WHEN income_volatility <= 0.25 AND surplus_stability >= 0.60
                  AND savings_rate >= 0.30                          THEN 'high'
             WHEN income_volatility > 0.60 OR savings_rate < 0.10
                  OR surplus_stability < 0.30                       THEN 'low'
             ELSE 'medium' END AS risk_capacity
    FROM profile_rates
)

SELECT
    p.customer_id,
    ci.city AS region,                        -- carried for later fairness audit
    p.income_type,
    round(p.true_monthly_income, 2)  AS true_monthly_income,
    round(p.income_volatility, 4)    AS income_volatility,
    round(p.essentials_avg, 2)       AS avg_monthly_essentials,
    round(p.emi_avg, 2)              AS total_emi,
    round(p.sip_avg, 2)              AS total_sip,
    round(p.investable_surplus, 2)   AS investable_surplus,
    round(p.surplus_stability, 4)    AS surplus_stability,
    round(p.savings_rate, 4)         AS savings_rate,
    p.risk_capacity,
    h.months_history,
    round(pc.pct_categorized, 4)     AS pct_categorized,
    ci.occupation_declared,
    ci.declared_monthly_income,
    -- EVAL-PASSTHROUGH: ground truth attached for evaluation only; nothing
    -- above this line reads these columns.
    g._true_occupation,
    g._true_monthly_income,
    g._is_good_prospect
FROM profile_risk p
JOIN hist h  USING (customer_id)
JOIN pct  pc USING (customer_id)
JOIN customers_input ci USING (customer_id)
JOIN (
    SELECT customer_id, _true_occupation, _true_monthly_income, _is_good_prospect
    FROM read_parquet('$customers_file')
) g USING (customer_id)
) TO '$out_file' (FORMAT PARQUET);
