"""RM calendar events: the minimal store behind the calendar_* agent tools.

Workflow state (never dropped by serving reloads, like review_status). Events
are only created for APPROVED interactions, the approval guardrail is checked
at the tool layer, and enforced here again by requiring an interaction_id whose
row carries approved_at.
"""

from __future__ import annotations

from datetime import datetime

DDL = """
CREATE TABLE IF NOT EXISTS rm_calendar_events (
    id             BIGSERIAL PRIMARY KEY,
    rm_id          TEXT NOT NULL,
    cust_id        TEXT,
    interaction_id BIGINT REFERENCES interactions (id),
    starts_at      TIMESTAMPTZ NOT NULL,
    ends_at        TIMESTAMPTZ NOT NULL,
    title          TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS rm_calendar_rm_idx ON rm_calendar_events (rm_id, starts_at);
"""


def ensure_table(conn) -> None:
    """Create the calendar table when missing (idempotent, never drops)."""
    with conn, conn.cursor() as cur:
        cur.execute(DDL)


def busy(conn, rm_id: str, window_start: datetime, window_end: datetime):
    """The RM's busy intervals inside a window, for slot proposals."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT starts_at, ends_at FROM rm_calendar_events
            WHERE rm_id = %s AND starts_at < %s AND ends_at > %s
            ORDER BY starts_at
            """,
            (rm_id, window_end, window_start),
        )
        return [(r[0], r[1]) for r in cur.fetchall()]


def create_event(
    conn,
    *,
    rm_id: str,
    cust_id: str,
    interaction_id: int,
    starts_at: str,
    ends_at: str,
    title: str,
) -> dict:
    """Insert a calendar event for an APPROVED interaction (DB-side check)."""
    with conn, conn.cursor() as cur:
        cur.execute(
            "SELECT approved_at FROM interactions WHERE id = %s", (interaction_id,)
        )
        row = cur.fetchone()
        if row is None:
            raise KeyError(f"interaction {interaction_id} not found")
        if row[0] is None:
            raise PermissionError(
                "interaction is not approved; a human must approve before "
                "anything lands on a calendar"
            )
        cur.execute(
            """
            INSERT INTO rm_calendar_events
                (rm_id, cust_id, interaction_id, starts_at, ends_at, title)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, rm_id, cust_id, interaction_id, starts_at, ends_at, title
            """,
            (rm_id, cust_id, interaction_id, starts_at, ends_at, title),
        )
        r = cur.fetchone()
    return {
        "id": r[0],
        "rm_id": r[1],
        "cust_id": r[2],
        "interaction_id": r[3],
        "starts_at": r[4].isoformat(),
        "ends_at": r[5].isoformat(),
        "title": r[6],
    }
