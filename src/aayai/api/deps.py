"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import HTTPException

from aayai.serving.db import connect
from aayai.serving.reviews import ensure_table
from aayai.serving.shares import ensure_table as ensure_share_table
from aayai.uploads.store import ensure_main_source_columns


def get_conn() -> Iterator:
    """Per-request serving-store connection; 503 with an honest message when down."""
    try:
        conn = connect()
        ensure_table(conn)  # review_status must exist for the LEFT JOINs
        ensure_share_table(conn)  # share_log for the customer-share audit trail
        ensure_main_source_columns(conn)  # source/batch_id on customer_profiles
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="serving store unavailable — start serving-postgres and "
            "run aayai.serving.load",
        ) from exc
    try:
        yield conn
    finally:
        conn.close()
