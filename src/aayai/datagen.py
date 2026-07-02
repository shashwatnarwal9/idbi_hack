"""Synthetic raw-data generator (pipeline stage 0).

Writes the two raw inputs the pipeline starts from:
  data/raw/transactions.csv  - messy Indian bank narrations (UPI/NEFT/IMPS/ACH/
                               POS/ATM), one row per transaction
  data/raw/customers.csv     - one row per customer with DECLARED profile fields

Ground truth: columns prefixed "_" (_true_category, _is_income,
_true_monthly_income, _is_good_prospect, _true_occupation) are for EVALUATION
ONLY. No transform or model may ever read them as an input; the pipeline
derives its own labels and is scored against these.

Deterministic: the same --seed always produces the same CSVs. Stdlib only.
Replace these CSVs with real exports of the same schema and every later stage
runs unchanged.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from datetime import date, datetime

from aayai.paths import RAW_DIR

# ---------------------------------------------------------------- constants

MONTHS = [
    (y, m) for y in (2025, 2026) for m in range(1, 13) if not (y == 2026 and m > 6)
]  # 2025-01 .. 2026-06
N_MONTHS = len(MONTHS)
MONTH_ABBR = [
    "",
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
]

ARCHETYPES = ["SALARIED", "SALARIED_PLUS", "GIG", "BUSINESS", "PENSIONER"]
ARCHETYPE_WEIGHTS = [0.40, 0.15, 0.15, 0.15, 0.15]

INCOME_CATEGORIES = {
    "SALARY",
    "PENSION",
    "BUSINESS_INCOME",
    "GIG_PAYOUT",
    "RENT_INCOME",
    "FREELANCE",
    "INTEREST",
}

FIRST = [
    "Aarav",
    "Vivaan",
    "Aditya",
    "Ananya",
    "Diya",
    "Ishaan",
    "Kavya",
    "Rohan",
    "Priya",
    "Neha",
    "Arjun",
    "Sneha",
    "Rahul",
    "Pooja",
    "Amit",
    "Sunita",
    "Vikram",
    "Meera",
    "Karan",
    "Divya",
]
LAST = [
    "Sharma",
    "Verma",
    "Gupta",
    "Iyer",
    "Nair",
    "Patel",
    "Reddy",
    "Singh",
    "Khan",
    "Das",
    "Joshi",
    "Kulkarni",
    "Mehta",
    "Chopra",
    "Banerjee",
    "Rao",
]
CITIES = [
    "Mumbai",
    "Delhi",
    "Bengaluru",
    "Hyderabad",
    "Chennai",
    "Kolkata",
    "Pune",
    "Ahmedabad",
    "Jaipur",
    "Lucknow",
    "Indore",
    "Kochi",
]
EMPLOYERS = [
    "ACME TECHNOLOGIES PVT LTD",
    "BHARAT INFOTECH LTD",
    "SUNRISE TEXTILES",
    "NATIONAL RETAIL CORP",
    "MEDIPLUS HEALTHCARE",
    "OMEGA CONSULTING",
    "TATA STEEL LTD",
    "INFOSYS LTD",
    "GODREJ AND BOYCE",
    "ZENITH PHARMA",
]
GIG_PLATFORMS = [
    "SWIGGY",
    "ZOMATO",
    "UBER INDIA",
    "OLA",
    "RAPIDO",
    "URBANCOMPANY",
    "BLINKIT",
    "ZEPTO",
]
SUPPLIERS = [
    "MAHALAXMI TRADERS",
    "SHREE ENTERPRISES",
    "KM DISTRIBUTORS",
    "ROYAL AGENCIES",
    "GANESH WHOLESALE",
    "APEX SUPPLIES",
]
GROCERY = [
    "DMART",
    "BIGBASKET",
    "RELIANCE FRESH",
    "MORE SUPERMARKET",
    "LOCAL KIRANA STORE",
    "JIOMART",
]
DINING = [
    "SWIGGY",
    "ZOMATO",
    "DOMINOS",
    "MCDONALDS",
    "HALDIRAMS",
    "CAFE COFFEE DAY",
    "BARBEQUE NATION",
]
SHOPPING = ["AMAZON", "FLIPKART", "MYNTRA", "AJIO", "CROMA", "LIFESTYLE"]
FUEL = ["INDIAN OIL", "HP PETROL PUMP", "BHARAT PETROLEUM", "SHELL"]
MEDICAL = ["APOLLO PHARMACY", "MEDPLUS", "FORTIS HOSPITAL", "1MG"]
ENTERTAINMENT = ["NETFLIX", "HOTSTAR", "SPOTIFY", "BOOKMYSHOW", "PVR CINEMAS"]
UTILITIES = ["MSEB", "TATA POWER", "BESCOM", "ADANI ELECTRICITY"]
TELCOS = ["JIO RECHARGE", "AIRTEL PREPAID", "VI POSTPAID"]
INSURERS = ["LIC OF INDIA", "HDFC ERGO", "STAR HEALTH", "ICICI PRULIFE"]
AMCS = ["SBI MUTUAL FUND", "HDFC AMC", "AXIS MF", "UTI AMC"]
LENDERS = ["BAJAJ FINANCE LTD", "HDFC BANK LOAN", "TATA CAPITAL", "HOME CREDIT"]
BANKS = ["HDFC", "ICIC", "SBIN", "UTIB", "KKBK", "PUNB", "IBKL"]
UPI_PSPS = ["okicici", "oksbi", "okhdfcbank", "ybl", "paytm", "apl", "ibl"]
SAL_WORDS = ["SALARY", "SAL", "SALRY", "SALARY CREDIT", "SAL CR", "MONTHLY SAL"]

DECLARED_OCC = {
    "SALARIED": ["SALARIED", "SERVICE", "PRIVATE JOB"],
    "SALARIED_PLUS": ["SALARIED", "SERVICE", "PRIVATE JOB"],
    "GIG": ["SELF EMPLOYED", "DRIVER", "DELIVERY PARTNER", "OTHERS"],
    "BUSINESS": ["BUSINESS", "TRADER", "SHOP OWNER"],
    "PENSIONER": ["RETIRED", "PENSIONER"],
}

# --------------------------------------------------------- narration pieces


def _rrn(rng: random.Random) -> str:
    return str(rng.randrange(10**11, 10**12))


def _ref(rng: random.Random) -> str:
    return "N" + str(rng.randrange(10**8, 10**9))


def _person(rng: random.Random) -> str:
    return f"{rng.choice(FIRST)} {rng.choice(LAST)}".upper()


def _handle(rng: random.Random, name: str) -> str:
    return (
        name.split()[0].lower()
        + str(rng.randrange(10, 999))
        + "@"
        + rng.choice(UPI_PSPS)
    )


def _card(rng: random.Random) -> str:
    return (
        "4"
        + str(rng.randrange(10**4, 10**5))
        + "XXXXXX"
        + str(rng.randrange(1000, 9999))
    )


def _mangle(rng: random.Random, s: str) -> str:
    """Random case/whitespace mess so narrations are realistically dirty."""
    r = rng.random()
    if r < 0.20:
        s = s.lower()
    elif r < 0.30:
        s = s.title()
    if rng.random() < 0.12:
        s = s.replace(" ", "  ", 1)
    if rng.random() < 0.06:
        s = " " + s
    return s


def narration(rng: random.Random, cat: str, p: dict, y: int, m: int) -> str:
    """Build one messy narration string for a category. p is the customer profile."""
    mn, yy = MONTH_ABBR[m], str(y)[2:]
    bank = rng.choice(BANKS)
    if cat == "SALARY":
        s = rng.choice(
            [
                f"NEFT-{bank}000{rng.randrange(1000, 9999)}-{p['employer']}-{rng.choice(SAL_WORDS)} {mn} {yy}-{_ref(rng)}",
                f"{p['employer']} {rng.choice(SAL_WORDS)} {mn}{yy}",
                f"BY TRANSFER-NEFT-{p['employer']}-{rng.choice(SAL_WORDS)}-{_ref(rng)}",
            ]
        )
    elif cat == "PENSION":
        s = rng.choice(
            [
                f"PENSION-{mn}{yy}-CPAO TREASURY-{_ref(rng)}",
                f"CENTRAL PENSION CR {mn} {yy}",
            ]
        )
    elif cat == "BUSINESS_INCOME":
        payer = _person(rng)
        s = rng.choice(
            [
                f"UPI/P2M/{_rrn(rng)}/{payer}/{_handle(rng, payer)}/PAYMENT",
                f"NEFT-{bank}000{rng.randrange(1000, 9999)}-{payer}-INV {rng.randrange(100, 9999)}-{_ref(rng)}",
                f"IMPS-P2A-{_rrn(rng)}-{payer}-BILL PAYMENT",
            ]
        )
    elif cat == "GIG_PAYOUT":
        pf = rng.choice(p["platforms"])
        s = rng.choice(
            [
                f"IMPS/P2A/{_rrn(rng)}/{pf} PAYOUT/{_ref(rng)}",
                f"UPI/{_rrn(rng)}/{pf} PARTNER PAYOUT/WEEKLY SETTLEMENT",
                f"NEFT-{bank}000{rng.randrange(1000, 9999)}-{pf}-PAYOUT-{_ref(rng)}",
            ]
        )
    elif cat == "RENT_INCOME":
        s = rng.choice(
            [
                f"UPI/{_rrn(rng)}/{p['tenant']}/{_handle(rng, p['tenant'])}/RENT {mn}",
                f"IMPS-P2A-{_rrn(rng)}-RENT FOR {mn}-{p['tenant']}",
            ]
        )
    elif cat == "FREELANCE":
        client = _person(rng)
        s = rng.choice(
            [
                f"NEFT-{bank}000{rng.randrange(1000, 9999)}-{client}-PROJECT PAYMENT-{_ref(rng)}",
                f"UPI/{_rrn(rng)}/{client}/{_handle(rng, client)}/FREELANCE WORK",
            ]
        )
    elif cat == "INTEREST":
        s = rng.choice(
            [
                f"INT.PD:01-{m:02d}-{y} TO 30-{m:02d}-{y}",
                f"SB INTEREST {mn} {yy}",
                "CREDIT INTEREST CAPITALISED",
            ]
        )
    elif cat == "FD_MATURITY":
        s = f"FD MATURITY PROCEEDS {rng.randrange(10**7, 10**8)}"
    elif cat == "REFUND":
        s = rng.choice(
            [
                f"REFUND/{rng.choice(SHOPPING)}/ORDER {rng.randrange(10**6, 10**7)}",
                f"UPI/REV/{_rrn(rng)}/{rng.choice(SHOPPING)}/REFUND",
            ]
        )
    elif cat == "SELF_TRANSFER_IN":
        s = rng.choice(
            [
                f"NEFT-{bank}000{rng.randrange(1000, 9999)}-{p['name'].upper()}-SELF-{_ref(rng)}",
                f"IMPS FROM OWN AC {_rrn(rng)}",
            ]
        )
    elif cat == "P2P_IN":
        who = _person(rng)
        s = f"UPI/{_rrn(rng)}/{who}/{_handle(rng, who)}/PAYMENT"
    elif cat == "RENT_PAID":
        s = rng.choice(
            [
                f"UPI/{_rrn(rng)}/{p['landlord']}/{_handle(rng, p['landlord'])}/RENT {mn}",
                f"IMPS-P2A-{_rrn(rng)}-{p['landlord']}-HOUSE RENT",
            ]
        )
    elif cat == "EMI":
        s = rng.choice(
            [
                f"ACH-D-{p['lender']}-EMI{rng.randrange(10**5, 10**6)}",
                f"NACH/{p['lender']}/LOAN EMI/{_ref(rng)}",
            ]
        )
    elif cat == "SIP_INVESTMENT":
        s = rng.choice(
            [
                f"ACH-D-{p['amc']}-SIP",
                f"NACH/{p['amc']}/SIP {rng.randrange(1, 29):02d}{m:02d}{yy}",
            ]
        )
    elif cat == "INSURANCE":
        s = f"ACH-D-{p['insurer']}-PREMIUM {rng.randrange(10**7, 10**8)}"
    elif cat == "UTILITIES":
        u = rng.choice(UTILITIES)
        s = rng.choice(
            [
                f"BBPS/{u}/BILL PAY/{rng.randrange(10**6, 10**7)}",
                f"UPI/{_rrn(rng)}/{u}/ELECTRICITY BILL {mn}",
            ]
        )
    elif cat == "MOBILE_RECHARGE":
        s = f"UPI/{_rrn(rng)}/{rng.choice(TELCOS)}/RECHARGE"
    elif cat == "GROCERIES":
        st = rng.choice(GROCERY)
        s = rng.choice(
            [
                f"UPI/P2M/{_rrn(rng)}/{st}/{_handle(rng, st)}/PAYMENT",
                f"POS {_card(rng)} {st}",
            ]
        )
    elif cat == "DINING":
        s = f"UPI/P2M/{_rrn(rng)}/{rng.choice(DINING)}/PAYMENT FROM PH"
    elif cat == "SHOPPING":
        st = rng.choice(SHOPPING)
        s = rng.choice(
            [
                f"UPI/P2M/{_rrn(rng)}/{st}/{_handle(rng, st)}/SHOPPING",
                f"POS {_card(rng)} {st}",
            ]
        )
    elif cat == "FUEL":
        s = f"POS {_card(rng)} {rng.choice(FUEL)} {p['city'].upper()}"
    elif cat == "MEDICAL":
        s = f"UPI/P2M/{_rrn(rng)}/{rng.choice(MEDICAL)}/PAYMENT"
    elif cat == "ENTERTAINMENT":
        s = f"UPI/{_rrn(rng)}/{rng.choice(ENTERTAINMENT)}/SUBSCRIPTION"
    elif cat == "CASH_WITHDRAWAL":
        s = rng.choice(
            [
                f"ATM-CASH-NFS/{bank} ATM/{p['city'].upper()}/{rng.randrange(10**5, 10**6)}",
                f"ATM WDL {_rrn(rng)}",
            ]
        )
    elif cat == "P2P_OUT":
        who = _person(rng)
        s = f"UPI/{_rrn(rng)}/{who}/{_handle(rng, who)}/SENT"
    elif cat == "BUSINESS_EXPENSE":
        s = rng.choice(
            [
                f"NEFT-{bank}000{rng.randrange(1000, 9999)}-{rng.choice(SUPPLIERS)}-PAYMENT-{_ref(rng)}",
                f"RTGS-{rng.choice(SUPPLIERS)}-INVOICE {rng.randrange(1000, 99999)}",
            ]
        )
    else:
        raise ValueError(f"no narration template for category {cat}")
    return _mangle(rng, s)


# ------------------------------------------------------------- profile


def make_profile(rng: random.Random, idx: int) -> dict:
    """Draw one customer: archetype, income parameters and fixed commitments."""
    arch = rng.choices(ARCHETYPES, ARCHETYPE_WEIGHTS)[0]
    p = {
        "customer_id": f"CUST{idx:05d}",
        "name": f"{rng.choice(FIRST)} {rng.choice(LAST)}",
        "age": rng.randint(61, 79) if arch == "PENSIONER" else rng.randint(23, 58),
        "city": rng.choice(CITIES),
        "archetype": arch,
        "employer": rng.choice(EMPLOYERS),
        "platforms": rng.sample(GIG_PLATFORMS, 2),
        "landlord": _person(rng),
        "tenant": _person(rng),
        "lender": rng.choice(LENDERS),
        "amc": rng.choice(AMCS),
        "insurer": rng.choice(INSURERS),
        "salary_day": rng.randint(1, 5),
        "open_date": date(
            rng.randint(2012, 2024), rng.randint(1, 12), rng.randint(1, 28)
        ),
        "opening_balance": round(rng.uniform(10_000, 400_000), 2),
    }
    # income parameters -> exp_income used to size the spending budget
    if arch in ("SALARIED", "SALARIED_PLUS"):
        p["salary"] = round(
            math.exp(rng.uniform(math.log(28_000), math.log(200_000))), -3
        )
        p["exp_income"] = p["salary"]
        if arch == "SALARIED_PLUS":
            p["rent_in"] = round(rng.uniform(8_000, 35_000), -3)
            p["freelance_target"] = (
                round(rng.uniform(5_000, 25_000), -3) if rng.random() < 0.6 else 0
            )
            p["exp_income"] += p["rent_in"] + p["freelance_target"]
    elif arch == "GIG":
        p["gig_target"] = round(rng.uniform(15_000, 60_000), -3)
        p["exp_income"] = p["gig_target"]
    elif arch == "BUSINESS":
        p["margin"] = rng.uniform(0.15, 0.35)
        p["margin_income"] = round(
            math.exp(rng.uniform(math.log(35_000), math.log(250_000))), -3
        )
        p["exp_income"] = p["margin_income"]
    else:  # PENSIONER
        p["pension"] = round(rng.uniform(15_000, 45_000), -3)
        p["fd_interest"] = round(rng.uniform(3_000, 20_000), -2)
        p["exp_income"] = p["pension"] + p["fd_interest"] / 3
    # fixed monthly commitments
    p["spend_ratio"] = rng.uniform(
        *{
            "SALARIED": (0.50, 0.85),
            "SALARIED_PLUS": (0.45, 0.75),
            "GIG": (0.60, 0.95),
            "BUSINESS": (0.50, 0.90),
            "PENSIONER": (0.50, 0.90),
        }[arch]
    )
    renter_p = {
        "SALARIED": 0.55,
        "SALARIED_PLUS": 0.20,
        "GIG": 0.55,
        "BUSINESS": 0.35,
        "PENSIONER": 0.10,
    }[arch]
    p["rent_paid"] = (
        round(rng.uniform(0.18, 0.28) * p["exp_income"], -2)
        if rng.random() < renter_p
        else 0
    )
    p["emi"] = (
        round(rng.uniform(0.08, 0.20) * p["exp_income"], -2)
        if rng.random() < (0.15 if arch == "PENSIONER" else 0.45)
        else 0
    )
    p["sip"] = (
        round(rng.uniform(0.05, 0.15) * p["exp_income"], -2)
        if rng.random() < 0.45
        else 0
    )
    p["premium"] = round(rng.uniform(500, 3000), -1) if rng.random() < 0.40 else 0
    return p


# ------------------------------------------------------- event generation


def _ts(
    rng: random.Random,
    y: int,
    m: int,
    day: int | None = None,
    hours: tuple[int, int] = (7, 22),
) -> datetime:
    return datetime(
        y,
        m,
        day or rng.randint(1, 28),
        rng.randint(*hours),
        rng.randint(0, 59),
        rng.randint(0, 59),
    )


def _split(rng: random.Random, total: float, k: int, lo: float = 50.0) -> list[float]:
    """Split total into k positive parts with +-40% jitter per part."""
    if k <= 0 or total <= 0:
        return []
    return [max(lo, round(total / k * rng.uniform(0.6, 1.4), 2)) for _ in range(k)]


def month_events(rng: random.Random, p: dict, y: int, m: int) -> list[tuple]:
    """All (datetime, category, txn_type, amount) events for one customer-month."""
    ev: list[tuple] = []
    arch = p["archetype"]

    # --- income credits
    if arch in ("SALARIED", "SALARIED_PLUS"):
        ev.append(
            (
                _ts(
                    rng,
                    y,
                    m,
                    min(28, p["salary_day"] + rng.randint(-1, 1)) or 1,
                    (9, 19),
                ),
                "SALARY",
                "CREDIT",
                p["salary"],
            )
        )
    if arch == "SALARIED_PLUS":
        ev.append(
            (_ts(rng, y, m, rng.randint(2, 7)), "RENT_INCOME", "CREDIT", p["rent_in"])
        )
        if p["freelance_target"]:
            for amt in _split(rng, p["freelance_target"], rng.randint(0, 2), lo=1500):
                ev.append((_ts(rng, y, m), "FREELANCE", "CREDIT", amt))
    if arch == "GIG":
        for amt in _split(rng, p["gig_target"], rng.randint(6, 14), lo=300):
            ev.append((_ts(rng, y, m), "GIG_PAYOUT", "CREDIT", amt))
    if arch == "BUSINESS":
        receipts = _split(
            rng, p["margin_income"] / p["margin"], rng.randint(8, 25), lo=500
        )
        for amt in receipts:
            ev.append((_ts(rng, y, m), "BUSINESS_INCOME", "CREDIT", amt))
        expense_total = sum(receipts) * (1 - p["margin"]) * rng.uniform(0.95, 1.05)
        for amt in _split(rng, expense_total, rng.randint(2, 6), lo=1000):
            ev.append(
                (_ts(rng, y, m, None, (10, 18)), "BUSINESS_EXPENSE", "DEBIT", amt)
            )
    if arch == "PENSIONER":
        ev.append(
            (
                _ts(rng, y, m, rng.randint(1, 2), (9, 12)),
                "PENSION",
                "CREDIT",
                p["pension"],
            )
        )
        if m in (3, 6, 9, 12):
            ev.append(
                (
                    _ts(rng, y, m, 28),
                    "INTEREST",
                    "CREDIT",
                    round(p["fd_interest"] * rng.uniform(0.9, 1.1), 2),
                )
            )
    if m in (3, 6, 9, 12):  # savings-account interest for everyone
        ev.append(
            (_ts(rng, y, m, 28), "INTEREST", "CREDIT", round(rng.uniform(50, 800), 2))
        )

    # --- non-income noise credits (the traps for is_income detection)
    if rng.random() < 0.15:
        ev.append(
            (_ts(rng, y, m), "REFUND", "CREDIT", round(rng.uniform(100, 3000), 2))
        )
    if rng.random() < 0.25:
        ev.append(
            (_ts(rng, y, m), "P2P_IN", "CREDIT", round(rng.uniform(500, 5000), 2))
        )
    if rng.random() < (0.35 if arch == "SALARIED_PLUS" else 0.15):
        ev.append(
            (
                _ts(rng, y, m),
                "SELF_TRANSFER_IN",
                "CREDIT",
                round(rng.uniform(5000, 50000), -2),
            )
        )
    if rng.random() < 0.02:
        ev.append(
            (
                _ts(rng, y, m),
                "FD_MATURITY",
                "CREDIT",
                round(rng.uniform(20000, 200000), -3),
            )
        )

    # --- fixed debits
    for cat, amt, day in (
        ("RENT_PAID", p["rent_paid"], rng.randint(1, 7)),
        ("EMI", p["emi"], rng.randint(3, 10)),
        ("SIP_INVESTMENT", p["sip"], rng.randint(1, 10)),
        ("INSURANCE", p["premium"], rng.randint(5, 15)),
    ):
        if amt:
            ev.append((_ts(rng, y, m, day, (4, 9)), cat, "DEBIT", amt))
    ev.append((_ts(rng, y, m), "UTILITIES", "DEBIT", round(rng.uniform(800, 3500), 2)))
    ev.append(
        (
            _ts(rng, y, m),
            "MOBILE_RECHARGE",
            "DEBIT",
            float(rng.choice([199, 239, 299, 479, 599, 999])),
        )
    )

    # --- variable spend, sized to income
    fixed = p["rent_paid"] + p["emi"] + p["sip"] + p["premium"]
    variable = max(p["spend_ratio"] * p["exp_income"] - fixed, 0.15 * p["exp_income"])
    for cat, frac, kmax in (
        ("GROCERIES", 0.32, 6),
        ("DINING", 0.14, 6),
        ("SHOPPING", 0.18, 4),
        ("FUEL", 0.10, 3),
        ("MEDICAL", 0.06, 2),
        ("ENTERTAINMENT", 0.06, 2),
        ("CASH_WITHDRAWAL", 0.10, 2),
        ("P2P_OUT", 0.04, 2),
    ):
        for amt in _split(
            rng, variable * frac * rng.uniform(0.6, 1.4), rng.randint(0, kmax)
        ):
            if cat == "CASH_WITHDRAWAL":
                amt = max(500.0, round(amt / 500) * 500)
            ev.append((_ts(rng, y, m), cat, "DEBIT", amt))
    return ev


def generate_customer(rng: random.Random, idx: int) -> tuple[dict, list[dict]]:
    """Returns (customer_row, transaction_rows) with ground truth attached."""
    p = make_profile(rng, idx)
    events: list[tuple] = []
    for y, m in MONTHS:
        events.extend(month_events(rng, p, y, m))
    events.sort(key=lambda e: e[0])

    balance = p["opening_balance"]
    txns = []
    income_total = personal_spend = expense_total = 0.0
    for ts, cat, ttype, amt in events:
        balance = (
            round(balance + amt, 2) if ttype == "CREDIT" else round(balance - amt, 2)
        )
        if cat in INCOME_CATEGORIES:
            income_total += amt
        elif cat == "BUSINESS_EXPENSE":
            expense_total += amt
        elif ttype == "DEBIT" and cat != "SIP_INVESTMENT":
            personal_spend += amt
        txns.append(
            {
                "customer_id": p["customer_id"],
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "txn_type": ttype,
                "amount": f"{amt:.2f}",
                "balance": f"{balance:.2f}",
                "narration": narration(rng, cat, p, ts.year, ts.month),
                "_true_category": cat,
                "_is_income": "true" if cat in INCOME_CATEGORIES else "false",
            }
        )

    # ground truth income = what was actually earned, averaged per month
    # (business income is net of business expenses)
    true_income = (income_total - expense_total) / N_MONTHS
    surplus_ratio = (
        (true_income - personal_spend / N_MONTHS) / true_income
        if true_income > 0
        else 0.0
    )
    prospect = true_income >= 60_000 and surplus_ratio >= 0.25
    if rng.random() < 0.04:  # label noise
        prospect = not prospect

    arch = p["archetype"]
    declared_factor = {
        "SALARIED": (0.90, 1.05),
        "SALARIED_PLUS": (0.90, 1.00),
        "GIG": (0.20, 0.60),
        "BUSINESS": (0.30, 0.70),
        "PENSIONER": (0.90, 1.10),
    }[arch]
    declared_base = p["salary"] if arch == "SALARIED_PLUS" else true_income
    customer = {
        "customer_id": p["customer_id"],
        "name": p["name"],
        "age": p["age"],
        "city": p["city"],
        "occupation_declared": rng.choice(DECLARED_OCC[arch]),
        "declared_monthly_income": f"{round(declared_base * rng.uniform(*declared_factor), -2):.2f}",
        "account_open_date": p["open_date"].isoformat(),
        "_true_occupation": arch,
        "_true_monthly_income": f"{true_income:.2f}",
        "_is_good_prospect": "true" if prospect else "false",
    }
    return customer, txns


# ---------------------------------------------------------------- main


def main() -> None:
    """Generate both CSVs deterministically and print a summary."""
    ap = argparse.ArgumentParser(description="AayAI synthetic raw data generator")
    ap.add_argument("--customers", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    customers, all_txns = [], []
    for i in range(1, args.customers + 1):
        cust, txns = generate_customer(rng, i)
        customers.append(cust)
        all_txns.extend(txns)

    all_txns.sort(key=lambda t: (t["timestamp"], t["customer_id"]))
    for i, t in enumerate(all_txns, 1):
        t["txn_id"] = f"TXN{i:08d}"

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    txn_cols = [
        "txn_id",
        "customer_id",
        "timestamp",
        "txn_type",
        "amount",
        "balance",
        "narration",
        "_true_category",
        "_is_income",
    ]
    with open(RAW_DIR / "transactions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=txn_cols)
        w.writeheader()
        w.writerows(all_txns)
    with open(RAW_DIR / "customers.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(customers[0].keys()))
        w.writeheader()
        w.writerows(customers)

    by_arch: dict[str, int] = {}
    for c in customers:
        by_arch[c["_true_occupation"]] = by_arch.get(c["_true_occupation"], 0) + 1
    print(
        f"[AayAI stage-0] wrote {len(all_txns):,} transactions "
        f"({all_txns[0]['timestamp'][:10]} .. {all_txns[-1]['timestamp'][:10]}) "
        f"and {len(customers)} customers -> {RAW_DIR}"
    )
    print(f"[AayAI stage-0] archetypes: {by_arch}")
    print(
        f"[AayAI stage-0] good prospects: "
        f"{sum(c['_is_good_prospect'] == 'true' for c in customers)}/{len(customers)}"
    )


if __name__ == "__main__":
    main()
