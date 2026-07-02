# आय·AI (AayAI)

**आय** ("aay") is Hindi for income. आय·AI reconstructs a bank customer's true
monthly income and investable surplus from raw transaction narrations, grades
how much each estimate can be trusted, and scores customers as investment
prospects. The value is in the data engineering — narration parsing and
feature reconstruction — with a small, explainable model on top.

Everything runs locally and free: DuckDB for transforms, Parquet for storage,
Great Expectations for data gates, XGBoost + SHAP for scoring and reason
codes, Airflow for orchestration, Postgres for serving, Streamlit for the
dashboard. No cloud calls and no LLM anywhere in the pipeline.

## Architecture

```
raw CSV          bronze              silver                  gold
transactions --> typed Parquet   --> narration parsing   --> customer_profiles
customers        year=/month=        + derived category      income, surplus,
                 partitions          + is_income              risk, confidence
                                                                  |
dashboard    <-- Postgres        <-- XGBoost + SHAP        <-- GE validation
(Streamlit)      point lookups       prospect scores           gates + bands
```

| Layer | Module | Output |
|---|---|---|
| 0 generator | `aayai.datagen` | `data/raw/*.csv` (synthetic, seeded) |
| 1 bronze | `aayai.bronze.ingest` | typed Parquet, partitioned `year=YYYY/month=MM` |
| 2 silver | `aayai.silver.transform` | parsed narrations + derived `category` / `is_income` |
| 3 gold | `aayai.gold.build` | one profile row per customer |
| 4 validation | `aayai.validation.run` | GE gates + `confidence_band` written onto gold |
| 5 model | `aayai.model.train` | `model/aayai_model.ubj` + metrics/fairness reports |
| 6 orchestration | `airflow/dags/aayai_pipeline.py` | one DAG chaining layers 1-5 |
| 7 serving | `aayai.serving.load` + `dashboard/app.py` | Postgres tables + dashboard |

## The ground-truth firewall

The synthetic raw data carries `_`-prefixed ground-truth columns
(`_true_category`, `_is_income`, `_true_monthly_income`, `_is_good_prospect`).
The rules are:

- No transform, feature or model input ever reads a `_` column. SQL enforces
  this structurally (input CTEs whitelist columns; ground truth is re-attached
  only in a marked `EVAL-PASSTHROUGH` block) and tests grep for violations.
- Evaluation modules (`aayai.silver.evaluate`, `aayai.gold.evaluate`) are the
  only readers, to measure accuracy.
- `_is_good_prospect` is used exactly once outside evaluation: as the training
  label.
- Serving tables exclude `_` columns entirely; ground truth never reaches the
  dashboard.

Swap the CSVs in `data/raw/` for real exports with the same schema (minus the
`_` columns) and every stage downstream runs unchanged.

## Getting started

Prerequisites: Python 3.12 (Great Expectations does not yet support 3.14),
Docker Desktop (for Airflow and the serving Postgres).

```powershell
git clone <repo-url> aayai && cd aayai
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt -e .
copy .env.example .env                          # local connection defaults
.venv\Scripts\python -m aayai.datagen           # generate raw CSVs (seeded)
```

## Running the pipeline

```powershell
.venv\Scripts\python -m aayai.bronze.ingest
.venv\Scripts\python -m aayai.silver.transform
.venv\Scripts\python -m aayai.gold.build
.venv\Scripts\python -m aayai.validation.run
.venv\Scripts\python -m aayai.model.train
```

Each step prints its own verification summary. Accuracy against ground truth:

```powershell
.venv\Scripts\python -m aayai.silver.evaluate   # category accuracy
.venv\Scripts\python -m aayai.gold.evaluate     # income reconstruction accuracy
```

### Orchestrated (Airflow)

```powershell
docker compose build
docker compose up -d
docker compose exec airflow-scheduler airflow dags trigger aayai_pipeline
```

UI at http://localhost:8080 (admin/admin, local dev only). The DAG runs
bronze through model with a branch that skips scoring when less than half the
book has a trustworthy confidence band.

### Serving and dashboard

```powershell
docker compose up -d serving-postgres
.venv\Scripts\python -m aayai.serving.load
.venv\Scripts\python -m streamlit run dashboard/app.py
```

Dashboard at http://localhost:8501: pick a customer, see reconstructed income
vs declared, spending breakdown, and the prospect score with SHAP reason
codes.

## Testing

```powershell
.venv\Scripts\python -m pytest -q
```

One test file per layer. Serving tests skip when Postgres is down; the
orchestration tests check DAG/compose wiring at file level since Airflow only
runs inside Docker.

## Results on the reference dataset (seed 42, 200 customers, 18 months)

- Silver category accuracy: 100% on synthetic narrations (the rule set and
  generator share a grammar; real narrations would land lower — the
  `parse_confidence` field exists to route weak parses).
- Income reconstruction: Pearson r 0.954, MAE Rs 9,285, bias strictly
  negative — the engine never overstates income. Gig/business estimates use a
  p25 monthly floor by design.
- Prospect model: ROC-AUC 0.936 on a stratified holdout, against a label with
  4% injected noise.
- Fairness: a variant trained with region gains no AUC, and region carries
  under 2% of SHAP mass. Exact numbers regenerate into
  `model/train_report.json` on every training run.

## Design decisions

- **Conservative income floors.** For volatile earners the 25th percentile of
  monthly net inflow is reported, not the mean: a lender wants a floor.
- **Business netting.** Trade-worded bank-transfer debits are netted against
  merchant receipts, so turnover is not mistaken for income.
- **Confidence as a feature.** Great Expectations results are not just a
  pass/fail gate: per-customer failures against tiered trust checks become the
  `confidence_band` column (high/medium/low).
- **Athena portability.** Transform SQL sticks to functions Athena (Trino)
  also supports; the few DuckDB-only constructs are flagged in comments with
  their Athena equivalents.

## Repository layout

```
airflow/dags/     the aayai_pipeline DAG
dashboard/        Streamlit app
data/             raw/bronze/silver/gold (generated; not tracked)
model/            trained model + reports (generated; not tracked)
sql/              all DuckDB transform SQL
src/aayai/        pipeline packages: bronze, silver, gold, validation,
                  model, serving, plus datagen and shared helpers
tests/            one test file per layer
```
