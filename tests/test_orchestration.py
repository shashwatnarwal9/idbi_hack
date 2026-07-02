"""Orchestration tests: DAG and compose wiring, checked at text/YAML level
because Airflow itself only runs inside Docker."""

from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
DAG_FILE = ROOT / "airflow" / "dags" / "aayai_pipeline.py"
COMPOSE_FILE = ROOT / "docker-compose.yaml"

TASK_IDS = [
    "bronze_ingest",
    "silver_transform",
    "gold_build",
    "ge_validation",
    "confidence_branch",
    "train_model",
    "skip_scoring",
]

STAGE_IMPORTS = [
    "aayai.bronze.ingest",
    "aayai.silver.transform",
    "aayai.gold.build",
    "aayai.validation.run",
    "aayai.model.train",
]


def test_dag_declares_all_tasks():
    text = DAG_FILE.read_text(encoding="utf-8")
    assert 'dag_id="aayai_pipeline"' in text
    for task_id in TASK_IDS:
        assert f'task_id="{task_id}"' in text


def test_dag_only_orchestrates():
    """Tasks must import existing stage mains — no duplicated pipeline logic."""
    text = DAG_FILE.read_text(encoding="utf-8")
    for module in STAGE_IMPORTS:
        assert f"from {module} import main" in text
    assert "COPY (" not in text  # no SQL re-implemented in the DAG
    assert "read_csv_auto" not in text


def test_compose_shape():
    yaml = pytest.importorskip("yaml")
    cfg = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    services = cfg["services"]
    assert {
        "postgres",
        "airflow-init",
        "airflow-webserver",
        "airflow-scheduler",
    } <= set(services)
    env = cfg["x-airflow-common"]["environment"]
    assert env["AIRFLOW__CORE__EXECUTOR"] == "LocalExecutor"
    assert env["AAYAI_ROOT"] == "/opt/aayai"
    assert "/opt/aayai/src" in env["PYTHONPATH"]
