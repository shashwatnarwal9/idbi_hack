"""Intent fusion + lead scoring: the 90/10 split, degradation, quadrants, firewall."""

from pathlib import Path

import pytest

from aayai.gold import intent, leads

# Full behavioural signals (all strong) and engagement signals (all strong).
STRONG_B = {
    "emi_regularity": 1.0,
    "surplus_trend": 1.0,
    "is_renter": 1.0,
    "sip_discipline": 1.0,
    "emi_ending": 1.0,
    "income_growth": 1.0,
}
STRONG_E = {
    "recency": 1.0,
    "frequency": 1.0,
    "strongest_tier": 1.0,
    "offer_click_rate": 1.0,
    "product_affinity": {"personal": 1.0, "auto": 1.0, "home": 1.0, "mortgage": 1.0},
}

# a profile that clears every eligibility gate
STRONG_PROFILE = dict(
    true_monthly_income=100000.0,
    income_volatility=0.05,
    total_emi=10000.0,
    months_history=18,
    confidence_band="high",
    investable_surplus=40000.0,
    prospect_score=0.95,
)


def test_fusion_weights_are_exactly_90_10():
    assert intent.BEHAVIORAL_WEIGHT == 0.90
    assert intent.ENGAGEMENT_WEIGHT == 0.10
    assert intent.BEHAVIORAL_WEIGHT + intent.ENGAGEMENT_WEIGHT == pytest.approx(1.0)


def test_signal_blocks_sum_to_100():
    assert sum(intent.BEHAVIORAL_SIGNAL_WEIGHTS.values()) == 100
    assert sum(intent.ENGAGEMENT_SIGNAL_WEIGHTS.values()) == 100


def test_behavioral_and_engagement_scores_hit_100_when_all_signals_max():
    b, comp = intent.behavioral_score(STRONG_B)
    assert b == pytest.approx(100.0)
    assert sum(c["contribution"] for c in comp) == pytest.approx(100.0)
    e, _ = intent.engagement_score(STRONG_E)
    assert e == pytest.approx(100.0)


def test_fuse_applies_the_10_percent_engagement_weight():
    # B=80, E=100, has_events -> 0.9*80 + 0.1*100 = 82.0
    fused, used, split = intent.fuse_intent(80.0, 100.0, has_events=True)
    assert used is True
    assert fused == pytest.approx(82.0)
    contrib = {s["part"]: s["contribution"] for s in split}
    assert contrib["behavioral"] == pytest.approx(72.0)
    assert contrib["engagement"] == pytest.approx(10.0)


def test_no_events_degrades_to_behavioral_only():
    fused, used, split = intent.fuse_intent(80.0, 100.0, has_events=False)
    assert used is False
    assert fused == pytest.approx(80.0)  # engagement ignored entirely
    assert len(split) == 1 and split[0]["part"] == "behavioral"


def test_score_customer_without_events_sets_flag_and_null_engagement():
    out = intent.score_customer(
        behavioural_signals=STRONG_B,
        engagement_signals=None,
        has_events=False,
        **STRONG_PROFILE,
    )
    assert out["engagement_used"] is False
    assert out["engagement_score"] is None
    assert out["intent"] == pytest.approx(out["behavioral_score"])


def test_score_customer_with_events_uses_90_10():
    out = intent.score_customer(
        behavioural_signals=STRONG_B,
        engagement_signals=STRONG_E,
        has_events=True,
        **STRONG_PROFILE,
    )
    assert out["engagement_used"] is True
    expected = 0.9 * out["behavioral_score"] + 0.1 * out["engagement_score"]
    assert out["intent"] == pytest.approx(expected, abs=0.05)


def test_best_fit_only_among_eligible():
    # renter signal makes home the top behavioural product…
    signals = {**{k: 0.0 for k in STRONG_B}, "is_renter": 1.0}
    pi = intent.per_product_intent(signals, None, has_events=False)
    assert pi["home"] == pytest.approx(100.0)
    # …but if only personal is eligible, best fit must be personal
    fit, reason = intent.best_fit(pi, eligible={"personal"})
    assert fit == "personal" and reason is None
    # no eligible product -> None with a reason
    none_fit, none_reason = intent.best_fit(pi, eligible=set())
    assert none_fit is None and none_reason


def test_best_repayable_is_illustrative_and_capped():
    r = intent.best_repayable(
        "personal",
        true_monthly_income=100000.0,
        total_emi=10000.0,
        investable_surplus=40000.0,
    )
    assert r["affordable_emi"] > 0 and r["max_principal"] > 0
    assert r["annual_rate_pct"] == intent.PRODUCT_DEFAULT_RATES["personal"]
    assert "illustrative" in r["disclaimer"]


def test_lead_quadrants():
    assert leads.quadrant(0.9, 80) == "act_now"
    assert leads.quadrant(0.2, 80) == "downsell"
    assert leads.quadrant(0.9, 10) == "nurture"
    assert leads.quadrant(0.2, 10) == "exclude"


def test_lead_urgency_and_discount():
    boost, urgent = leads.urgency(emi_ending=True, days_since_strong_event=None)
    assert urgent and boost == leads.URGENCY_BOOST
    boost2, urgent2 = leads.urgency(emi_ending=False, days_since_strong_event=5)
    assert urgent2 and boost2 == leads.URGENCY_BOOST
    _, calm = leads.urgency(emi_ending=False, days_since_strong_event=30)
    assert not calm


def test_firewall_no_ground_truth_or_analyst_activity_in_scoring_inputs():
    # The scoring layer must never read a "_" ground-truth column nor any
    # analyst/app-activity table (reviews, shares, mark-contacted).
    # Unambiguous ground-truth columns ("_"-prefixed) and analyst-activity
    # tables. NB: the model's prospect score (p_good_prospect) is a legitimate
    # input, only the ground-truth label (_is_good_prospect) is forbidden.
    forbidden = (
        "_true",
        "_is_income",
        "_intent_propensity",
        "_is_good_prospect",
        "review_status",
        "share_log",
    )
    root = Path(intent.__file__).parent
    for module in ("intent.py", "leads.py", "behaviour.py", "engagement.py"):
        path = root / module
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in src, f"{module} references forbidden `{token}`"


def test_lead_score_gate_zeroes_and_low_band_discounts_not_excludes():
    ineligible = leads.lead_score(
        eligible=False,
        product_intent=90,
        prospect_score=0.9,
        suggested_amount_norm=1.0,
        confidence_band="high",
    )
    assert ineligible["lead_score"] == 0.0
    low = leads.lead_score(
        eligible=True,
        product_intent=90,
        prospect_score=0.9,
        suggested_amount_norm=1.0,
        confidence_band="low",
    )
    high = leads.lead_score(
        eligible=True,
        product_intent=90,
        prospect_score=0.9,
        suggested_amount_norm=1.0,
        confidence_band="high",
    )
    assert 0 < low["lead_score"] < high["lead_score"]  # discounted, not excluded
    assert low["band_discount"] == leads.LOW_BAND_DISCOUNT
