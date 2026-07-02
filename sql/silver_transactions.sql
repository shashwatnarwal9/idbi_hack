-- आय·AI Silver — the core: crack raw narrations into structure and DERIVE a
-- category. Two sub-steps in one statement:
--   (2a) PARSE  : channel, direction, counterparty_raw/_norm, ref
--   (2b) CLASSIFY: ordered rule cascade -> 'category:confidence', then
--                  is_income derived from the category.
--
-- GROUND-TRUTH FIREWALL: bronze_input whitelists columns explicitly, so no
-- parse/classify expression can ever reference a "_" column. Ground truth is
-- re-attached ONLY in the eval-passthrough join at the very bottom.
--
-- Athena notes: regexp_matches -> regexp_like; read_parquet -> external table
-- over the S3 prefix; everything else (regexp_extract with group index,
-- regexp_replace, split_part, lpad, CASE) is Athena (Trino) compatible.
-- The rule CASE encodes 'category:confidence' in one VARCHAR so category and
-- parse_confidence stay single-sourced without DuckDB-only struct literals.

COPY (
WITH bronze_input AS (
    -- explicit whitelist: the firewall. NO "_" columns pass this line.
    SELECT txn_id, customer_id, "timestamp", txn_type, amount, balance,
           narration, year, month
    FROM $bronze_read
),

normalized AS (
    SELECT *,
        -- narr_c: original case, trimmed, runs of spaces collapsed (parse source)
        regexp_replace(trim(narration), ' +', ' ')        AS narr_c,
        -- narr_u: uppercased narr_c (rule-matching source)
        upper(regexp_replace(trim(narration), ' +', ' ')) AS narr_u
    FROM bronze_input
),

parsed AS (
    SELECT *,
        CASE WHEN upper(txn_type) = 'CREDIT' THEN 'credit' ELSE 'debit' END AS direction,
        CASE
            WHEN narr_u LIKE 'UPI/%'                                THEN 'UPI'
            WHEN narr_u LIKE '%NACH/%' OR narr_u LIKE '%ACH-D-%'    THEN 'ACH'
            WHEN narr_u LIKE '%NEFT%'                               THEN 'NEFT'
            WHEN narr_u LIKE '%IMPS%'                               THEN 'IMPS'
            WHEN narr_u LIKE '%BBPS%' OR narr_u LIKE '%BILL PAY%'   THEN 'BIL'
            WHEN narr_u LIKE '%ATM%'                                THEN 'ATW'
            ELSE 'OTHER'  -- POS, RTGS, free-text (pension/interest/FD) narrations
        END AS channel,
        -- counterparty: first matching per-channel pattern wins ((?i) = case-
        -- insensitive, narrations arrive in random case)
        COALESCE(
            NULLIF(regexp_extract(narr_c, '(?i)UPI/(?:P2M/|P2A/|REV/)?[0-9]{6,}/([^/]+)', 1), ''),
            NULLIF(regexp_extract(narr_c, '(?i)IMPS[-/](?:P2A[-/])?[0-9]{6,}[-/]([^-/]+)', 1), ''),
            NULLIF(regexp_extract(narr_c, '(?i)NEFT-[A-Z]{4}[0-9]{3,}-([^-]+)', 1), ''),
            NULLIF(regexp_extract(narr_c, '(?i)(?:NEFT|RTGS)-([A-Z][A-Z .&]{2,})-', 1), ''),
            NULLIF(regexp_extract(narr_c, '(?i)ACH-D-([^-]+)', 1), ''),
            NULLIF(regexp_extract(narr_c, '(?i)NACH/([^/]+)', 1), ''),
            NULLIF(regexp_extract(narr_c, '(?i)BBPS/([^/]+)', 1), ''),
            NULLIF(regexp_extract(narr_c, '(?i)POS [0-9X]+ (.+)', 1), ''),
            NULLIF(regexp_extract(narr_c, '(?i)ATM-CASH-NFS/([^/]+)', 1), ''),
            NULLIF(regexp_extract(narr_c, '(?i)^([A-Z][A-Z .&]{2,}) (?:MONTHLY )?(?:SALARY|SALRY|SAL)\b', 1), '')
        ) AS counterparty_raw,
        -- ref: prefer an explicit N-prefixed reference, else first long digit run
        COALESCE(
            NULLIF(regexp_extract(narr_u, '\bN[0-9]{8,}\b'), ''),
            NULLIF(regexp_extract(narr_u, '[0-9]{6,}'), '')
        ) AS ref
    FROM normalized
),

enriched AS (
    SELECT *,
        regexp_replace(upper(trim(counterparty_raw)), ' +', ' ') AS counterparty_norm
    FROM parsed
),

-- (2b) rule cascade. FIRST match wins, so order = specificity. Encoded as
-- 'category:confidence'; 1.0 = strong rule, mid = keyword/dictionary rule,
-- 0.5 = direction-only fallback. Small merchant dictionaries play the role a
-- curated MCC/merchant table plays in production narration parsers.
classified AS (
    SELECT *,
        CASE
            -- ============ CREDITS ============
            WHEN direction = 'credit' AND regexp_matches(narr_u, 'INT\.PD|SB INTEREST|INTEREST CAPITALISED')
                THEN 'interest:1.0'
            -- salary incl. pension: payroll-style regular income credits
            WHEN direction = 'credit' AND regexp_matches(narr_u, '\b(SALARY|SALRY|SAL)\b|PENSION|CPAO')
                THEN 'salary:1.0'
            -- gig platform + settlement wording = platform payout
            WHEN direction = 'credit'
                 AND regexp_matches(narr_u, 'SWIGGY|ZOMATO|\bUBER\b|\bOLA\b|RAPIDO|URBANCOMPANY|BLINKIT|ZEPTO')
                 AND regexp_matches(narr_u, 'PAYOUT|SETTLEMENT|PARTNER')
                THEN 'gig_income:1.0'
            WHEN direction = 'credit' AND regexp_matches(narr_u, 'PAYOUT|WEEKLY SETTLEMENT')
                THEN 'gig_income:0.8'    -- payout wording, platform not in dictionary
            -- non-income credits: self transfers, reversals, deposit maturities
            WHEN direction = 'credit' AND regexp_matches(narr_u, '\bSELF\b|FROM OWN A/?C')
                THEN 'p2p_in:0.9'
            WHEN direction = 'credit' AND regexp_matches(narr_u, 'REFUND|/REV/|FD MATURITY')
                THEN 'p2p_in:0.9'
            WHEN direction = 'credit' AND regexp_matches(narr_u, '\bRENT\b')
                THEN 'rent:1.0'
            -- invoice/professional wording = business or freelance receipts
            WHEN direction = 'credit' AND regexp_matches(narr_u, 'FREELANCE|PROJECT PAYMENT|\bINV\b|INVOICE|BILL PAYMENT')
                THEN 'business_income:0.9'
            -- UPI P2M credit: a merchant-side collection into this account
            WHEN direction = 'credit' AND narr_u LIKE 'UPI/P2M/%'
                THEN 'business_income:0.85'
            WHEN direction = 'credit'
                THEN 'p2p_in:0.5'        -- fallback: unexplained credit is NOT income
            -- ============ DEBITS ============ (everything below is a debit)
            WHEN regexp_matches(narr_u, 'ATM')
                THEN 'atm:1.0'
            WHEN regexp_matches(narr_u, '\bRENT\b')
                THEN 'rent:1.0'
            -- insurance premia folded into utility (recurring bills bucket)
            WHEN regexp_matches(narr_u, 'PREMIUM|LIC OF INDIA|HDFC ERGO|STAR HEALTH|ICICI PRULIFE')
                THEN 'utility:0.9'
            WHEN regexp_matches(narr_u, '\bEMI|\bLOAN\b')
                THEN 'emi:1.0'
            WHEN regexp_matches(narr_u, '\bSIP\b|MUTUAL FUND|\bAMC\b|AXIS MF')
                THEN 'sip:1.0'
            WHEN regexp_matches(narr_u, 'BBPS|BILL PAY|ELECTRICITY|RECHARGE|MSEB|TATA POWER|BESCOM|ADANI|AIRTEL|VI POSTPAID')
                THEN 'utility:1.0'
            WHEN regexp_matches(narr_u, 'DMART|BIGBASKET|RELIANCE FRESH|MORE SUPERMARKET|KIRANA|JIOMART')
                THEN 'groceries:1.0'
            WHEN regexp_matches(narr_u, 'SWIGGY|ZOMATO|DOMINOS|MCDONALDS|HALDIRAMS|CAFE COFFEE|BARBEQUE')
                THEN 'food:1.0'
            WHEN regexp_matches(narr_u, 'INDIAN OIL|BHARAT PETROLEUM|\bSHELL\b|PETROL|FUEL')
                THEN 'fuel:1.0'
            WHEN regexp_matches(narr_u, 'NETFLIX|HOTSTAR|SPOTIFY|BOOKMYSHOW|\bPVR\b|SUBSCRIPTION')
                THEN 'entertainment:1.0'
            WHEN regexp_matches(narr_u, 'AMAZON|FLIPKART|MYNTRA|AJIO|CROMA|LIFESTYLE')
                THEN 'shopping:1.0'
            -- medical/pharmacy folded into shopping (taxonomy has no medical)
            WHEN regexp_matches(narr_u, 'APOLLO|MEDPLUS|FORTIS|1MG|PHARMACY|HOSPITAL')
                THEN 'shopping:0.7'
            WHEN regexp_matches(narr_u, '/SENT\b')
                THEN 'p2p_out:0.9'
            -- bank-transfer debit with trade wording: supplier/business outflow
            WHEN regexp_matches(narr_u, '^(NEFT|RTGS)')
                 AND regexp_matches(narr_u, 'PAYMENT|INVOICE|TRADERS|ENTERPRISES|DISTRIBUTORS|AGENCIES|WHOLESALE|SUPPLIES')
                THEN 'p2p_out:0.6'
            ELSE 'p2p_out:0.5'           -- fallback: unexplained debit
        END AS rule
    FROM enriched
)

SELECT
    c.txn_id,
    c.customer_id,
    c."timestamp",
    c.direction,
    c.amount,
    c.balance,
    c.narration,
    c.channel,
    c.counterparty_raw,
    c.counterparty_norm,
    c.ref,
    split_part(c.rule, ':', 1)                    AS category,
    CAST(split_part(c.rule, ':', 2) AS DOUBLE)    AS parse_confidence,
    split_part(c.rule, ':', 1)
        IN ('salary', 'gig_income', 'business_income', 'interest') AS is_income,
    c.year,
    c.month,
    -- EVAL-PASSTHROUGH: ground truth re-attached for the evaluation step only.
    -- Nothing above this line reads these columns (bronze_input whitelists).
    g._true_category,
    g._is_income
FROM classified c
JOIN (
    SELECT txn_id, _true_category, _is_income
    FROM $bronze_read
) g USING (txn_id)
) TO '$out_dir' (FORMAT PARQUET, PARTITION_BY (year, month));
