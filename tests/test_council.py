"""Council routing + anonymisation + synthesis, proven offline with a fake LLM."""

import random

import pytest

from aayai.agent import council


class FakeLLM:
    """Deterministic completer that records every call."""

    def __init__(self):
        self.calls = []  # (system, user)

    def complete(self, system, user, temperature=None):
        self.calls.append((system, user))
        if "CHAIRMAN" in system:
            return (
                "They agree on timing. The contrarian dissents on channel and "
                "wins: phone beats email here (overruling the majority).\n"
                "FIRST ACTION: RM calls tomorrow at 11am\n"
                "MESSAGE: Hi Meera, your car EMI just ended. Want a quick call "
                "about putting that amount to work?"
            )
        if "reviewing five anonymous" in system:
            return "Strongest: B. Blind spot: cost. All missed: consent."
        if "outreach strategist" in system:
            return (
                "Lead with personal, phone, warm tone.\n"
                "FIRST ACTION: call this week\n"
                "MESSAGE: Hi, your EMI ended. Shall we talk this week?"
            )
        return f"[{system[:24]}] opinion"


HIGH_STAKES_LEAD = {
    "customer_id": "CUST01101",
    "name": "Meera Chopra",
    "quadrant": "act_now",
    "confidence_band": "high",
    "best_repayable_amount": 500_000,
}
CHEAP_LEAD = {
    "customer_id": "CUST01002",
    "name": "Arjun Rao",
    "quadrant": "nurture",
    "confidence_band": "high",
    "best_repayable_amount": 300_000,
}


def test_stakes_routing():
    assert council.is_high_stakes(HIGH_STAKES_LEAD)  # act_now
    assert council.is_high_stakes(
        {**CHEAP_LEAD, "best_repayable_amount": council.HIGH_STAKES_AMOUNT}
    )  # large amount
    assert council.is_high_stakes({**CHEAP_LEAD, "confidence_band": "low"})  # ambiguous
    assert not council.is_high_stakes(CHEAP_LEAD)


def test_cheap_lead_skips_council_single_call():
    llm = FakeLLM()
    res = council.run_strategist(CHEAP_LEAD, "nurture cadence", llm, parallel=False)
    assert res.used_council is False
    assert res.calls_made == 1
    assert len(llm.calls) == 1  # exactly ONE model call, no five-lens fan-out
    assert res.first_action == "call this week"
    assert res.drafted_message.startswith("Hi, your EMI ended")


def test_high_stakes_runs_full_council():
    llm = FakeLLM()
    res = council.run_strategist(
        HIGH_STAKES_LEAD,
        "EMI ending (signal: emi_ending)",
        llm,
        rng=random.Random(7),
        parallel=False,
    )
    assert res.used_council is True
    assert res.calls_made == 11 and len(llm.calls) == 11  # 5 + 5 + 1
    assert set(res.opinions) == set(council.LENSES)
    # chairman synthesis parsed
    assert res.first_action == "RM calls tomorrow at 11am"
    assert "quick call" in res.drafted_message
    # the chairman can overrule the majority (present in synthesis)
    assert "overruling the majority" in res.approach


def test_peer_review_is_anonymised():
    llm = FakeLLM()
    res = council.run_strategist(
        HIGH_STAKES_LEAD, "why", llm, rng=random.Random(3), parallel=False
    )
    # labels A-E map 1:1 onto the five lenses, in shuffled order
    assert sorted(res.label_map.keys()) == list("ABCDE")
    assert set(res.label_map.values()) == set(council.LENSES)
    # reviewers see ONLY the anonymous labels, never the lens names
    review_inputs = [u for s, u in llm.calls if "reviewing five anonymous" in s]
    assert review_inputs
    for text in review_inputs:
        assert "OPINION A:" in text
        for lens in council.LENSES:
            assert f"OPINION {lens}" not in text


class FlakyLLM(FakeLLM):
    """Fails for the named lenses (simulating shed 5xx requests)."""

    def __init__(self, fail_for):
        super().__init__()
        self.fail_for = fail_for

    def complete(self, system, user, temperature=None):
        for lens, prompt in council.LENSES.items():
            if system == prompt and lens in self.fail_for:
                raise RuntimeError("504 shed")
        return super().complete(system, user, temperature)


def test_council_survives_one_lost_advisor():
    llm = FlakyLLM(fail_for={"expansionist"})
    res = council.run_strategist(
        HIGH_STAKES_LEAD, "why", llm, rng=random.Random(1), parallel=False
    )
    assert res.used_council is True
    assert set(res.opinions) == set(council.LENSES) - {"expansionist"}
    assert res.first_action  # chairman still synthesised


def test_council_below_quorum_raises():
    llm = FlakyLLM(fail_for={"contrarian", "expansionist", "outsider"})
    with pytest.raises(council.CouncilUnavailable):
        council.run_strategist(
            HIGH_STAKES_LEAD, "why", llm, rng=random.Random(1), parallel=False
        )


def test_lead_brief_carries_signal_not_invention():
    llm = FakeLLM()
    council.run_strategist(CHEAP_LEAD, "quadrant_nurture cadence", llm, parallel=False)
    _, user = llm.calls[0]
    assert "WHY NOW (signal-backed): quadrant_nurture cadence" in user
    assert "do not invent" in user
