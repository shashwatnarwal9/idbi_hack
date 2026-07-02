# आय·AI (AayAI)

**आय** ("aay") means **income**. आय·AI is a medallion-architecture data pipeline
that reconstructs a bank customer's *true* income and investable surplus from
messy transaction narrations, then scores them as investment prospects.
Built for the IDBI × AWS hackathon. Local stack: DuckDB · Parquet ·
Great Expectations · XGBoost/SHAP · Airflow · Postgres · Streamlit.

**Ground-truth firewall:** raw data carries `_`-prefixed columns
(`_true_category`, `_is_income`, `_true_monthly_income`, `_is_good_prospect`).
They are for **evaluation only** — no transform or model ever reads them as an
input. The pipeline derives its own labels and is scored against them.

## Quickstart

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt -e .
.venv\Scripts\python -m aayai.datagen          # stage 0: synthetic raw CSVs
.venv\Scripts\python -m aayai.bronze.ingest    # stage 1: bronze parquet
.venv\Scripts\python -m pytest -q              # sanity tests
```

## Stage log

| Stage | What | Status |
|-------|------|--------|
| 0 | Synthetic raw data generator (`aayai.datagen`) | done |
| 1 | Bronze: CSV → typed Parquet, partitioned `year=YYYY/month=MM` (`aayai.bronze.ingest`) | done |
| 2 | Silver: narration parsing + rule categorization (`aayai.silver.transform`), eval vs ground truth (`aayai.silver.evaluate`) | done |
| 3 | Gold: income engine → `customer_profiles.parquet` (`aayai.gold.build`), eval vs ground truth (`aayai.gold.evaluate`) | done |
| 4 | Great Expectations gates + `confidence_band` feature write-back (`aayai.validation.run`) | done |
| 5 | XGBoost prospect model + SHAP + fairness audit (`aayai.model.train`) | done |
| 6 | Airflow DAG `aayai_pipeline` (docker-compose, LocalExecutor) | done |
| 7 | Postgres serving store (`aayai.serving.load`) + Streamlit dashboard (`dashboard/app.py`) | done |
| 8+ | Final polish | pending |
