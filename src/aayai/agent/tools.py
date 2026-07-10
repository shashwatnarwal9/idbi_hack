"""Agent tool surface: thin, typed wrappers over the serving store.

No business logic lives here: each tool is a small function plus a JSON schema
the model sees. Guardrails (channel allow-list, frequency cap, human-approval
gate) run INSIDE the write tools so the model cannot bypass them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

BANDS_ORDER = {"low": 0, "medium": 1, "high": 2}
QUADRANTS = ("act_now", "nurture", "downsell", "exclude")
PRODUCTS = ("personal", "auto", "home", "mortgage")


@dataclass
class Tool:
    """A callable the model can invoke, with its JSON-schema parameters."""

    name: str
    description: str
    parameters: dict
    fn: Callable[..., object]

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def leads_list(
    quadrant: str = "act_now",
    product: str = "personal",
    region: str | None = None,
    min_confidence: str | None = None,
    limit: int = 15,
) -> dict:
    """Ranked leads for a product/quadrant with the fields an RM needs to plan.

    Reads the precomputed lead_scores joined to display fields, no scoring here.
    """
    from aayai.serving.db import connect

    where = ["l.product = %s", "l.quadrant = %s"]
    params: list = [product, quadrant]
    if region:
        where.append("p.region = %s")
        params.append(region)
    if min_confidence and min_confidence in BANDS_ORDER:
        allowed = [
            b for b, r in BANDS_ORDER.items() if r >= BANDS_ORDER[min_confidence]
        ]
        where.append("p.confidence_band = ANY(%s)")
        params.append(allowed)
    params.append(int(limit))

    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT l.customer_id, p.name, p.region, p.confidence_band,
                       l.product, l.quadrant, l.product_intent, l.urgency,
                       l.best_repayable_amount, l.trigger
                FROM lead_scores l
                JOIN customer_profiles p USING (customer_id)
                WHERE {' AND '.join(where)}
                ORDER BY l.lead_score DESC, l.customer_id
                LIMIT %s
                """,
                params,
            )
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()
    for r in rows:
        r["best_repayable_amount"] = (
            float(r["best_repayable_amount"])
            if r["best_repayable_amount"] is not None
            else None
        )
        r["product_intent"] = float(r["product_intent"]) if r["product_intent"] else 0.0
    return {"count": len(rows), "leads": rows}


def intent_get(cust_id: str) -> dict:
    """Fused intent, quadrant, best-fit and the engagement strip for a customer."""
    from fastapi import HTTPException

    from aayai.api.intent import customer_intent
    from aayai.serving.db import connect

    conn = connect()
    try:
        return customer_intent(cust_id, conn=conn)
    except HTTPException as exc:
        return {"error": exc.detail}
    finally:
        conn.close()


def customer_get(cust_id: str | None = None, name: str | None = None) -> dict:
    """Resolve a customer by id or (partial) name; returns core profile fields."""
    from aayai.serving.db import connect

    if not cust_id and not name:
        return {"error": "provide cust_id or name"}
    conn = connect()
    try:
        with conn.cursor() as cur:
            if cust_id:
                cur.execute(
                    """
                    SELECT p.customer_id, p.name, p.region, p.confidence_band,
                           p.true_monthly_income, p.investable_surplus, p.total_emi
                    FROM customer_profiles p WHERE p.customer_id = %s
                    """,
                    (cust_id,),
                )
            else:
                cur.execute(
                    """
                    SELECT p.customer_id, p.name, p.region, p.confidence_band,
                           p.true_monthly_income, p.investable_surplus, p.total_emi
                    FROM customer_profiles p WHERE p.name ILIKE %s
                    ORDER BY p.customer_id LIMIT 5
                    """,
                    (f"%{name}%",),
                )
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()
    if not rows:
        return {"error": "no matching customer"}
    for r in rows:
        for k in ("true_monthly_income", "investable_surplus", "total_emi"):
            r[k] = float(r[k]) if r[k] is not None else None
    return {"matches": rows}


def calendar_find_slots(rm_id: str, window_days: int = 7, max_slots: int = 3) -> dict:
    """Free SLOT_MINUTES slots for an RM inside the next window_days."""
    from aayai.agent.scheduler import Window, propose_slots
    from aayai.serving import calendar_store
    from aayai.serving.db import connect

    now = datetime.now().astimezone()
    window = Window(
        signal="availability",
        why_now="RM availability lookup",
        opens=now,
        closes=now + timedelta(days=window_days),
        priority=9,
    )
    conn = connect()
    try:
        calendar_store.ensure_table(conn)
        busy = calendar_store.busy(conn, rm_id, window.opens, window.closes)
    finally:
        conn.close()
    slots = propose_slots(window, busy, max_slots=max_slots)
    return {"rm_id": rm_id, "slots": [s.isoformat() for s in slots]}


