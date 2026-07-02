"""आय·AI Serving loader: gold profiles + silver aggregates + model scores -> Postgres.

Three tables, all keyed by customer_id, all point-lookup friendly:
  customer_profiles   one row per customer (gold, WITHOUT "_" ground truth —
                      serving is bank-facing; ground truth never leaves the lake)
  spending_breakdown  avg monthly debit spend per silver category
  prospect_scores     model probability + top SHAP reason codes, precomputed
                      here so the dashboard needs no xgboost/shap at runtime

Idempotent: tables are dropped and rebuilt on every load.
"""
from __future__ import annotations

import numpy as np
import duckdb
import shap
import xgboost as xgb
from psycopg2.extras import Json, execute_values

from aayai.gold.build import PROFILES_READ
from aayai.model.train import FEATURES, MODEL_FILE, load_features
from aayai.serving.db import connect
from aayai.silver.transform import TXN_READ

PROFILE_COLS = ["customer_id", "region", "income_type", "true_monthly_income",
                "income_volatility", "avg_monthly_essentials", "total_emi",
                "total_sip", "investable_surplus", "surplus_stability",
                "savings_rate", "risk_capacity", "months_history",
                "pct_categorized", "occupation_declared",
                "declared_monthly_income", "confidence_band"]

DDL = """
DROP TABLE IF EXISTS customer_profiles;
CREATE TABLE customer_profiles (
    customer_id             TEXT PRIMARY KEY,
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
    confidence_band         TEXT
);
DROP TABLE IF EXISTS spending_breakdown;
CREATE TABLE spending_breakdown (
    customer_id TEXT,
    category    TEXT,
    avg_monthly DOUBLE PRECISION,
    PRIMARY KEY (customer_id, category)
);
DROP TABLE IF EXISTS prospect_scores;
CREATE TABLE prospect_scores (
    customer_id     TEXT PRIMARY KEY,
    p_good_prospect DOUBLE PRECISION,
    reasons         JSONB
);
"""


def load_profiles(duck: duckdb.DuckDBPyConnection) -> list[tuple]:
    # explicit column list = the "_" firewall for serving
    cols = ", ".join(PROFILE_COLS)
    return duck.execute(f"SELECT {cols} FROM {PROFILES_READ} ORDER BY customer_id").fetchall()


def load_breakdown(duck: duckdb.DuckDBPyConnection) -> list[tuple]:
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


def score_customers(top_k: int = 5) -> list[tuple]:
    """Batch-score every customer and keep the top SHAP drivers as reason codes."""
    X, _y, ids, _region = load_features()
    booster = xgb.Booster()
    booster.load_model(MODEL_FILE.as_posix())
    proba = booster.inplace_predict(X[FEATURES])
    sv = shap.TreeExplainer(booster).shap_values(X[FEATURES])
    rows = []
    for i, cid in enumerate(ids):
        order = np.argsort(np.abs(sv[i]))[::-1][:top_k]
        reasons = [{"feature": FEATURES[j], "value": float(X.iloc[i, j]),
                    "shap": round(float(sv[i][j]), 4)} for j in order]
        rows.append((str(cid), float(proba[i]), Json(reasons)))
    return rows


def main() -> None:
    duck = duckdb.connect()
    profiles = load_profiles(duck)
    breakdown = load_breakdown(duck)
    scores = score_customers()

    pg = connect()
    with pg, pg.cursor() as cur:
        cur.execute(DDL)
        execute_values(cur,
                       f"INSERT INTO customer_profiles ({', '.join(PROFILE_COLS)}) VALUES %s",
                       profiles)
        execute_values(cur,
                       "INSERT INTO spending_breakdown (customer_id, category, avg_monthly) VALUES %s",
                       breakdown)
        execute_values(cur,
                       "INSERT INTO prospect_scores (customer_id, p_good_prospect, reasons) VALUES %s",
                       scores)

    with pg, pg.cursor() as cur:
        for table in ("customer_profiles", "spending_breakdown", "prospect_scores"):
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
