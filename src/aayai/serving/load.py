"""Serving loader: gold profiles, silver aggregates and model scores to Postgres.

Tables rebuilt on every load (all point-lookup friendly, keyed by customer_id):
  customer_profiles   one row per customer (gold minus "_" ground truth, plus
                      display name and account_open_date joined from bronze)
  spending_breakdown  avg monthly debit spend per silver category
  income_streams      avg monthly income inflow per category with months seen
  key_transactions    each customer's largest transactions, for the profile view
  income_by_month     book-wide avg income inflow per month (overview chart)
  prospect_scores     model probability + top SHAP reason codes, precomputed
                      here so the dashboard needs no xgboost/shap at runtime

review_status (analyst state) is intentionally NOT dropped here, see
aayai.serving.reviews. Ground truth never reaches serving: "_" columns stay in
the lake.
"""

from __future__ import annotations

import duckdb
import numpy as np
import shap
import xgboost as xgb
from psycopg2.extras import Json, execute_values

from aayai.bronze.ingest import CUSTOMERS_FILE
from aayai.gold.build import PROFILES_READ
from aayai.model.train import FEATURES, MODEL_FILE, load_features
from aayai.serving.db import connect
from aayai.serving.reviews import ensure_table as ensure_review_table
from aayai.silver.transform import TXN_READ

PROFILE_COLS = [
    "customer_id",
    "region",
    "income_type",
    "true_monthly_income",
    "income_volatility",
    "avg_monthly_essentials",
    "total_emi",
    "total_sip",
    "investable_surplus",
    "surplus_stability",
    "savings_rate",
    "risk_capacity",
    "months_history",
    "pct_categorized",
    "occupation_declared",
    "declared_monthly_income",
    "confidence_band",
]

DDL = """
DROP TABLE IF EXISTS customer_profiles;
CREATE TABLE customer_profiles (
    customer_id             TEXT PRIMARY KEY,
    name                    TEXT,
    account_open_date       DATE,
    region                  TEXT,
    income_type             TEXT,
    true_monthly_income     DOUBLE PRECISION,
    income_volatility       DOUBLE PRECISION,
    avg_monthly_essentials  DOUBLE PRECISION,
    total_emi               DOUBLE PRECISION,
    total_sip               DOUBLE PRECISION,
    investable_surplus      DOUBLE PRECISION,
    surplus_stability       DOUBLE PRECISION,
    savings_rate            DOUBLE PRECISION,
    risk_capacity           TEXT,
    months_history          INTEGER,
    pct_categorized         DOUBLE PRECISION,
    occupation_declared     TEXT,
    declared_monthly_income DOUBLE PRECISION,
    confidence_band         TEXT,
    -- provenance: seeded rows vs merged uploaded batches (accuracy stays seeded)
    source                  TEXT NOT NULL DEFAULT 'seeded',
    batch_id                TEXT,
    merged_at               TIMESTAMPTZ
);
DROP TABLE IF EXISTS spending_breakdown;
CREATE TABLE spending_breakdown (
    customer_id TEXT,
    category    TEXT,
    avg_monthly DOUBLE PRECISION,
    PRIMARY KEY (customer_id, category)
);
DROP TABLE IF EXISTS income_streams;
CREATE TABLE income_streams (
    customer_id TEXT,
    category    TEXT,
    avg_monthly DOUBLE PRECISION,
    share       DOUBLE PRECISION,
    months_seen INTEGER,
    PRIMARY KEY (customer_id, category)
);
DROP TABLE IF EXISTS key_transactions;
CREATE TABLE key_transactions (
    txn_id      TEXT PRIMARY KEY,
    customer_id TEXT,
    ts          DATE,
    label       TEXT,
    channel     TEXT,
    category    TEXT,
    direction   TEXT,
    amount      DOUBLE PRECISION
);
DROP TABLE IF EXISTS income_by_month;
CREATE TABLE income_by_month (
    month      TEXT PRIMARY KEY,
    avg_income DOUBLE PRECISION
);
DROP TABLE IF EXISTS prospect_scores;
CREATE TABLE prospect_scores (
    customer_id     TEXT PRIMARY KEY,
    p_good_prospect DOUBLE PRECISION,
    reasons         JSONB
);
"""


