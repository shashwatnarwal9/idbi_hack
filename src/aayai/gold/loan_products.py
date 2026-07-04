"""Per-loan-type eligibility rules over already-derived gold features.

A pure rules layer — no new model, no new pipeline stage. Every threshold is a
named constant, tuned as a reasonable starting point against our synthetic
archetypes. Eligibility uses only gold-derived fields (income, income
volatility, DTI, months of history, confidence band); no "_" ground-truth column
is ever read, consistent with the pipeline firewall.

Why the thresholds differ by product:
  * Personal loan  — short, unsecured, surplus-driven. The most permissive: a
    moderate DTI and 6 months of history are enough because the tenure is short
    and the exposure small.
  * Auto loan      — secured by the vehicle, medium tenure (~5yr). Slightly more
    DTI headroom than personal (the asset backs it) but tighter volatility and a
    little more history, since repayment runs longer.
  * Home loan      — large, long tenure (~15yr). Needs a long, low-volatility
    income record and high confidence: a lender is underwriting many years of
    steady repayment, so a thin or noisy history is disqualifying.
  * Mortgage loan  — the largest, longest exposure (~20yr). Strictest DTI and
    volatility and the same long-history / high-confidence bar as home, because
    the repayment horizon is longest and the amount typically highest.

The prospect-score floor (min_prospect_score) is a fifth criterion, tiered the
same way. It asks a holistic question the individual ratios do not: is this a
sound overall candidate? Short loans lean on immediate affordability, so the
floor is off (personal) or low (auto); long-tenure loans depend on the customer
staying sound for many years, so home/mortgage carry a real floor. The score is
partly derived from income/volatility/DTI, so the floor mostly reinforces the
ratio checks — its value is catching customers who clear each ratio yet read
poorly overall.
"""

from __future__ import annotations

from dataclasses import dataclass

# Share of investable surplus a suggested EMI may consume. Illustrative only —
# a conservative half keeps headroom for the buffer the surplus already nets out.
MAX_EMI_TO_SURPLUS_RATIO = 0.5

# confidence bands as an order so "at least medium" is comparable
CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


@dataclass(frozen=True)
class LoanProduct:
    key: str
    label: str
    max_dti: float
    max_income_volatility: float
    min_months_history: int
    min_confidence: str
    standard_tenure_months: int  # stated approximation, not an amortization engine
    min_prospect_score: float | None  # holistic floor; None = no floor for this product


PERSONAL_LOAN = LoanProduct(
    "personal",
    "Personal Loan",
    max_dti=0.45,
    max_income_volatility=0.35,
    min_months_history=6,
    min_confidence="medium",
    standard_tenure_months=36,
    min_prospect_score=None,  # short tenure, affordability-driven: no holistic floor
)
AUTO_LOAN = LoanProduct(
    "auto",
    "Auto Loan",
    max_dti=0.50,
    max_income_volatility=0.30,
    min_months_history=9,
    min_confidence="medium",
    standard_tenure_months=60,
    # secured + medium tenure: affordability-driven like personal, so no holistic
    # floor. A 0.35 floor was rejected in tuning: the prospect score is strongly
    # bimodal, so any mid-range floor excluded ~half of otherwise-affordable
    # applicants (mostly stable low-income salaried) on an investment-prospect
    # signal, not creditworthiness. The floor stays on the long-tenure products.
    min_prospect_score=None,
)
HOME_LOAN = LoanProduct(
    "home",
    "Home Loan",
    max_dti=0.40,
    max_income_volatility=0.15,
    min_months_history=18,
    min_confidence="high",
    standard_tenure_months=180,
    min_prospect_score=0.55,
)
MORTGAGE_LOAN = LoanProduct(
    "mortgage",
    "Mortgage Loan",
    max_dti=0.35,
    max_income_volatility=0.12,
    min_months_history=18,
    min_confidence="high",
    standard_tenure_months=240,
    min_prospect_score=0.60,
)

