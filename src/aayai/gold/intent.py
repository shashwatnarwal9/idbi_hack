"""Intent fusion: pure, I/O-free scoring over behavioural + engagement signals.

Two independent 0-100 scores are fused into one intent score:

  * B (behavioural): a weighted sum of transaction-derived signals (A4). It is
    the whole story when a customer has no marketing events.
  * E (engagement): a weighted sum of event-derived signals (A5).

Fused intent = BEHAVIORAL_WEIGHT·B + ENGAGEMENT_WEIGHT·E, and the two weights are
exactly 0.90 / 0.10 (asserted to sum to 1.0). When a customer has no events,
intent degrades cleanly to B alone with engagement_used=False, engagement is
never fabricated.

Firewall: nothing here reads a "_" ground-truth column or any analyst/app
activity table. Behavioural signals come from the customer's own transactions;
engagement signals from their own product events. Every threshold, weight and
default rate is a named constant, and every score returns a composition
breakdown (each signal's contribution) for the UI.
"""

from __future__ import annotations

from aayai.gold.loan_calc import affordable_emi, max_principal
from aayai.gold.loan_products import PRODUCTS_BY_KEY, evaluate_all

# Fusion weights, EVENTS ARE EXACTLY 10%
BEHAVIORAL_WEIGHT = 0.90
ENGAGEMENT_WEIGHT = 0.10
assert abs(BEHAVIORAL_WEIGHT + ENGAGEMENT_WEIGHT - 1.0) < 1e-9, "weights must sum to 1"

# Per-signal weights (each block sums to 100 so a score lands on 0-100)
BEHAVIORAL_SIGNAL_WEIGHTS: dict[str, float] = {
    "emi_regularity": 25,
    "surplus_trend": 20,
    "is_renter": 20,
    "sip_discipline": 15,
    "emi_ending": 20,
}
ENGAGEMENT_SIGNAL_WEIGHTS: dict[str, float] = {
    "recency": 30,
    "frequency": 25,
    "strongest_tier": 30,
    "offer_click_rate": 15,
}

# Default annual rates for the "best repayable" illustration (defined once here;
# the frontend calculator carries the same defaults).
PRODUCT_DEFAULT_RATES: dict[str, float] = {
    "personal": 11.0,
    "auto": 9.5,
    "home": 8.5,
    "mortgage": 8.5,
}


def _clamp01(value: float | None) -> float:
    if value is None:
        return 0.0
    return min(max(float(value), 0.0), 1.0)


def _weighted_score(
    signals: dict, weights: dict[str, float]
) -> tuple[float, list[dict]]:
    """Weighted sum of 0-1 signals onto a 0-100 score, with a contribution list."""
    score = 0.0
    composition: list[dict] = []
    for name, weight in weights.items():
        value = _clamp01(signals.get(name))
        contribution = value * weight  # weights sum to 100 => score in [0, 100]
        score += contribution
        composition.append(
            {
                "signal": name,
                "value": round(value, 4),
                "weight": weight,
                "contribution": round(contribution, 2),
            }
        )
    return round(score, 2), composition


def behavioral_score(signals: dict) -> tuple[float, list[dict]]:
    """B in [0, 100] from transaction-derived signals, plus its composition."""
    return _weighted_score(signals, BEHAVIORAL_SIGNAL_WEIGHTS)


def engagement_score(signals: dict) -> tuple[float, list[dict]]:
    """E in [0, 100] from event-derived signals, plus its composition."""
    return _weighted_score(signals, ENGAGEMENT_SIGNAL_WEIGHTS)


def fuse_intent(
    behavioral: float, engagement: float, has_events: bool
) -> tuple[float, bool, list[dict]]:
    """Fuse B and E at the fixed 90/10 split, or fall back to B with no events.

    Returns (intent, engagement_used, split) where split shows how much each of
    behavioural / engagement contributed to the final score.
    """
    if has_events:
        intent = BEHAVIORAL_WEIGHT * behavioral + ENGAGEMENT_WEIGHT * engagement
        split = [
            {
                "part": "behavioral",
                "weight": BEHAVIORAL_WEIGHT,
                "score": round(behavioral, 2),
                "contribution": round(BEHAVIORAL_WEIGHT * behavioral, 2),
            },
            {
                "part": "engagement",
                "weight": ENGAGEMENT_WEIGHT,
                "score": round(engagement, 2),
                "contribution": round(ENGAGEMENT_WEIGHT * engagement, 2),
            },
        ]
        return round(intent, 2), True, split
    # no events: behavioural is the whole score, engagement never fabricated
    split = [
        {
            "part": "behavioral",
            "weight": 1.0,
            "score": round(behavioral, 2),
            "contribution": round(behavioral, 2),
        }
    ]
    return round(behavioral, 2), False, split


