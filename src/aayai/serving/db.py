"""Connection factory for the serving Postgres (compose service serving-postgres)."""

from __future__ import annotations

import os

import psycopg2


def connect():
    """Open a connection using AAYAI_PG_* environment variables or local defaults."""
    return psycopg2.connect(
        host=os.environ.get("AAYAI_PG_HOST", "localhost"),
        port=int(os.environ.get("AAYAI_PG_PORT", "5433")),
        user=os.environ.get("AAYAI_PG_USER", "aayai"),
        password=os.environ.get("AAYAI_PG_PASSWORD", "aayai"),
        dbname=os.environ.get("AAYAI_PG_DB", "aayai"),
    )
