"""Guardrails + scheduler rules, pure, offline, no LLM and no DB."""

from datetime import datetime, timedelta

import pytest

from aayai.agent import guardrails as g
from aayai.agent import scheduler as s

NOW = datetime(2026, 7, 6, 9, 0)


# guardrails
def test_channel_allow_list():
    g.check_channel("phone")  # allowed -> no raise
    with pytest.raises(g.GuardrailError, match="allow-list"):
        g.check_channel("whatsapp")


def test_frequency_cap():
    g.check_frequency(g.MAX_CONTACTS_PER_WINDOW - 1)  # under cap -> ok
    with pytest.raises(g.GuardrailError, match="frequency cap"):
        g.check_frequency(g.MAX_CONTACTS_PER_WINDOW)


def test_approval_gate():
    with pytest.raises(g.GuardrailError, match="approval"):
        g.check_approved({"approved_at": None})
    g.check_approved({"approved_at": "2026-07-06T10:00:00"})  # approved -> ok


def test_message_contract():
    good = (
        "Hi Meera, your car loan EMI just finished. That frees about Rs 12,000 "
        "a month. Would a quick call tomorrow suit you?"
    )
    assert g.validate_message(good).ok

    assert "em dash" in " ".join(g.validate_message("Great news — call me?").problems)
    long = "word " * 60 + "call me?"
    assert any("too long" in p for p in g.validate_message(long).problems)
    assert any(
        "no call to action" in p for p in g.validate_message("We have loans.").problems
    )
    two_ctas = "Call me today? Also reply to this SMS and book a visit?"
    assert any("more than one" in p for p in g.validate_message(two_ctas).problems)


# scheduler windows
def test_emi_ending_opens_named_window():
    (w,) = [
        w
        for w in s.timing_windows(
            now=NOW, quadrant="exclude", emi_ending=True, ending_stream="hdfc auto"
        )
        if w.signal == "emi_ending"
    ]
    assert "hdfc auto" in w.why_now
    assert w.closes - w.opens == timedelta(days=s.EMI_ENDING_WINDOW_DAYS)


def test_recent_strong_event_is_top_priority():
    ws = s.timing_windows(
        now=NOW,
        quadrant="act_now",
        emi_ending=True,
        days_since_strong_event=2,
        last_event_type="eligibility_check",
    )
    assert ws[0].signal == "recent_strong_event"  # warm intent outranks all
    assert "eligibility_check" in ws[0].why_now and "2 day" in ws[0].why_now


def test_quadrant_cadence_windows():
    act = s.timing_windows(now=NOW, quadrant="act_now")
    assert act and act[0].signal == "quadrant_act_now"
    assert act[0].closes - act[0].opens == timedelta(days=s.ACT_NOW_WINDOW_DAYS)

    nurture = s.timing_windows(now=NOW, quadrant="nurture")
    assert nurture[0].signal == "quadrant_nurture"
    assert nurture[0].opens == NOW + timedelta(days=s.NURTURE_SPACING_DAYS)

    assert s.timing_windows(now=NOW, quadrant="exclude") == []  # no signal, no window


def test_every_window_cites_a_signal():
    for w in s.timing_windows(
        now=NOW, quadrant="act_now", emi_ending=True, days_since_strong_event=1
    ):
        assert w.signal and w.why_now  # why_now always traces to a named signal


# slot proposals
def test_slots_avoid_busy_and_stay_in_hours():
    w = s.timing_windows(now=NOW, quadrant="act_now")[0]
    busy = [
        (NOW.replace(hour=10, minute=0), NOW.replace(hour=11, minute=0)),
    ]
    slots = s.propose_slots(w, busy, max_slots=3)
    assert len(slots) == 3
    for slot in slots:
        assert s.WORKING_HOURS[0] <= slot.time() < s.WORKING_HOURS[1]
        for b0, b1 in busy:
            assert not (b0 <= slot < b1)
    assert slots[0] >= NOW.replace(hour=11, minute=0)  # first free after the meeting