def per_product_behavioral(signals: dict) -> dict[str, float]:
    """Behavioural intent vote per product (0-1) from transaction signals.

    Triggers: renters lean home; a customer whose EMI is ending has personal
    headroom; steady SIP discipline suits the long mortgage horizon; a clean EMI
    record plus income growth points at auto/personal.
    """
    renter = _clamp01(signals.get("is_renter"))
    emi_ending = _clamp01(signals.get("emi_ending"))
    sip = _clamp01(signals.get("sip_discipline"))
    regularity = _clamp01(signals.get("emi_regularity"))
    income_growth = _clamp01(signals.get("income_growth"))
    return {
        "personal": _clamp01(0.6 * emi_ending + 0.4 * income_growth),
        "auto": _clamp01(0.6 * regularity + 0.4 * income_growth),
        "home": renter,
        "mortgage": _clamp01(0.6 * sip + 0.4 * regularity),
    }


def per_product_intent(
    signals: dict,
    event_affinity: dict | None,
    has_events: bool,
) -> dict[str, float]:
    """Per-product intent (0-100). Event affinity votes at the same 10% weight."""
    behavioural = per_product_behavioral(signals)
    out: dict[str, float] = {}
    for key in PRODUCTS_BY_KEY:
        b100 = behavioural.get(key, 0.0) * 100
        if has_events and event_affinity is not None:
            e100 = _clamp01((event_affinity or {}).get(key)) * 100
            out[key] = round(BEHAVIORAL_WEIGHT * b100 + ENGAGEMENT_WEIGHT * e100, 2)
        else:
            out[key] = round(b100, 2)
    return out


def eligible_products(
    *,
    true_monthly_income: float,
    income_volatility: float,
    total_emi: float,
    months_history: int,
    confidence_band: str,
    investable_surplus: float,
    prospect_score: float | None,
) -> set[str]:
    """The product keys whose existing eligibility gate passes (reuses rules)."""
    results = evaluate_all(
        true_monthly_income=true_monthly_income,
        income_volatility=income_volatility,
        total_emi=total_emi,
        months_history=months_history,
        confidence_band=confidence_band,
        investable_surplus=investable_surplus,
        prospect_score=prospect_score,
    )
    return {r["product"] for r in results if r["status"] == "eligible"}


def best_fit(
    product_intent: dict[str, float], eligible: set[str]
) -> tuple[str | None, str | None]:
    """argmax per-product intent among eligible products (None with a reason)."""
    candidates = {k: v for k, v in product_intent.items() if k in eligible}
    if not candidates:
        return None, "no product passes the eligibility gate for this customer"
    key = max(candidates, key=lambda k: (candidates[k], k))
    return key, None


def best_repayable(
    product_key: str,
    *,
    true_monthly_income: float,
    total_emi: float,
    investable_surplus: float,
) -> dict:
    """Illustrative affordable EMI + max principal for a product (not an offer).

    Uses the FOIR/surplus-capped affordable EMI and the max principal at the
    product's default rate and standard tenure.
    """
    product = PRODUCTS_BY_KEY[product_key]
    rate = PRODUCT_DEFAULT_RATES[product_key]
    tenure = product.standard_tenure_months
    headroom, cap = affordable_emi(true_monthly_income, total_emi, investable_surplus)
    principal = max_principal(headroom, rate, tenure)
    return {
        "product": product_key,
        "affordable_emi": round(headroom, 2),
        "binding_cap": cap,
        "annual_rate_pct": rate,
        "tenure_months": tenure,
        "max_principal": round(principal, 2),
        "disclaimer": "illustrative, not an offer",
    }


def score_customer(
    *,
    behavioural_signals: dict,
    engagement_signals: dict | None,
    has_events: bool,
    true_monthly_income: float,
    income_volatility: float,
    total_emi: float,
    months_history: int,
    confidence_band: str,
    investable_surplus: float,
    prospect_score: float | None = None,
) -> dict:
    """Full intent payload for one customer (fused score → best repayable)."""
    b, b_comp = behavioral_score(behavioural_signals)
    if has_events and engagement_signals is not None:
        e, e_comp = engagement_score(engagement_signals)
        affinity = engagement_signals.get("product_affinity")
    else:
        e, e_comp, affinity = 0.0, [], None

    intent, engagement_used, split = fuse_intent(b, e, has_events)
    product_intent = per_product_intent(behavioural_signals, affinity, engagement_used)
    eligible = eligible_products(
        true_monthly_income=true_monthly_income,
        income_volatility=income_volatility,
        total_emi=total_emi,
        months_history=months_history,
        confidence_band=confidence_band,
        investable_surplus=investable_surplus,
        prospect_score=prospect_score,
    )
    fit, fit_reason = best_fit(product_intent, eligible)
    repayable = (
        best_repayable(
            fit,
            true_monthly_income=true_monthly_income,
            total_emi=total_emi,
            investable_surplus=investable_surplus,
        )
        if fit is not None
        else None
    )
    return {
        "intent": intent,
        "behavioral_score": b,
        "engagement_score": e if engagement_used else None,
        "engagement_used": engagement_used,
        "composition": {
            "split": split,
            "behavioral": b_comp,
            "engagement": e_comp,
        },
        "per_product_intent": product_intent,
        "eligible_products": sorted(eligible),
        "best_fit_product": fit,
        "best_fit_reason": fit_reason,
        "best_repayable": repayable,
    }
