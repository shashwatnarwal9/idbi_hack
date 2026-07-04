# आय·AI (AayAI)

**आय** ("aay") means income in Hindi.

आय·AI is a data pipeline that works out a bank customer's **real monthly income**
and **investable surplus** by parsing raw transaction narrations (UPI / NEFT /
IMPS / ACH strings), then scores each customer as an investment prospect —
with a confidence grade attached to every estimate.

Everything runs locally and free. No cloud calls, no LLM.

## What it does

1. **Parses** messy narration strings into channel, counterparty and category.
2. **Reconstructs income** — detects recurring salaries; uses a conservative
   monthly floor for gig workers and merchants (netting out supplier payments).
3. **Computes surplus** — income minus essentials, EMIs and a safety buffer.
4. **Grades trust** — every customer gets a high / medium / low
   `confidence_band` based on history length and parse quality.
5. **Scores prospects** — a small XGBoost model with SHAP reason codes,
   audited to show it does not lean on region.

## Stack

| Purpose | Tool |
|---|---|
| Transforms | DuckDB SQL (Athena-compatible where possible) |
| Storage | Parquet, partitioned `year=YYYY/month=MM` |
| Data quality | Great Expectations |
| Model | XGBoost + scikit-learn + SHAP |
| Orchestration | Airflow (docker-compose, LocalExecutor) |
| Serving | Postgres |
| Dashboard | Streamlit + Altair |

## How it flows

```
data/raw/*.csv                                (stage 0: seeded generator)
   |  bronze   typed Parquet, partitioned     aayai.bronze.ingest
   |  silver   parsed narrations + category   aayai.silver.transform
   |  gold     one profile row per customer   aayai.gold.build
   |  gates    GE checks + confidence_band    aayai.validation.run
   |  model    prospect score + SHAP          aayai.model.train
   v  serving  Postgres -> Streamlit          aayai.serving.load, dashboard/
```

## Quickstart

Prerequisites: **Python 3.12** (Great Expectations does not support 3.14 yet)
and **Docker Desktop** (only for Airflow and the serving database).

```powershell
git clone <repo-url> aayai
cd aayai
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt -e .
copy .env.example .env
```

Generate data and run the pipeline:

```powershell
.venv\Scripts\python -m aayai.datagen             # synthetic raw CSVs (seeded)
.venv\Scripts\python -m aayai.bronze.ingest
.venv\Scripts\python -m aayai.silver.transform
.venv\Scripts\python -m aayai.gold.build
.venv\Scripts\python -m aayai.validation.run
.venv\Scripts\python -m aayai.model.train
```

Every step prints its own verification summary. Check accuracy against the
built-in ground truth:

```powershell
.venv\Scripts\python -m aayai.silver.evaluate     # category accuracy
.venv\Scripts\python -m aayai.gold.evaluate       # income accuracy
```

Run the tests:

```powershell
.venv\Scripts\python -m pytest -q
```

## Dashboard

```powershell
docker compose up -d serving-postgres
.venv\Scripts\python -m aayai.serving.load
.venv\Scripts\python -m streamlit run dashboard/app.py
```

Open http://localhost:8501, pick a customer, and see: reconstructed income vs
what they declared, spending breakdown, and the prospect score with SHAP
reason codes.

## Airflow (optional)

```powershell
docker compose build
docker compose up -d
docker compose exec airflow-scheduler airflow dags trigger aayai_pipeline
```

UI at http://localhost:8080 (admin / admin, local dev only). One DAG,
`aayai_pipeline`, chains bronze through model; a branch skips model training
when too little of the book has a trustworthy confidence band.

## The ground-truth firewall

The synthetic data carries `_`-prefixed answer columns (`_true_category`,
`_is_income`, `_true_monthly_income`, `_is_good_prospect`) so results can be
measured. Strict rules, enforced by SQL structure and tests:

- No transform or model feature ever reads a `_` column.
- Only the two `evaluate` modules read them, to score the pipeline.
- `_is_good_prospect` is used once outside evaluation: as the training label.
- Serving and the dashboard never see them at all.

Swap in real CSVs with the same schema (minus `_` columns) and everything
downstream runs unchanged.

## Results (seed 42 — 200 customers, 18 months, 84,818 transactions)

| Measure | Result |
|---|---|
| Category accuracy (silver) | 100% on synthetic narrations* |
| Income reconstruction (gold) | Pearson r 0.954, MAE Rs 9,285, never overstates |
| Prospect model (holdout) | ROC-AUC 0.936 against a label with 4% noise |
| Fairness | region adds no AUC; under 2% of SHAP mass |

*The rule set and the generator share a grammar, so treat 100% as an upper
bound; `parse_confidence` exists to route weak parses on real data.

## Repository layout

```
airflow/dags/    aayai_pipeline DAG
dashboard/       Streamlit app
data/            raw / bronze / silver / gold   (generated, not tracked)
model/           trained model + reports        (generated, not tracked)
sql/             all DuckDB transform SQL
src/aayai/       bronze, silver, gold, validation, model, serving,
                 datagen and shared helpers
tests/           one test file per layer
```
