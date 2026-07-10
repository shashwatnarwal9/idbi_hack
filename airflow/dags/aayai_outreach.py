"""Daily outreach refresh DAG.

Re-derives timing windows from the latest signals, proposes interactions for
top leads that have none open, and surfaces due reminders. Nothing is approved
or sent here, the agent proposes, the RM commits in the dashboard.

Requires NVIDIA_API_KEY in the Airflow environment (the strategist is GLM-5.2).
Equivalent manual run:  python -m aayai.agent.run_planner
"""

from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator


def _refresh() -> None:
    from aayai.agent.run_planner import refresh

    refresh(rm_id="rm-1", product="personal", quadrant="act_now", top=5)


with DAG(
    dag_id="aayai_outreach_refresh",
    description="Propose outreach for top leads and enqueue due reminders",
    start_date=datetime(2026, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["aayai", "outreach"],
) as dag:
    PythonOperator(task_id="outreach_refresh", python_callable=_refresh)
