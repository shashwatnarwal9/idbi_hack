"""Engagement signal summarisation from events (pure, DB-free)."""

from datetime import datetime

from aayai.gold.engagement import STRONG_EVENTS, recency_decay, summarize_events

NOW = datetime(2026, 6, 28)


def _ev(days_ago, etype, product="", session="S1"):
    return {
        "timestamp": datetime(2026, 6, 28)
        - __import__("datetime").timedelta(days=days_ago),
        "event_type": etype,
        "product": product,
        "session_id": session,
    }


def test_no_events_has_events_false():
    assert summarize_events([], NOW) == {"has_events": False}


def test_recency_decay_halves_every_halflife():
    assert recency_decay(0) == 1.0
    assert recency_decay(30) == 0.5
    assert recency_decay(60) == 0.25
    assert recency_decay(None) == 0.0


def test_summary_signals_are_in_range_and_flagged():
    events = [
        _ev(1, "eligibility_check", "home"),
        _ev(2, "product_page_view", "home"),
        _ev(3, "offer_email_sent", "home"),
        _ev(3, "offer_email_click", "home"),
        _ev(80, "app_open"),
    ]
    s = summarize_events(events, NOW)
    assert s["has_events"] is True
    assert 0.0 <= s["recency"] <= 1.0
    assert 0.0 <= s["strongest_tier"] <= 1.0
    assert (
        s["strongest_tier"] == 1.0 or s["strongest_tier"] == 0.8
    )  # eligibility_check tier
    # affinity is a share per product, summing to 1 over product events
    assert abs(sum(s["product_affinity"].values()) - 1.0) < 1e-6
    assert s["product_affinity"]["home"] > 0
    # offer click rate = clicks/sends = 1/1
    assert s["offer_click_rate"] == 1.0
    # a strong recent event drives urgency downstream
    assert s["days_since_strong_event"] == 1


def test_strong_events_match_lead_urgency_set():
    # engagement's STRONG_EVENTS must align with the lead urgency trigger set
    from aayai.gold.leads import STRONG_RECENT_EVENTS

    assert set(STRONG_EVENTS) == set(STRONG_RECENT_EVENTS)
