"""Outreach planner: turns a lead + its real signals into a PROPOSED interaction.

Composes the deterministic pieces (scheduler windows, guardrails) with the
strategist/council (LLM) and writes a PLANNED, UNAPPROVED interaction row.
Humans approve before anything lands on a calendar or is marked sent.

The planner never invents a why_now: it reads the lead's behaviour/engagement
signals from the serving store and uses the top scheduler window's sentence.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from aayai.agent.council import TextLLM, run_strategist
from aayai.agent.guardrails import (
    CONTACT_WINDOW_DAYS,
    GuardrailError,
    check_channel,
    check_frequency,
    validate_message,
)
from aayai.agent.scheduler import propose_slots, timing_windows

log = logging.getLogger("aayai.agent.planner")

DEFAULT_CHANNEL = "phone"


@dataclass
class PlanOutcome:
    created: bool
    interaction: dict | None
    reason: str  # why created / why skipped
    used_council: bool = False
    proposed_slots: list[str] | None = None


def _lead_signals(conn, cust_id: str) -> dict:
    """Real signals for a customer from the serving store (never invented)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT b.emi_ending, b.ending_stream,
                   e.days_since_strong_event, e.last_event_type
            FROM customer_profiles p
            LEFT JOIN behaviour_signals b USING (customer_id)
            LEFT JOIN engagement_summary e USING (customer_id)
            WHERE p.customer_id = %s
            """,
            (cust_id,),
        )
        row = cur.fetchone()
    if row is None:
        return {}
    return {
        "emi_ending": bool(row[0]),
        "ending_stream": row[1],
        "days_since_strong_event": row[2],
        "last_event_type": row[3],
    }


def plan_outreach(
    conn,
    lead: dict,
    rm_id: str,
    client: TextLLM,
    *,
    now: datetime | None = None,
    channel: str = DEFAULT_CHANNEL,
) -> PlanOutcome:
    """Plan one lead end to end; returns the created row or the skip reason."""
    from aayai.serving import calendar_store, interactions

    interactions.ensure_table(conn)
    calendar_store.ensure_table(conn)
    now = now or datetime.now().astimezone()
    cust_id = lead["customer_id"]

    # guardrails first, cheap and non-negotiable
    try:
        check_channel(channel)
        check_frequency(
            interactions.recent_contact_count(conn, cust_id, CONTACT_WINDOW_DAYS)
        )
    except GuardrailError as exc:
        return PlanOutcome(False, None, f"guardrail: {exc}")

    # timing windows from the customer's REAL signals
    signals = _lead_signals(conn, cust_id)
    windows = timing_windows(
        now=now,
        quadrant=lead.get("quadrant", "exclude"),
        emi_ending=signals.get("emi_ending", False),
        ending_stream=signals.get("ending_stream"),
        days_since_strong_event=signals.get("days_since_strong_event"),
        last_event_type=signals.get("last_event_type"),
    )
    if not windows:
        return PlanOutcome(False, None, "no open timing window (no signal fired)")
    window = windows[0]

    # concrete slot proposals around the RM's calendar
    busy = calendar_store.busy(conn, rm_id, window.opens, window.closes)
    slots = propose_slots(window, busy)
    scheduled_at = slots[0].isoformat() if slots else None

    # strategist / council decides HOW; the window decided WHY and WHEN
    try:
        strategy = run_strategist(lead, window.why_now, client)
    except Exception as exc:  # LLM outage skips this lead, never kills the run
        log.warning("strategist unavailable for %s: %s", cust_id, exc)
        return PlanOutcome(False, None, f"strategist unavailable: {exc}")
    message = strategy.drafted_message or ""
    check = validate_message(message)
    if not check.ok:
        log.warning("draft failed contract for %s: %s", cust_id, check.problems)
        message = ""  # store no message rather than a bad one; RM drafts by hand

    row = interactions.create(
        conn,
        cust_id=cust_id,
        rm_id=rm_id,
        product=lead.get("product") or lead.get("best_fit_product"),
        scheduled_at=scheduled_at,
        channel=channel,
        why_now=window.why_now,
        signals=[window.signal],
        approach_notes=strategy.approach,
        drafted_message=message or None,
    )
    return PlanOutcome(
        True,
        row,
        "planned (awaiting human approval)",
        used_council=strategy.used_council,
        proposed_slots=[s.isoformat() for s in slots],
    )
