"""Customer-facing financial summary PDF.

A clean, plain-language summary built live from one customer's real profile:
income, cash-flow, confidence and optional saving guidance. It deliberately
excludes all internal model mechanics (prospect score, SHAP impactors, reasoning);
none of that appears on the customer version. fpdf2 core fonts are latin-1 only,
so figures use "Rs" and the brand is romanised (AayAI).
"""

from __future__ import annotations

from datetime import date

from fpdf import FPDF

DISCLAIMER = (
    "This is an informational estimate based on your transaction data. "
    "It is not a loan decision, an approval or denial, or financial advice."
)

INCOME_TYPE_PLAIN = {
    "salaried": "primarily salaried income",
    "gig": "primarily gig / platform income",
    "business": "primarily business income",
}

BAND_PLAIN = {
    "high": "High confidence",
    "medium": "Medium confidence",
    "low": "Low confidence",
}
BAND_MEANING = {
    "high": "We could read your transactions clearly over a long history.",
    "medium": "A good read, though history or transaction clarity is moderate.",
    "low": "Limited history or harder-to-read transactions; treat as indicative.",
}

FOREST = (31, 74, 56)
INK = (28, 43, 35)
MUTED = (120, 130, 124)


def mask_id(customer_id: str) -> str:
    """Partially mask an internal id, e.g. CUST00087 -> CUST***87."""
    if len(customer_id) <= 4:
        return customer_id
    return f"{customer_id[:4]}***{customer_id[-2:]}"


def _rs(value: float) -> str:
    return f"Rs {round(value):,}"


def build_customer_summary(
    profile: dict, surplus: dict, *, synthetic: bool = True
) -> bytes:
    """Render the clean customer summary PDF from live profile data.

    Args:
        profile: the 'profile' block of a customer analysis.
        surplus: the 'surplus_breakdown' block (income/essentials/emis/surplus).
        synthetic: when True, footer notes the demo data is synthetic.
    """
    pdf = FPDF(format="A4")
    pdf.set_margins(18, 16, 18)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    # header
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(*FOREST)
    pdf.cell(0, 10, "AayAI", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 13)
    pdf.set_text_color(*INK)
    pdf.cell(0, 8, "Your Financial Summary", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, date.today().strftime("%d %B %Y"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    # prominent disclaimer near the top
    pdf.set_draw_color(*FOREST)
    pdf.set_fill_color(222, 240, 229)
    pdf.set_text_color(*INK)
    pdf.set_font("Helvetica", "I", 9)
    pdf.multi_cell(0, 5, DISCLAIMER, border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # identity
    pdf.set_text_color(*INK)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, str(profile["name"]), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*MUTED)
    pdf.cell(
        0,
        5,
        f"Reference: {mask_id(str(profile['customer_id']))}",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(3)

    # reconstructed income
    income_type = INCOME_TYPE_PLAIN.get(profile["income_type"], profile["income_type"])
    _section(pdf, "Estimated monthly income")
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*FOREST)
    pdf.cell(0, 10, _rs(surplus["income"]), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(
        0,
        5,
        f"Estimated from your transaction history ({income_type}).",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(3)

    # cash-flow summary (plain figures only)
    _section(pdf, "Your monthly cash flow")
    _row(pdf, "Estimated income", _rs(surplus["income"]))
    _row(pdf, "Essentials (rent, bills, groceries)", "- " + _rs(surplus["essentials"]))
    _row(pdf, "Loan EMIs", "- " + _rs(surplus["emis"]))
    _row(pdf, "Investable surplus", _rs(surplus["surplus"]), bold=True)
    pdf.ln(3)

    # confidence (honest trustworthiness signal)
    band = profile["confidence_band"]
    _section(pdf, "How confident is this estimate?")
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*INK)
    pdf.cell(0, 7, BAND_PLAIN.get(band, band), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 5, BAND_MEANING.get(band, ""), new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(
        0,
        5,
        f"Based on {int(profile['months_history'])} months of history and how "
        f"cleanly your transactions were read ({round(profile['pct_categorized'] * 100)}%).",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(3)

    # optional plain guidance (no products, no returns, no guarantees)
    if surplus["surplus"] > 0:
        lo = round(surplus["surplus"] * 0.4 / 100) * 100
        hi = round(surplus["surplus"] * 0.6 / 100) * 100
        _section(pdf, "A simple saving idea")
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*INK)
        pdf.multi_cell(
            0,
            5,
            f"If it suits you, setting aside {_rs(lo)} to {_rs(hi)} a month "
            "(about 40-60% of your surplus) could steadily build your savings. "
            "This is a general idea, not a recommendation of any product.",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.ln(2)

    # footer disclaimer + synthetic note (no auto-break so it stays on this page)
    pdf.set_auto_page_break(False)
    pdf.set_y(-20)
    pdf.set_draw_color(*MUTED)
    pdf.line(18, pdf.get_y(), 192, pdf.get_y())
    pdf.ln(1)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(*MUTED)
    footer = DISCLAIMER
    if synthetic:
        footer += " Demo document: the underlying data is synthetic."
    pdf.multi_cell(0, 4, footer, new_x="LMARGIN", new_y="NEXT")

    return bytes(pdf.output())


def _section(pdf: FPDF, title: str) -> None:
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 5, title.upper(), new_x="LMARGIN", new_y="NEXT")


def _row(pdf: FPDF, label: str, value: str, *, bold: bool = False) -> None:
    pdf.set_font("Helvetica", "B" if bold else "", 11)
    pdf.set_text_color(*INK)
    pdf.cell(120, 7, label)
    pdf.cell(0, 7, value, align="R", new_x="LMARGIN", new_y="NEXT")