def calendar_create_event(
    rm_id: str,
    cust_id: str,
    interaction_id: int,
    starts_at: str,
    ends_at: str,
    title: str,
) -> dict:
    """Write a calendar event, ONLY for an interaction a human has approved."""
    from aayai.agent.guardrails import GuardrailError, check_approved
    from aayai.serving import calendar_store, interactions
    from aayai.serving.db import connect

    conn = connect()
    try:
        calendar_store.ensure_table(conn)
        row = interactions.get(conn, interaction_id)
        if row is None:
            return {"error": f"interaction {interaction_id} not found"}
        try:
            check_approved(row)
        except GuardrailError as exc:
            return {"error": str(exc)}
        try:
            return calendar_store.create_event(
                conn,
                rm_id=rm_id,
                cust_id=cust_id,
                interaction_id=interaction_id,
                starts_at=starts_at,
                ends_at=ends_at,
                title=title,
            )
        except PermissionError as exc:  # DB-side double check
            return {"error": str(exc)}
    finally:
        conn.close()


def interactions_upsert(
    cust_id: str,
    rm_id: str,
    interaction_id: int | None = None,
    product: str | None = None,
    scheduled_at: str | None = None,
    channel: str | None = None,
    status: str | None = None,
    why_now: str | None = None,
    signals: list | None = None,
    approach_notes: str | None = None,
    drafted_message: str | None = None,
    outcome: str | None = None,
    next_action: str | None = None,
) -> dict:
    """Create or update an interaction. Guardrails run here, not in the model:
    channel allow-list + frequency cap on create; state machine on update."""
    from aayai.agent.guardrails import (
        CONTACT_WINDOW_DAYS,
        GuardrailError,
        check_channel,
        check_frequency,
    )
    from aayai.serving import interactions
    from aayai.serving.db import connect

    conn = connect()
    try:
        interactions.ensure_table(conn)
        if interaction_id is None:
            try:
                if channel is not None:
                    check_channel(channel)
                recent = interactions.recent_contact_count(
                    conn, cust_id, CONTACT_WINDOW_DAYS
                )
                check_frequency(recent)
            except GuardrailError as exc:
                return {"error": str(exc)}
            return interactions.create(
                conn,
                cust_id=cust_id,
                rm_id=rm_id,
                product=product,
                scheduled_at=scheduled_at,
                channel=channel,
                why_now=why_now,
                signals=signals,
                approach_notes=approach_notes,
                drafted_message=drafted_message,
            )
        try:
            return interactions.update(
                conn,
                interaction_id,
                status=status,
                outcome=outcome,
                next_action=next_action,
                scheduled_at=scheduled_at,
                drafted_message=drafted_message,
                approach_notes=approach_notes,
            )
        except (interactions.IllegalTransition, KeyError) as exc:
            return {"error": str(exc)}
    finally:
        conn.close()


def interactions_list(
    cust_id: str | None = None,
    rm_id: str | None = None,
    status: str | None = None,
) -> dict:
    """Past + planned interactions (the agent reads outcomes to plan better)."""
    from aayai.serving import interactions
    from aayai.serving.db import connect

    conn = connect()
    try:
        interactions.ensure_table(conn)
        rows = interactions.list_interactions(
            conn, cust_id=cust_id, rm_id=rm_id, status=status
        )
    finally:
        conn.close()
    return {"count": len(rows), "interactions": rows}


def reminders_due(rm_id: str) -> dict:
    """Open interactions whose scheduled time has arrived for this RM."""
    from aayai.serving import interactions
    from aayai.serving.db import connect

    conn = connect()
    try:
        interactions.ensure_table(conn)
        rows = interactions.reminders_due(conn, rm_id)
    finally:
        conn.close()
    return {"count": len(rows), "due": rows}


LEADS_LIST = Tool(
    name="leads_list",
    description=(
        "List ranked loan leads for a product and capacity/intent quadrant, "
        "with each lead's name, region, confidence band, intent, urgency flag, "
        "illustrative best-repayable amount and a signal-backed trigger. Use "
        "this to fetch REAL leads; never invent customers."
    ),
    parameters={
        "type": "object",
        "properties": {
            "quadrant": {"type": "string", "enum": list(QUADRANTS)},
            "product": {"type": "string", "enum": list(PRODUCTS)},
            "region": {"type": "string", "description": "optional city/region filter"},
            "min_confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
        },
        "required": [],
    },
    fn=leads_list,
)

