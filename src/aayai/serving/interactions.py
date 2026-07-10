"""Outreach interactions: the lead-to-outcome tracking table + state machine.

One row per planned outreach: who, when, channel, WHY NOW (always traced to a
real signal), the drafted message, approval state, and the outcome. Lives in
its own table that serving reloads never drop (workflow state, like
review_status / lead_contacts). STRICT firewall: nothing here ever feeds a
behaviour, engagement, intent or lead score.

Status state machine (enforced here, not in the agent):
    planned -> contacted | dormant
    contacted -> responded | dormant
    responded -> converted | dormant
    converted, dormant are terminal
Approval is separate from status: a row starts unapproved; calendar writes and
"sent" marks are blocked until approved_at is set by a human.
"""

from __future__ import annotations

from psycopg2.extras import Json

STATUSES = ("planned", "contacted", "responded", "converted", "dormant")

# legal transitions; terminal states have no exits
TRANSITIONS: dict[str, set[str]] = {
    "planned": {"contacted", "dormant"},
    "contacted": {"responded", "dormant"},
    "responded": {"converted", "dormant"},
    "converted": set(),
    "dormant": set(),
}

DDL = """
CREATE TABLE IF NOT EXISTS interactions (
    id               BIGSERIAL PRIMARY KEY,
    cust_id          TEXT NOT NULL,
    rm_id            TEXT NOT NULL,
    product          TEXT,
    scheduled_at     TIMESTAMPTZ,
    channel          TEXT,
    status           TEXT NOT NULL DEFAULT 'planned',
    why_now          TEXT,
    signals          JSONB,
    approach_notes   TEXT,
    drafted_message  TEXT,
    outcome          TEXT,
    next_action      TEXT,
    approved_at      TIMESTAMPTZ,
    approved_by      TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS interactions_cust_idx ON interactions (cust_id);
CREATE INDEX IF NOT EXISTS interactions_due_idx
    ON interactions (rm_id, scheduled_at)
    WHERE status IN ('planned', 'contacted');
"""

_COLS = (
    "id, cust_id, rm_id, product, scheduled_at, channel, status, why_now, "
    "signals, approach_notes, drafted_message, outcome, next_action, "
    "approved_at, approved_by, created_at, updated_at"
)


class IllegalTransition(ValueError):
    """Raised when a status change violates the state machine."""


def ensure_table(conn) -> None:
    """Create the interactions table when missing (idempotent, never drops)."""
    with conn, conn.cursor() as cur:
        cur.execute(DDL)


def _row_to_dict(cur, row) -> dict:
    d = dict(zip([c[0] for c in cur.description], row))
    for key in ("scheduled_at", "approved_at", "created_at", "updated_at"):
        if d.get(key) is not None:
            d[key] = d[key].isoformat()
    return d


def create(
    conn,
    *,
    cust_id: str,
    rm_id: str,
    product: str | None = None,
    scheduled_at: str | None = None,
    channel: str | None = None,
    why_now: str | None = None,
    signals: list | dict | None = None,
    approach_notes: str | None = None,
    drafted_message: str | None = None,
) -> dict:
    """Insert a new PLANNED, UNAPPROVED interaction and return the row."""
    with conn, conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO interactions
                (cust_id, rm_id, product, scheduled_at, channel, why_now,
                 signals, approach_notes, drafted_message)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING {_COLS}
            """,
            (
                cust_id,
                rm_id,
                product,
                scheduled_at,
                channel,
                why_now,
                Json(signals) if signals is not None else None,
                approach_notes,
                drafted_message,
            ),
        )
        return _row_to_dict(cur, cur.fetchone())


def get(conn, interaction_id: int) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {_COLS} FROM interactions WHERE id = %s", (interaction_id,)
        )
        row = cur.fetchone()
        return _row_to_dict(cur, row) if row else None


def update(
    conn,
    interaction_id: int,
    *,
    status: str | None = None,
    outcome: str | None = None,
    next_action: str | None = None,
    scheduled_at: str | None = None,
    drafted_message: str | None = None,
    approach_notes: str | None = None,
) -> dict:
    """Update a row; a status change must follow the state machine."""
    current = get(conn, interaction_id)
    if current is None:
        raise KeyError(f"interaction {interaction_id} not found")
    if status is not None and status != current["status"]:
        if status not in STATUSES:
            raise IllegalTransition(f"unknown status '{status}'")
        allowed = TRANSITIONS[current["status"]]
        if status not in allowed:
            raise IllegalTransition(
                f"cannot move {current['status']} -> {status}; "
                f"allowed: {sorted(allowed) or 'none (terminal)'}"
            )
    sets, params = ["updated_at = now()"], []
    for col, val in (
        ("status", status),
        ("outcome", outcome),
        ("next_action", next_action),
        ("scheduled_at", scheduled_at),
        ("drafted_message", drafted_message),
        ("approach_notes", approach_notes),
    ):
        if val is not None:
            sets.append(f"{col} = %s")
            params.append(val)
    params.append(interaction_id)
    with conn, conn.cursor() as cur:
        cur.execute(
            f"UPDATE interactions SET {', '.join(sets)} WHERE id = %s RETURNING {_COLS}",
            params,
        )
        return _row_to_dict(cur, cur.fetchone())


def approve(conn, interaction_id: int, approved_by: str) -> dict:
    """Human approval, unlocks calendar writes / sending for this row."""
    with conn, conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE interactions
            SET approved_at = now(), approved_by = %s, updated_at = now()
            WHERE id = %s RETURNING {_COLS}
            """,
            (approved_by, interaction_id),
        )
        row = cur.fetchone()
        if row is None:
            raise KeyError(f"interaction {interaction_id} not found")
        return _row_to_dict(cur, row)


def list_interactions(
    conn,
    *,
    cust_id: str | None = None,
    rm_id: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[dict]:
    where, params = ["1=1"], []
    if cust_id:
        where.append("cust_id = %s")
        params.append(cust_id)
    if rm_id:
        where.append("rm_id = %s")
        params.append(rm_id)
    if status:
        where.append("status = %s")
        params.append(status)
    params.append(limit)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {_COLS} FROM interactions
            WHERE {' AND '.join(where)}
            ORDER BY scheduled_at NULLS LAST, id
            LIMIT %s
            """,
            params,
        )
        return [_row_to_dict(cur, r) for r in cur.fetchall()]


def reminders_due(conn, rm_id: str, now_sql: str = "now()") -> list[dict]:
    """Open interactions whose scheduled time has arrived for this RM."""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT {_COLS} FROM interactions
            WHERE rm_id = %s
              AND status IN ('planned', 'contacted')
              AND scheduled_at IS NOT NULL
              AND scheduled_at <= {now_sql}
            ORDER BY scheduled_at
            """,
            (rm_id,),
        )
        return [_row_to_dict(cur, r) for r in cur.fetchall()]


def recent_contact_count(conn, cust_id: str, window_days: int) -> int:
    """Contacts scheduled/made for a customer inside the frequency window."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FROM interactions
            WHERE cust_id = %s
              AND status <> 'dormant'
              AND created_at >= now() - make_interval(days => %s)
            """,
            (cust_id, window_days),
        )
        return int(cur.fetchone()[0])
