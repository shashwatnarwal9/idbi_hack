"""आय·AI pipeline DAG — orchestration ONLY.

bronze -> silver -> gold -> validation -> confidence branch -> model / skip

Every task is a thin wrapper importing the stage's existing main() from
src/aayai (mounted at /opt/aayai, on PYTHONPATH). No pipeline logic lives here.
Imports happen inside the callables so DAG parsing stays fast and dependency-
free. Trigger manually (schedule=None) or from the UI.
"""
from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.python import BranchPythonOperator, PythonOperator

# If less than half the book has a trustworthy (high/medium) confidence_band,
# training a scorer on it would amplify noise -> skip scoring instead.
MIN_TRUSTED_SHARE = 0.50


def _bronze() -> None:
    from aayai.bronze.ingest import main
    main()


def _silver() -> None:
    from aayai.silver.transform import main
    main()


def _gold() -> None:
    from aayai.gold.build import main
    main()


def _validation() -> None:
    # exits non-zero (fails the task) if a GE gate fails; also writes the
    # confidence_band feature the branch below decides on
    from aayai.validation.run import main
    main()


def _confidence_branch() -> str:
    import duckdb

    from aayai.gold.build import PROFILES_READ

    trusted, total = duckdb.connect().execute(
        f"SELECT sum(CASE WHEN confidence_band IN ('high', 'medium') "
        f"THEN 1 ELSE 0 END), count(*) FROM {PROFILES_READ}").fetchone()
    share = trusted / total
    print(f"[branch] trusted population share = {share:.1%} "
          f"(threshold {MIN_TRUSTED_SHARE:.0%})")
    return "train_model" if share >= MIN_TRUSTED_SHARE else "skip_scoring"


def _train() -> None:
    from aayai.model.train import main
    main()


def _skip() -> None:
    print("insufficient data, skip scoring")


with DAG(
    dag_id="aayai_pipeline",
    description="AayAI medallion pipeline: bronze->silver->gold->GE->model",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args={"retries": 0},
    tags=["aayai"],
) as dag:
    bronze = PythonOperator(task_id="bronze_ingest", python_callable=_bronze)
    silver = PythonOperator(task_id="silver_transform", python_callable=_silver)
    gold = PythonOperator(task_id="gold_build", python_callable=_gold)
    validation = PythonOperator(task_id="ge_validation", python_callable=_validation)
    branch = BranchPythonOperator(task_id="confidence_branch",
                                  python_callable=_confidence_branch)
    train = PythonOperator(task_id="train_model", python_callable=_train)
    skip = PythonOperator(task_id="skip_scoring", python_callable=_skip)

    bronze >> silver >> gold >> validation >> branch >> [train, skip]