INTENT_GET = Tool(
    name="intent_get",
    description=(
        "Fused intent score, quadrant, best-fit product, best-repayable amount "
        "and the engagement strip (last event, days since a strong action) for "
        "one customer."
    ),
    parameters={
        "type": "object",
        "properties": {"cust_id": {"type": "string"}},
        "required": ["cust_id"],
    },
    fn=intent_get,
)

CUSTOMER_GET = Tool(
    name="customer_get",
    description="Resolve a customer by cust_id or partial name; core profile fields.",
    parameters={
        "type": "object",
        "properties": {
            "cust_id": {"type": "string"},
            "name": {"type": "string"},
        },
        "required": [],
    },
    fn=customer_get,
)

CALENDAR_FIND_SLOTS = Tool(
    name="calendar_find_slots",
    description="Free 30-minute slots for an RM within the next N days.",
    parameters={
        "type": "object",
        "properties": {
            "rm_id": {"type": "string"},
            "window_days": {"type": "integer", "minimum": 1, "maximum": 30},
            "max_slots": {"type": "integer", "minimum": 1, "maximum": 10},
        },
        "required": ["rm_id"],
    },
    fn=calendar_find_slots,
)

CALENDAR_CREATE_EVENT = Tool(
    name="calendar_create_event",
    description=(
        "Write a calendar event for an interaction. BLOCKED unless a human has "
        "approved the interaction (the tool returns an error otherwise)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "rm_id": {"type": "string"},
            "cust_id": {"type": "string"},
            "interaction_id": {"type": "integer"},
            "starts_at": {"type": "string", "description": "ISO timestamp"},
            "ends_at": {"type": "string", "description": "ISO timestamp"},
            "title": {"type": "string"},
        },
        "required": [
            "rm_id",
            "cust_id",
            "interaction_id",
            "starts_at",
            "ends_at",
            "title",
        ],
    },
    fn=calendar_create_event,
)

INTERACTIONS_UPSERT = Tool(
    name="interactions_upsert",
    description=(
        "Create a PLANNED outreach interaction (channel allow-list + frequency "
        "cap enforced) or update an existing one (status follows the state "
        "machine planned->contacted->responded->converted, dormant from any "
        "non-terminal state). why_now must cite a real signal."
    ),
    parameters={
        "type": "object",
        "properties": {
            "cust_id": {"type": "string"},
            "rm_id": {"type": "string"},
            "interaction_id": {"type": "integer"},
            "product": {"type": "string", "enum": list(PRODUCTS)},
            "scheduled_at": {"type": "string"},
            "channel": {"type": "string", "enum": ["phone", "email", "sms", "branch"]},
            "status": {
                "type": "string",
                "enum": ["planned", "contacted", "responded", "converted", "dormant"],
            },
            "why_now": {"type": "string"},
            "signals": {"type": "array", "items": {"type": "string"}},
            "approach_notes": {"type": "string"},
            "drafted_message": {"type": "string"},
            "outcome": {"type": "string"},
            "next_action": {"type": "string"},
        },
        "required": ["cust_id", "rm_id"],
    },
    fn=interactions_upsert,
)

INTERACTIONS_LIST = Tool(
    name="interactions_list",
    description="List past and planned interactions (read outcomes before planning).",
    parameters={
        "type": "object",
        "properties": {
            "cust_id": {"type": "string"},
            "rm_id": {"type": "string"},
            "status": {
                "type": "string",
                "enum": ["planned", "contacted", "responded", "converted", "dormant"],
            },
        },
        "required": [],
    },
    fn=interactions_list,
)

REMINDERS_DUE = Tool(
    name="reminders_due",
    description="Open interactions whose scheduled time has arrived for an RM.",
    parameters={
        "type": "object",
        "properties": {"rm_id": {"type": "string"}},
        "required": ["rm_id"],
    },
    fn=reminders_due,
)

ALL_TOOLS: tuple[Tool, ...] = (
    LEADS_LIST,
    INTENT_GET,
    CUSTOMER_GET,
    CALENDAR_FIND_SLOTS,
    CALENDAR_CREATE_EVENT,
    INTERACTIONS_UPSERT,
    INTERACTIONS_LIST,
    REMINDERS_DUE,
)
