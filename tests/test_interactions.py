"""Interactions state machine + reminders + frequency counting (needs store)."""

import pytest

from aayai.serving import interactions as ix

try:
    from aayai.serving.db import connect

    _conn = connect()
    ix.ensure_table(_conn)
except Exception:
    _conn = None

needs_store = pytest.mark.skipif(
    _conn is None, reason="serving postgres not reachable; start it via docker compose"
)


def _new(**over):
    defaults = dict(
        cust_id="TEST-IX-CUST",
        rm_id="TEST-IX-RM",
        product="personal",
        channel="phone",
        why_now="EMI ending in 12 days (signal: emi_ending)",
        signals=["emi_ending"],
    )
    defaults.update(over)
    return ix.create(_conn, **defaults)


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    if _conn is not None:
        with _conn, _conn.cursor() as cur:
            cur.execute("DELETE FROM interactions WHERE cust_id LIKE 'TEST-IX-%'")


@needs_store
def test_create_starts_planned_and_unapproved():
    row = _new()
    assert row["status"] == "planned"
    assert row["approved_at"] is None
    assert row["why_now"].startswith("EMI ending")
    assert row["signals"] == ["emi_ending"]


@needs_store
def test_legal_transition_chain_to_converted():
    row = _new()
    row = ix.update(_conn, row["id"], status="contacted")
    row = ix.update(_conn, row["id"], status="responded")
    row = ix.update(_conn, row["id"], status="converted", outcome="took the loan")
    assert row["status"] == "converted"
    assert row["outcome"] == "took the loan"


@needs_store
def test_illegal_transitions_raise():
    row = _new()
    with pytest.raises(ix.IllegalTransition):
        ix.update(_conn, row["id"], status="converted")  # planned -/-> converted
    row = ix.update(_conn, row["id"], status="dormant")
    with pytest.raises(ix.IllegalTransition):
        ix.update(_conn, row["id"], status="contacted")  # dormant is terminal


@needs_store
def test_outcome_written_feeds_next_suggestion():
    # an outcome + next_action recorded on one pass is what the next
    # planning pass reads back (list by customer)
    row = _new()
    ix.update(_conn, row["id"], status="contacted")
    ix.update(
        _conn,
        row["id"],
        status="responded",
        outcome="asked to call back after salary credit",
        next_action="call first week of next month",
    )
    latest = ix.list_interactions(_conn, cust_id="TEST-IX-CUST")[-1]
    assert latest["next_action"] == "call first week of next month"


@needs_store
def test_approval_gate_and_reminders_due():
    row = _new(scheduled_at="2020-01-01T09:00:00+00:00")  # in the past -> due
    assert row["approved_at"] is None
    approved = ix.approve(_conn, row["id"], approved_by="rm-9")
    assert approved["approved_at"] is not None and approved["approved_by"] == "rm-9"
    due = ix.reminders_due(_conn, "TEST-IX-RM")
    assert any(d["id"] == row["id"] for d in due)
    # terminal rows never appear as reminders
    ix.update(_conn, row["id"], status="dormant")
    assert not any(d["id"] == row["id"] for d in ix.reminders_due(_conn, "TEST-IX-RM"))


@needs_store
def test_recent_contact_count_for_frequency_cap():
    _new()
    _new()
    assert ix.recent_contact_count(_conn, "TEST-IX-CUST", window_days=30) == 2
    # dormant rows don't count against the cap
    row = _new()
    ix.update(_conn, row["id"], status="dormant")
    assert ix.recent_contact_count(_conn, "TEST-IX-CUST", window_days=30) == 2
