"""Append-only audit trail of customer-facing documents shared with customers.

Distinct from the internal analyst review/audit: this records that a clean
customer summary was generated and offered for download. Rows are only ever
inserted, never updated or deleted, so the trail is tamper-evident by design.
"""

from __future__ import annotations

DDL = """
CREATE TABLE IF NOT EXISTS share_log (
    id            BIGSERIAL PRIMARY KEY,
    customer_id   TEXT NOT NULL,
    shared_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    shared_by     TEXT,
    document_type TEXT NOT NULL DEFAULT 'customer_summary'
)
"""


def ensure_table(conn) -> None:
    """Create the append-only share_log table when missing (idempotent)."""
    with conn, conn.cursor() as cur:
        cur.execute(DDL)


def log_share(
    conn, customer_id: str, shared_by: str, document_type: str = "customer_summary"
) -> dict:
    """Append one share event and return it."""
    with conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO share_log (customer_id, shared_by, document_type) "
            "VALUES (%s, %s, %s) RETURNING shared_at, shared_by, document_type",
            (customer_id, shared_by, document_type),
        )
        shared_at, by, doc = cur.fetchone()
    return {"shared_at": shared_at.isoformat(), "shared_by": by, "document_type": doc}


def last_share(conn, customer_id: str) -> dict | None:
    """Most recent share event for a customer, or None if never shared."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT shared_at, shared_by, document_type FROM share_log "
            "WHERE customer_id = %s ORDER BY shared_at DESC LIMIT 1",
            (customer_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return {
        "shared_at": row[0].isoformat(),
        "shared_by": row[1],
        "document_type": row[2],
    }
