"""Connection factory for the serving Postgres.

Two ways to point at a database, in priority order:
  1. SERVING_DB_DSN: a full ``postgres://…`` connection string. This is what
     managed hosts (Render, etc.) inject, so production sets exactly one var.
  2. AAYAI_PG_*: host/port/user/password/db pieces, used for the local
     docker-compose Postgres and as the developer default.

load_dotenv() is called here (not just by the API app) so standalone scripts,
aayai.serving.migrate, aayai.serving.load, tests, also pick up a local .env
without needing the caller to load it first.
"""

from __future__ import annotations

import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def connect():
    """Open a serving-store connection from SERVING_DB_DSN or the AAYAI_PG_* parts."""
    dsn = os.environ.get("SERVING_DB_DSN")
    if dsn:
        return psycopg2.connect(dsn)
    return psycopg2.connect(
        host=os.environ.get("AAYAI_PG_HOST", "localhost"),
        port=int(os.environ.get("AAYAI_PG_PORT", "5433")),
        user=os.environ.get("AAYAI_PG_USER", "aayai"),
        password=os.environ.get("AAYAI_PG_PASSWORD", "aayai"),
        dbname=os.environ.get("AAYAI_PG_DB", "aayai"),
    )
