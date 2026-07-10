"""Outreach endpoints: today's queue, status updates, and the approval gate.

Backs the Outreach screen. Reads/writes the interactions workflow table only,
never a score. Status changes follow the state machine; approval is an explicit
human action recorded with who approved. Planning (the agent proposing new
interactions) can be triggered from the UI via POST /outreach/generate, which
runs the planner in a BACKGROUND THREAD (GLM-5.2 is slow) and reports progress
through GET /outreach/generate/status. The same work also runs offline via
`python -m aayai.agent.run_planner`.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from aayai.api.deps import get_conn
from aayai.serving import interactions as ix

router = APIRouter(prefix="/outreach", tags=["outreach"])

DEFAULT_RM = "rm-1"  # single-RM demo; a real deployment keys this off auth
PRODUCTS = ("personal", "auto", "home", "mortgage")
QUADRANTS = ("act_now", "nurture", "downsell", "exclude")


@router.get("/queue")
def queue(rm_id: str = DEFAULT_RM, conn=Depends(get_conn)) -> dict:
    """Today's work: due reminders plus every open planned/contacted row."""
    ix.ensure_table(conn)
    due = ix.reminders_due(conn, rm_id)
    due_ids = {d["id"] for d in due}
    open_rows = [
        r
        for r in ix.list_interactions(conn, rm_id=rm_id)
        if r["status"] in ("planned", "contacted") and r["id"] not in due_ids
    ]
    return {"rm_id": rm_id, "due": due, "upcoming": open_rows}


@router.get("/interactions")
def list_all(
    cust_id: str | None = None,
    rm_id: str | None = None,
    status: str | None = None,
    conn=Depends(get_conn),
) -> list[dict]:
    ix.ensure_table(conn)
    if status is not None and status not in ix.STATUSES:
        raise HTTPException(422, f"status must be one of {sorted(ix.STATUSES)}")
    return ix.list_interactions(conn, cust_id=cust_id, rm_id=rm_id, status=status)


class StatusUpdate(BaseModel):
    status: str
    outcome: str | None = None
    next_action: str | None = None


@router.post("/{interaction_id}/status")
def set_status(interaction_id: int, body: StatusUpdate, conn=Depends(get_conn)) -> dict:
    """Move an interaction along the state machine (422 on illegal moves)."""
    ix.ensure_table(conn)
    try:
        return ix.update(
            conn,
            interaction_id,
            status=body.status,
            outcome=body.outcome,
            next_action=body.next_action,
        )
    except ix.IllegalTransition as exc:
        raise HTTPException(422, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


class ApproveRequest(BaseModel):
    approved_by: str = "rm-1"


@router.post("/{interaction_id}/approve")
def approve(interaction_id: int, body: ApproveRequest, conn=Depends(get_conn)) -> dict:
    """Human approval, unlocks calendar writes / sending for this row."""
    ix.ensure_table(conn)
    try:
        return ix.approve(conn, interaction_id, body.approved_by)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


# background "generate outreach" job
# One in-process job at a time. State is read by GET /generate/status while the
# planner (GLM-5.2, minutes per lead) runs in a daemon thread off the request.
_JOB_LOCK = threading.Lock()
_JOB: dict = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "planned": 0,
    "error": None,
}


def _run_planner(rm_id: str, product: str, quadrant: str, top: int) -> int:
    """Plan one product's leads; indirection so tests can patch out the LLM."""
    from aayai.agent.run_planner import refresh

    return refresh(rm_id, product, quadrant, top)


def _generate_worker(rm_id: str, quadrant: str, products: list[str], top: int) -> None:
    planned = 0
    error = None
    try:
        for product in products:
            planned += _run_planner(rm_id, product, quadrant, top)
            with _JOB_LOCK:
                _JOB["planned"] = planned
    except Exception as exc:  # LLM/DB outage is reported, not crashed
        error = f"{exc.__class__.__name__}: {exc}"
    finally:
        with _JOB_LOCK:
            _JOB["running"] = False
            _JOB["finished_at"] = datetime.now(timezone.utc).isoformat()
            _JOB["planned"] = planned
            _JOB["error"] = error


class GenerateRequest(BaseModel):
    rm_id: str = DEFAULT_RM
    quadrant: str = "act_now"
    products: list[str] | None = None
    top: int = 3


@router.post("/generate")
def generate(body: GenerateRequest) -> dict:
    """Start the planner in the background for the top leads (idempotent while running).

    Returns immediately; poll GET /generate/status for progress. A human still
    approves every proposed interaction before anything is committed.
    """
    if body.quadrant not in QUADRANTS:
        raise HTTPException(422, "unknown quadrant")
    products = [p for p in (body.products or PRODUCTS) if p in PRODUCTS] or list(
        PRODUCTS
    )
    with _JOB_LOCK:
        if _JOB["running"]:
            return {"status": "already_running", **_JOB}
        _JOB.update(
            running=True,
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=None,
            planned=0,
            error=None,
        )
    threading.Thread(
        target=_generate_worker,
        args=(body.rm_id, body.quadrant, products, body.top),
        daemon=True,
    ).start()
    return {"status": "started", **_JOB}


@router.get("/generate/status")
def generate_status() -> dict:
    with _JOB_LOCK:
        return dict(_JOB)
