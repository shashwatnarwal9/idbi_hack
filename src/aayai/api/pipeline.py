"""Pipeline endpoints: real Airflow orchestration state via its REST API.

Never scrapes the Airflow HTML UI. When Airflow is down or credentials are
not configured, the endpoint says so honestly instead of inventing state.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Query

from aayai.api.config import (
    AIRFLOW_BASE_URL,
    AIRFLOW_PASSWORD,
    AIRFLOW_USERNAME,
    REPO_URL,
)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])

DAG_ID = "aayai_pipeline"
# display order mirrors the DAG's task chain
TASK_ORDER = [
    "bronze_ingest",
    "silver_transform",
    "gold_build",
    "ge_validation",
    "confidence_branch",
    "train_model",
    "skip_scoring",
]

# Directory `git clone` creates, derived from the config repo URL (no placeholder).
_REPO_DIR = REPO_URL.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")


def _local_setup() -> dict:
    """Real, config-driven commands to run Airflow locally (Pipeline page)."""
    return {
        "repo_url": REPO_URL,
        "repo_dir": _REPO_DIR,
        "clone": f"git clone {REPO_URL}",
        "cd": f"cd {_REPO_DIR}",
        "up": "docker compose up -d",
        "airflow_url": AIRFLOW_BASE_URL,
    }


def _unavailable(reason: str) -> dict:
    return {
        "available": False,
        "reason": reason,
        "ui_url": AIRFLOW_BASE_URL,
        "setup": _local_setup(),
    }


@router.get("/state")
def state(
    username: str | None = Query(None),
    password: str | None = Query(None),
) -> dict:
    """Latest aayai_pipeline run with per-task states, from Airflow's REST API.

    Credentials come from the request when supplied (the Pipeline page lets an
    operator enter an Airflow id/password), otherwise from the server env. When
    neither is set the endpoint reports its unavailable state rather than guess.
    """
    user = username or AIRFLOW_USERNAME
    secret = password or AIRFLOW_PASSWORD
    if not (user and secret):
        return _unavailable(
            "Airflow credentials not configured — enter an Airflow id/password "
            "on this page, or set AAYAI_AIRFLOW_USERNAME / AAYAI_AIRFLOW_PASSWORD."
        )
    auth = (user, secret)
    try:
        runs_res = httpx.get(
            f"{AIRFLOW_BASE_URL}/api/v1/dags/{DAG_ID}/dagRuns",
            params={"limit": 1, "order_by": "-execution_date"},
            auth=auth,
            timeout=5,
        )
        runs_res.raise_for_status()
        dag_runs = runs_res.json().get("dag_runs", [])
        if not dag_runs:
            return {
                "available": True,
                "ui_url": AIRFLOW_BASE_URL,
                "run": None,
                "tasks": [],
            }
        run = dag_runs[0]
        tis_res = httpx.get(
            f"{AIRFLOW_BASE_URL}/api/v1/dags/{DAG_ID}/dagRuns/"
            f"{run['dag_run_id']}/taskInstances",
            auth=auth,
            timeout=5,
        )
        tis_res.raise_for_status()
        instances = tis_res.json().get("task_instances", [])
    except httpx.HTTPStatusError as exc:
        return _unavailable(f"Airflow API returned {exc.response.status_code}")
    except Exception as exc:
        return _unavailable(f"Airflow unreachable ({exc.__class__.__name__})")

    def order_key(ti: dict) -> int:
        try:
            return TASK_ORDER.index(ti["task_id"])
        except ValueError:
            return len(TASK_ORDER)

    tasks = [
        {
            "task_id": ti["task_id"],
            "state": ti.get("state"),
            "start_date": ti.get("start_date"),
            "end_date": ti.get("end_date"),
            "duration": ti.get("duration"),
        }
        for ti in sorted(instances, key=order_key)
    ]
    return {
        "available": True,
        "ui_url": AIRFLOW_BASE_URL,
        "run": {
            "run_id": run["dag_run_id"],
            "state": run["state"],
            "start_date": run.get("start_date"),
            "end_date": run.get("end_date"),
        },
        "tasks": tasks,
    }
