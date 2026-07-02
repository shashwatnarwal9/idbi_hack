"""आय·AI Silver evaluation — the ONLY place (so far) allowed to read "_" columns.

Compares the DERIVED category against _true_category and prints:
  * overall category accuracy (the headline number),
  * per-category precision / recall / support,
  * the salary / gig_income / p2p_in confusion matrix (income vs non-income
    credits is the hard part of आय·AI),
  * derived is_income vs _is_income.

Ground truth uses a richer taxonomy than silver's fixed 16 categories, so it is
FOLDED onto the silver taxonomy first (e.g. PENSION->salary, DINING->food).
The fold expresses what the right answer is in silver's vocabulary; the rules
never see it.
"""
from __future__ import annotations

from collections import defaultdict

import duckdb

from aayai.silver.transform import TXN_READ

SILVER_CATEGORIES = ["salary", "gig_income", "business_income", "interest",
                     "rent", "emi", "sip", "utility", "groceries", "food",
                     "fuel", "shopping", "entertainment", "p2p_in", "p2p_out",
                     "atm"]

# ground truth -> silver taxonomy (evaluation-only fold)
TRUTH_TO_SILVER = {
    "SALARY": "salary", "PENSION": "salary",
    "GIG_PAYOUT": "gig_income",
    "BUSINESS_INCOME": "business_income", "FREELANCE": "business_income",
    "INTEREST": "interest",
    "RENT_INCOME": "rent", "RENT_PAID": "rent",
    "EMI": "emi",
    "SIP_INVESTMENT": "sip",
    "INSURANCE": "utility", "UTILITIES": "utility", "MOBILE_RECHARGE": "utility",
    "GROCERIES": "groceries",
    "DINING": "food",
    "SHOPPING": "shopping", "MEDICAL": "shopping",
    "FUEL": "fuel",
    "ENTERTAINMENT": "entertainment",
    "REFUND": "p2p_in", "SELF_TRANSFER_IN": "p2p_in", "P2P_IN": "p2p_in",
    "FD_MATURITY": "p2p_in",
    "CASH_WITHDRAWAL": "atm",
    "P2P_OUT": "p2p_out", "BUSINESS_EXPENSE": "p2p_out",
}


def evaluate(con: duckdb.DuckDBPyConnection | None = None) -> dict:
    """Returns {'overall': float, 'per_category': {cat: (prec, rec, support)},
    'confusion3': {(truth, derived): n}, 'is_income_acc': float, 'total': int}."""
    con = con or duckdb.connect()
    pairs = con.execute(
        f"SELECT _true_category, category, count(*) FROM {TXN_READ} GROUP BY 1, 2"
    ).fetchall()

    total = correct = 0
    tp: dict = defaultdict(int)
    truth_n: dict = defaultdict(int)     # support per expected category
    derived_n: dict = defaultdict(int)
    confusion3: dict = defaultdict(int)
    focus = ("salary", "gig_income", "p2p_in")
    for truth_raw, derived, n in pairs:
        expected = TRUTH_TO_SILVER[truth_raw]
        total += n
        truth_n[expected] += n
        derived_n[derived] += n
        if expected == derived:
            correct += n
            tp[expected] += n
        if expected in focus or derived in focus:
            confusion3[(expected if expected in focus else "other",
                        derived if derived in focus else "other")] += n

    per_category = {}
    for cat in SILVER_CATEGORIES:
        prec = tp[cat] / derived_n[cat] if derived_n[cat] else float("nan")
        rec = tp[cat] / truth_n[cat] if truth_n[cat] else float("nan")
        per_category[cat] = (prec, rec, truth_n[cat])

    n_income_ok = con.execute(
        f"SELECT count(*) FROM {TXN_READ} WHERE is_income = _is_income").fetchone()[0]
    return {"overall": correct / total, "total": total, "correct": correct,
            "per_category": per_category, "confusion3": dict(confusion3),
            "is_income_acc": n_income_ok / total}


def main() -> None:
    m = evaluate()
    print(f"[silver eval] overall category accuracy: {m['overall']:.2%} "
          f"({m['correct']:,} / {m['total']:,})")

    print(f"[silver eval] per-category precision/recall "
          f"(truth folded onto silver taxonomy):")
    print(f"  {'category':<16} {'precision':>9} {'recall':>9} {'support':>9}")
    weak = []
    for cat, (prec, rec, support) in m["per_category"].items():
        print(f"  {cat:<16} {prec:>9.3f} {rec:>9.3f} {support:>9,}")
        if prec < 0.85 or rec < 0.85:
            weak.append(cat)

    print("[silver eval] salary / gig_income / p2p_in confusion "
          "(rows = truth, cols = derived):")
    labels = ["salary", "gig_income", "p2p_in", "other"]
    print(f"  {'':<12}" + "".join(f"{c:>12}" for c in labels))
    for t in labels:
        row = "".join(f"{m['confusion3'].get((t, d), 0):>12,}" for d in labels)
        print(f"  {t:<12}{row}")

    print(f"[silver eval] derived is_income vs _is_income: {m['is_income_acc']:.2%}")
    print("[silver eval] note: rent credits are real income in ground truth but "
          "the fixed taxonomy scores them as 'rent' (not income) by design.")
    print(f"[silver eval] categories below 85% precision or recall: "
          f"{', '.join(weak) if weak else 'none'}")


if __name__ == "__main__":
    main()
