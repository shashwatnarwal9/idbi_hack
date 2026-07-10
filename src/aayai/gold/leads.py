"""Lead scoring and quadrants: pure, I/O-free, all thresholds named constants.

lead_score = eligibility_gate(0/1)
             × per_product_intent (0-1)
             × prospect_score (0-1)
             × normalized(suggested_amount) (0-1)
             × urgency_boost
             × band_discount

A low confidence band applies a discount, never an exclusion. Urgency lifts a
lead when the customer's EMI is ending or they took a strong action recently
(enquiry / eligibility check). The quadrant is capacity (prospect score) ×
intent. Analyst/app activity NEVER feeds this, mark-contacted lives in its own
firewalled table and changes no score.
"""

from __future__ import annotations

# Urgency multiplier (>1) for a time-sensitive lead; and how recent a strong
# event must be to count as urgent.
URGENCY_BOOST = 1.25
RECENT_EVENT_DAYS = 14
STRONG_RECENT_EVENTS = ("enquiry_submitted", "eligibility_check")

# A weak-confidence estimate is discounted, not dropped.
LOW_BAND_DISCOUNT = 0.8

# Quadrant thresholds: capacity on the prospect score [0, 1], intent on [0, 100].
CAPACITY_THRESHOLD = 0.5
INTENT_THRESHOLD = 50.0


def _clamp01(value: float | None) -> float:
    if value is None:
        return 0.0
    return min(max(float(value), 0.0), 1.0)


def quadrant(prospect_score: float | None, intent: float) -> str:
    """capacity × intent → act_now / nurture / downsell / exclude."""
    high_capacity = (prospect_score or 0.0) >= CAPACITY_THRESHOLD
    high_intent = intent >= INTENT_THRESHOLD
    if high_capacity and high_intent:
        return "act_now"
    if high_intent and not high_capacity:
        return "downsell"  # wants it, limited capacity → smaller product
    if high_capacity and not high_intent:
        return "nurture"  # can afford, not yet interested
    return "exclude"


def urgency(
    emi_ending: bool, days_since_strong_event: float | None
) -> tuple[float, bool]:
    """Return (boost, is_urgent). Urgent when EMI is ending or a strong recent event."""
    recent = (
        days_since_strong_event is not None
        and days_since_strong_event <= RECENT_EVENT_DAYS
    )
    is_urgent = bool(emi_ending) or recent
    return (URGENCY_BOOST if is_urgent else 1.0), is_urgent


def lead_score(
    *,
    eligible: bool,
    product_intent: float,
    prospect_score: float | None,
    suggested_amount_norm: float,
    confidence_band: str,
    emi_ending: bool = False,
    days_since_strong_event: float | None = None,
) -> dict:
    """Score one customer × product lead and label its quadrant.

    An ineligible product zeroes the score (gate = 0). The result carries the
    urgency and band-discount factors so the UI can explain the ranking.
    """
    gate = 1.0 if eligible else 0.0
    boost, is_urgent = urgency(emi_ending, days_since_strong_event)
    discount = LOW_BAND_DISCOUNT if confidence_band == "low" else 1.0
    score = (
        gate
        * _clamp01(product_intent / 100.0)
        * _clamp01(prospect_score)
        * _clamp01(suggested_amount_norm)
        * boost
        * discount
    )
    return {
        "lead_score": round(score, 6),
        "eligible": eligible,
        "quadrant": quadrant(prospect_score, product_intent),
        "urgency": is_urgent,
        "urgency_boost": boost,
        "band_discount": discount,
    }
