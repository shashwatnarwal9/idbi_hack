"""Lead contact workflow state (mark-contacted).

Its own table that serving reloads never drop, a contacted mark is workflow
state, not derived data. STRICT firewall: nothing here ever feeds a behaviour,
engagement, intent or lead score; it only records that an analyst reached out.
"""

from __future__ import annotations

DDL = """
CREATE TABLE IF NOT EXISTS lead_contacts (
    customer_id  TEXT NOT NULL,
    product      TEXT NOT NULL,
    contacted    BOOLEAN NOT NULL,
    contacted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    contacted_by TEXT,
    PRIMARY KEY (customer_id, product)
)
"""


def ensure_table(conn) -> None:
    """Create the contacts table when missing (idempotent, never drops)."""
    with conn, conn.cursor() as cur:
        cur.execute(DDL)


def set_contacted(
    conn, customer_id: str, product: str, contacted: bool, contacted_by: str
) -> dict:
    """Upsert the contacted mark for one customer × product lead."""
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO lead_contacts (customer_id, product, contacted, contacted_by)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (customer_id, product) DO UPDATE
            SET contacted = EXCLUDED.contacted,
                contacted_by = EXCLUDED.contacted_by,
                contacted_at = now()
            RETURNING contacted, contacted_at, contacted_by
            """,
            (customer_id, product, contacted, contacted_by),
        )
        row = cur.fetchone()
    return {
        "customer_id": customer_id,
        "product": product,
        "contacted": row[0],
        "contacted_at": row[1].isoformat(),
        "contacted_by": row[2],
    }


def contacted_set(conn, product: str) -> set[str]:
    """Customer ids already contacted for a product (for list display only)."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT customer_id FROM lead_contacts "
            "WHERE product = %s AND contacted = true",
            (product,),
        )
        return {r[0] for r in cur.fetchall()}
