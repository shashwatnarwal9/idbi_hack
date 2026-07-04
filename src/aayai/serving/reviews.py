"""Analyst review state for customers.

Lives in its own table that serving reloads never drop: a review mark is
analyst-entered state, not derived data, so it must survive pipeline re-runs.
"""

from __future__ import annotations

DDL = """
CREATE TABLE IF NOT EXISTS review_status (
    customer_id TEXT PRIMARY KEY,
    reviewed    BOOLEAN NOT NULL,
    reviewed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_by TEXT
)
"""


def ensure_table(conn) -> None:
    """Create the review table when missing (idempotent, never drops)."""
    with conn, conn.cursor() as cur:
        cur.execute(DDL)


def get_review(conn, customer_id: str) -> dict:
    """Current review state; an unreviewed customer yields reviewed=False."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT reviewed, reviewed_at, reviewed_by FROM review_status "
            "WHERE customer_id = %s",
            (customer_id,),
        )
        row = cur.fetchone()
    if row is None:
        return {"reviewed": False, "reviewed_at": None, "reviewed_by": None}
    return {
        "reviewed": row[0],
        "reviewed_at": row[1].isoformat(),
        "reviewed_by": row[2],
    }


def set_review(conn, customer_id: str, reviewed: bool, reviewed_by: str) -> dict:
    """Upsert the review mark and return the stored state."""
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO review_status (customer_id, reviewed, reviewed_by)
            VALUES (%s, %s, %s)
            ON CONFLICT (customer_id) DO UPDATE
            SET reviewed = EXCLUDED.reviewed,
                reviewed_by = EXCLUDED.reviewed_by,
                reviewed_at = now()
            RETURNING reviewed, reviewed_at, reviewed_by
            """,
            (customer_id, reviewed, reviewed_by),
        )
        row = cur.fetchone()
    return {
        "reviewed": row[0],
        "reviewed_at": row[1].isoformat(),
        "reviewed_by": row[2],
    }