PRODUCTS: tuple[LoanProduct, ...] = (
    PERSONAL_LOAN,
    AUTO_LOAN,
    HOME_LOAN,
    MORTGAGE_LOAN,
)

PRODUCTS_BY_KEY: dict[str, LoanProduct] = {p.key: p for p in PRODUCTS}


def suggested_amount(product: LoanProduct, investable_surplus: float) -> float:
    """Illustrative loan size: affordable EMI x standard tenure (not an offer)."""
    max_emi = max(investable_surplus, 0.0) * MAX_EMI_TO_SURPLUS_RATIO
    return round(max_emi * product.standard_tenure_months, -3)


def evaluate_product(
    product: LoanProduct,
    *,
    dti: float,
    income_volatility: float,
    months_history: int,
    confidence_band: str,
    investable_surplus: float,
    prospect_score: float | None = None,
) -> dict:
    """Eligibility for one product from gold features plus the prospect score.

    Every failing criterion is collected (history, confidence, volatility, DTI,
    then the prospect-score floor), so the reason lists all of them rather than
    only the first. The prospect floor is evaluated last and, when it is the sole
    failure, its reason says so explicitly. It is skipped when the product has no
    floor or the score is unavailable (e.g. a batch scored without the model).

    Args:
        prospect_score: model probability in [0, 1]; None means "not scored".

    Returns:
        Dict with status, a semicolon-joined reason (None if eligible) and a
        suggested amount (None if not eligible).
    """
    reasons: list[str] = []
    if months_history < product.min_months_history:
        reasons.append(
            f"needs {product.min_months_history} months history, "
            f"has {int(months_history)}"
        )
    if (
        CONFIDENCE_RANK.get(confidence_band, 0)
        < CONFIDENCE_RANK[product.min_confidence]
    ):
        reasons.append(
            f"needs {product.min_confidence} confidence, has {confidence_band}"
        )
    if income_volatility > product.max_income_volatility:
        reasons.append(
            f"income too volatile ({income_volatility:.2f} > "
            f"{product.max_income_volatility:.2f} max)"
        )
    if dti > product.max_dti:
        reasons.append(
            f"debt-to-income too high ({dti:.0%} > {product.max_dti:.0%} max)"
        )
    if (
        product.min_prospect_score is not None
        and prospect_score is not None
        and prospect_score < product.min_prospect_score
    ):
        if reasons:
            reasons.append(
                f"overall prospect score ({prospect_score:.2f}) is below the "
                f"{product.min_prospect_score:.2f} threshold for {product.label}"
            )
        else:
            reasons.append(
                f"Overall prospect score ({prospect_score:.2f}) is below the "
                f"{product.min_prospect_score:.2f} threshold required for "
                f"{product.label}, despite meeting the individual income/debt criteria"
            )

    if reasons:
        return {
            "product": product.key,
            "label": product.label,
            "status": "not_eligible",
            "reason": "; ".join(reasons),
            "suggested_amount": None,
        }
    return {
        "product": product.key,
        "label": product.label,
        "status": "eligible",
        "reason": None,
        "suggested_amount": suggested_amount(product, investable_surplus),
    }


def evaluate_all(
    *,
    true_monthly_income: float,
    income_volatility: float,
    total_emi: float,
    months_history: int,
    confidence_band: str,
    investable_surplus: float,
    prospect_score: float | None = None,
) -> list[dict]:
    """Evaluate all four products for one customer's gold row.

    dti (debt-to-income) is derived here as total_emi / true_monthly_income so
    callers pass raw gold fields; a non-positive income yields dti that fails
    every threshold. prospect_score is threaded through to the per-product
    prospect floor; None leaves that criterion unevaluated.
    """
    dti = total_emi / true_monthly_income if true_monthly_income > 0 else float("inf")
    return [
        evaluate_product(
            p,
            dti=dti,
            income_volatility=income_volatility,
            months_history=months_history,
            confidence_band=confidence_band,
            investable_surplus=investable_surplus,
            prospect_score=prospect_score,
        )
        for p in PRODUCTS
    ]