def load_profiles(duck: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Read gold profile rows plus name/open-date from the bronze customers file.

    Gold is a modelling table and carries neither; they join in here from the
    real bronze data. The explicit column list keeps "_" columns out.
    """
    cols = ", ".join(f"g.{c}" for c in PROFILE_COLS)
    return duck.execute(f"""
        SELECT {cols}, c.name, c.account_open_date
        FROM {PROFILES_READ} g
        JOIN read_parquet('{CUSTOMERS_FILE.as_posix()}') c USING (customer_id)
        ORDER BY g.customer_id""").fetchall()


def load_breakdown(duck: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Average monthly debit spend per customer and silver category."""
    return duck.execute(f"""
        WITH months AS (
            SELECT customer_id, count(DISTINCT year || '-' || month) AS m
            FROM {TXN_READ} GROUP BY 1
        )
        SELECT t.customer_id, t.category,
               round(sum(t.amount) / max(mo.m), 2) AS avg_monthly
        FROM {TXN_READ} t
        JOIN months mo USING (customer_id)
        WHERE t.direction = 'debit'
        GROUP BY 1, 2
        ORDER BY 1, 3 DESC""").fetchall()


def load_income_streams(
    duck: duckdb.DuckDBPyConnection, txn_read: str = TXN_READ
) -> list[tuple]:
    """Average monthly income inflow per category, with recurrence evidence.

    txn_read defaults to the seeded silver table but any silver read expression
    works, so uploaded batches reuse this exact query.
    """
    return duck.execute(f"""
        WITH months AS (
            SELECT customer_id, count(DISTINCT year || '-' || month) AS m
            FROM {txn_read} GROUP BY 1
        ),
        inc AS (
            SELECT customer_id, category, sum(amount) AS total,
                   count(DISTINCT year || '-' || month) AS months_seen
            FROM {txn_read}
            WHERE is_income AND direction = 'credit'
            GROUP BY 1, 2
        ),
        totals AS (SELECT customer_id, sum(total) AS t FROM inc GROUP BY 1)
        SELECT i.customer_id, i.category,
               round(i.total / mo.m, 2)  AS avg_monthly,
               round(i.total / tt.t, 4)  AS share,
               i.months_seen
        FROM inc i
        JOIN months mo USING (customer_id)
        JOIN totals tt USING (customer_id)
        ORDER BY 1, 4 DESC""").fetchall()


def load_key_transactions(
    duck: duckdb.DuckDBPyConnection, per_customer: int = 6, txn_read: str = TXN_READ
) -> list[tuple]:
    """Each customer's largest transactions by amount (most recent first)."""
    return duck.execute(f"""
        SELECT txn_id, customer_id, CAST("timestamp" AS DATE) AS ts,
               COALESCE(counterparty_norm, trim(narration)) AS label,
               channel, category, direction, amount
        FROM (
            SELECT *, row_number() OVER (
                PARTITION BY customer_id ORDER BY amount DESC
            ) AS rn
            FROM {txn_read}
        )
        WHERE rn <= {per_customer}
        ORDER BY customer_id, ts DESC""").fetchall()


def load_income_by_month(duck: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Book-wide average income-classified inflow per customer per month."""
    return duck.execute(f"""
        WITH per_customer AS (
            SELECT year || '-' || month AS ym, customer_id,
                   sum(CASE WHEN is_income AND direction = 'credit'
                            THEN amount ELSE 0 END) AS inflow
            FROM {TXN_READ}
            GROUP BY 1, 2
        )
        SELECT ym, round(avg(inflow), 2) FROM per_customer
        GROUP BY 1 ORDER BY 1""").fetchall()


def score_frame(X, ids, top_k: int = 5) -> list[tuple]:
    """Score a feature matrix with the trained model and top SHAP reason codes.

    Shared by seeded scoring and uploaded-batch scoring so both use the exact
    same model and explanation path.

    Args:
        X: feature matrix with the model's FEATURES columns.
        ids: customer ids aligned with X rows.
        top_k: number of reason codes per customer.

    Returns:
        Rows of (customer_id, probability, reasons-as-plain-list).
    """
    booster = xgb.Booster()
    booster.load_model(MODEL_FILE.as_posix())
    proba = booster.inplace_predict(X[FEATURES])
    sv = shap.TreeExplainer(booster).shap_values(X[FEATURES])
    rows = []
    for i, cid in enumerate(ids):
        order = np.argsort(np.abs(sv[i]))[::-1][:top_k]
        reasons = [
            {
                "feature": FEATURES[j],
                "value": float(X.iloc[i, j]),
                "shap": round(float(sv[i][j]), 4),
            }
            for j in order
        ]
        rows.append((str(cid), float(proba[i]), reasons))
    return rows


def score_customers(top_k: int = 5) -> list[tuple]:
    """Batch-score the seeded book; reasons wrapped as JSONB for Postgres."""
    X, _y, ids, _region = load_features()
    return [
        (cid, proba, Json(reasons))
        for cid, proba, reasons in score_frame(X, ids, top_k)
    ]


def main() -> None:
    """Rebuild all serving tables, then print row counts and a sample."""
    duck = duckdb.connect()
    profiles = load_profiles(duck)
    breakdown = load_breakdown(duck)
    streams = load_income_streams(duck)
    transactions = load_key_transactions(duck)
    monthly = load_income_by_month(duck)
    scores = score_customers()

    pg = connect()
    with pg, pg.cursor() as cur:
        cur.execute(DDL)
        execute_values(
            cur,
            f"INSERT INTO customer_profiles "
            f"({', '.join(PROFILE_COLS)}, name, account_open_date) VALUES %s",
            profiles,
        )
        execute_values(
            cur,
            "INSERT INTO spending_breakdown (customer_id, category, avg_monthly) VALUES %s",
            breakdown,
        )
        execute_values(
            cur,
            "INSERT INTO income_streams "
            "(customer_id, category, avg_monthly, share, months_seen) VALUES %s",
            streams,
        )
        execute_values(
            cur,
            "INSERT INTO key_transactions "
            "(txn_id, customer_id, ts, label, channel, category, direction, amount) VALUES %s",
            transactions,
        )
        execute_values(
            cur, "INSERT INTO income_by_month (month, avg_income) VALUES %s", monthly
        )
        execute_values(
            cur,
            "INSERT INTO prospect_scores (customer_id, p_good_prospect, reasons) VALUES %s",
            scores,
        )
    ensure_review_table(pg)

    with pg, pg.cursor() as cur:
        for table in (
            "customer_profiles",
            "spending_breakdown",
            "income_streams",
            "key_transactions",
            "income_by_month",
            "prospect_scores",
        ):
            cur.execute(f"SELECT count(*) FROM {table}")
            print(f"[serving] {table}: {cur.fetchone()[0]:,} rows")
        cur.execute("""
            SELECT p.customer_id, p.income_type, p.true_monthly_income,
                   p.confidence_band, round(s.p_good_prospect::numeric, 3)
            FROM customer_profiles p JOIN prospect_scores s USING (customer_id)
            LIMIT 1""")
        print(f"[serving] sample lookup: {cur.fetchone()}")
    pg.close()


if __name__ == "__main__":
    main()
