"""API configuration, read from the environment (.env supported, no secrets in code).

The serving-store connection itself stays in aayai.serving.db, which already
reads AAYAI_PG_* from the environment — the API reuses it rather than holding
its own DSN.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# deployment environment tag, surfaced on /health (e.g. "local", "render")
AAYAI_ENV = os.environ.get("AAYAI_ENV", "local")

# Browser origins allowed to call the API. Comma-separate for more than one
# (e.g. the deployed static site plus a preview URL); defaults to the dev server.
CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get("AAYAI_CORS_ORIGIN", "http://localhost:5173").split(",")
    if o.strip()
]

# Airflow REST API endpoint + credentials; None means "not configured" and the
# pipeline endpoints must report unavailable instead of guessing
AIRFLOW_BASE_URL = os.environ.get("AAYAI_AIRFLOW_BASE_URL", "http://localhost:8080")
AIRFLOW_USERNAME = os.environ.get("AAYAI_AIRFLOW_USERNAME")
AIRFLOW_PASSWORD = os.environ.get("AAYAI_AIRFLOW_PASSWORD")
