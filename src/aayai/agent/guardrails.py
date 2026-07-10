"""Outreach guardrails: pure checks the agent cannot bypass.

Enforced OUTSIDE the model: consent/frequency caps and the channel allow-list
run before anything is scheduled; the human-approval gate blocks calendar
writes and sends; the message validator rejects drafts that break the message
contract. All constants are named; none of this is model-negotiable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# consent + frequency
ALLOWED_CHANNELS = ("phone", "email", "sms", "branch")
MAX_CONTACTS_PER_WINDOW = 2  # per customer, per rolling window
CONTACT_WINDOW_DAYS = 30

# message contract
# reads in under ~8 seconds: ≈3 words/second silent reading -> 45-word budget
MAX_MESSAGE_WORDS = 45
EM_DASH = "—"
# a call to action = a question or an imperative invitation; count sentences
# that end with "?" plus explicit ask-verbs, and require exactly one
_CTA_VERBS = re.compile(
    r"\b(call|reply|book|schedule|visit|confirm|tap|click|let me know|shall we|"
    r"would you like)\b",
    re.IGNORECASE,
)


class GuardrailError(ValueError):
    """A guardrail refused the action; the message says which and why."""


def check_channel(channel: str) -> None:
    if channel not in ALLOWED_CHANNELS:
        raise GuardrailError(
            f"channel '{channel}' is not in the allow-list {ALLOWED_CHANNELS}"
        )


def check_frequency(recent_contacts: int) -> None:
    """recent_contacts = non-dormant interactions inside CONTACT_WINDOW_DAYS."""
    if recent_contacts >= MAX_CONTACTS_PER_WINDOW:
        raise GuardrailError(
            f"frequency cap: customer already has {recent_contacts} contact(s) in "
            f"the last {CONTACT_WINDOW_DAYS} days (max {MAX_CONTACTS_PER_WINDOW})"
        )


def check_approved(interaction: dict) -> None:
    """Calendar writes and sends require a human approval on the row."""
    if not interaction.get("approved_at"):
        raise GuardrailError(
            "human approval required: interaction is not approved; the agent "
            "proposes, the RM commits"
        )


@dataclass
class MessageCheck:
    ok: bool
    problems: list[str]


def validate_message(text: str) -> MessageCheck:
    """The drafted-message contract: short, one CTA, signal-tied, no em dashes."""
    problems: list[str] = []
    if EM_DASH in text:
        problems.append("contains an em dash")
    words = len(text.split())
    if words > MAX_MESSAGE_WORDS:
        problems.append(
            f"too long to read in 8 seconds ({words} words > {MAX_MESSAGE_WORDS})"
        )
    questions = text.count("?")
    cta_hits = len(_CTA_VERBS.findall(text))
    total_cta = max(questions, 0) + (1 if cta_hits and not questions else 0)
    if questions + cta_hits == 0:
        problems.append("no call to action")
    elif questions > 1 or (questions == 0 and cta_hits > 1) or total_cta > 1:
        problems.append("more than one call to action")
    return MessageCheck(ok=not problems, problems=problems)
