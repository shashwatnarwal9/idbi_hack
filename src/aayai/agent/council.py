"""Strategist + LLM council: how to approach a lead.

Cheap/obvious leads get a SINGLE strategist pass. HIGH-STAKES leads (act_now,
large amounts, or low-confidence bands) get a COUNCIL first, because that is
where being wrong is expensive:

  1. five thinking lenses run as separate GLM-5.2 calls IN PARALLEL, each
     leaning fully into its angle (no hedging),
  2. ANONYMOUS peer review: the five are relabelled A-E at random and each
     reviewer names the strongest, the biggest blind spot, and the one thing
     ALL of them missed,
  3. a CHAIRMAN call synthesises and may overrule the majority when the
     dissenter's reasoning is stronger.

The chairman's output is the approach written to the interaction row. Every
call is recorded on the result for auditing. All model I/O goes through the
LLMClient protocol, so routing/anonymisation/synthesis are provable offline
with a fake client.
"""

from __future__ import annotations

import json
import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Protocol

# stakes routing (named constants)
HIGH_STAKES_QUADRANTS = {"act_now"}
HIGH_STAKES_AMOUNT = 2_000_000  # ≥ Rs 20L best-repayable is expensive to fumble
HIGH_STAKES_BANDS = {"low"}  # ambiguous estimates deserve scrutiny

# minimum surviving advisors for a council verdict when the endpoint sheds calls
COUNCIL_QUORUM = 3


class CouncilUnavailable(RuntimeError):
    """Too few advisors responded for a trustworthy council verdict."""


def _fan_out(
    client: "TextLLM", jobs: dict[str, tuple[str, str]], parallel: bool
) -> dict[str, str]:
    """Run (system, user) jobs, dropping individual failures instead of raising."""
    results: dict[str, str] = {}
    if parallel:
        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            futures = {
                name: pool.submit(client.complete, system, user)
                for name, (system, user) in jobs.items()
            }
            for name, fut in futures.items():
                try:
                    results[name] = fut.result()
                except Exception:  # a shed request loses one voice, not the council
                    continue
    else:
        for name, (system, user) in jobs.items():
            try:
                results[name] = client.complete(system, user)
            except Exception:
                continue
    return results


def is_high_stakes(lead: dict) -> bool:
    """Council only where being wrong is expensive; cheap leads skip it."""
    if lead.get("quadrant") in HIGH_STAKES_QUADRANTS:
        return True
    amount = lead.get("best_repayable_amount") or 0
    if amount >= HIGH_STAKES_AMOUNT:
        return True
    if lead.get("confidence_band") in HIGH_STAKES_BANDS:
        return True
    return False


class TextLLM(Protocol):
    """The single-completion surface the council needs (see NvidiaGLMClient)."""

    def complete(
        self, system: str, user: str, temperature: float | None = None
    ) -> str: ...


LENSES: dict[str, str] = {
    "contrarian": (
        "You are the CONTRARIAN on a bank outreach council. Your only job: say "
        "exactly how this outreach FAILS or annoys the customer. Attack the "
        "premise, the timing, the channel and the message. No hedging, no "
        "balance, the others will do that."
    ),
    "first_principles": (
        "You are the FIRST-PRINCIPLES thinker on a bank outreach council. "
        "Ignore the plan on the table. From the raw signals alone, reason out "
        "whether this is even the right product and the right moment, and what "
        "the customer actually needs. No hedging."
    ),
    "expansionist": (
        "You are the EXPANSIONIST on a bank outreach council. Your only job: "
        "name the bigger cross-sell, bundling or timing upside everyone else "
        "is missing. Think one size larger. No hedging."
    ),
    "outsider": (
        "You are the OUTSIDER on a bank outreach council. You know nothing "
        "about banking jargon. Read the plan as the customer would: would a "
        "person with zero context understand it and why it concerns them? "
        "Flag every assumption. No hedging."
    ),
    "executor": (
        "You are the EXECUTOR on a bank outreach council. Your only job: state "
        "the single fastest concrete next action, who does it, and when. One "
        "action only. No hedging."
    ),
}

REVIEWER_SYSTEM = (
    "You are reviewing five anonymous council opinions labelled A-E about one "
    "bank outreach plan. Name: (1) the strongest opinion and why, (2) the "
    "biggest blind spot among them, (3) the ONE thing ALL of them missed. "
    "Be specific and brief."
)

CHAIRMAN_SYSTEM = (
    "You are the CHAIRMAN of a bank outreach council. You have five advisor "
    "opinions and anonymous peer reviews of them. Synthesise: where they "
    "agree, where they clash, blind spots the review caught, and a clear "
    "final recommendation. You may OVERRULE the majority if a dissenter's "
    "reasoning is stronger, say so explicitly when you do. End with exactly "
    "one line starting 'FIRST ACTION:' naming the one thing to do first, and "
    "one line starting 'MESSAGE:' with the drafted opening message (under 45 "
    "words, one call to action, no em dashes)."
)


@dataclass
class CouncilResult:
    used_council: bool
    approach: str  # the final approach text (chairman synthesis or single pass)
    first_action: str | None = None
    drafted_message: str | None = None
    opinions: dict[str, str] = field(default_factory=dict)  # lens -> text
    reviews: dict[str, str] = field(default_factory=dict)  # lens -> review text
    label_map: dict[str, str] = field(default_factory=dict)  # anon label -> lens
    calls_made: int = 0


def _lead_brief(lead: dict, why_now: str) -> str:
    return (
        "LEAD (real data, do not invent):\n"
        + json.dumps(lead, default=str, indent=2)
        + f"\nWHY NOW (signal-backed): {why_now}\n"
    )


def _parse_tail(text: str) -> tuple[str | None, str | None]:
    """Pull the FIRST ACTION / MESSAGE lines from the chairman synthesis."""
    first_action = message = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("FIRST ACTION:"):
            first_action = stripped.split(":", 1)[1].strip()
        elif stripped.upper().startswith("MESSAGE:"):
            message = stripped.split(":", 1)[1].strip()
    return first_action, message


SINGLE_STRATEGIST_SYSTEM = (
    "You are a bank outreach strategist. For the given lead produce a short "
    "plan: product to lead with, why now (cite the given signal, never invent "
    "one), channel, tone. End with exactly one line starting 'FIRST ACTION:' "
    "and one line starting 'MESSAGE:' with the drafted opening message (under "
    "45 words, one call to action, no em dashes)."
)


def run_strategist(
    lead: dict,
    why_now: str,
    client: TextLLM,
    *,
    rng: random.Random | None = None,
    parallel: bool = True,
) -> CouncilResult:
    """Single pass for cheap leads; full council for high-stakes leads."""
    brief = _lead_brief(lead, why_now)

    if not is_high_stakes(lead):
        text = client.complete(SINGLE_STRATEGIST_SYSTEM, brief)
        first_action, message = _parse_tail(text)
        return CouncilResult(
            used_council=False,
            approach=text,
            first_action=first_action,
            drafted_message=message,
            calls_made=1,
        )

    # 1. five lenses in parallel
    # The congested endpoint sometimes sheds one of the parallel calls with a
    # 5xx. A single lost advisor must not sink the whole council: keep whatever
    # opinions survive as long as a quorum remains.
    lens_names = list(LENSES)
    opinions = _fan_out(
        client, {name: (LENSES[name], brief) for name in lens_names}, parallel
    )
    if len(opinions) < COUNCIL_QUORUM:
        raise CouncilUnavailable(
            f"only {len(opinions)}/{len(lens_names)} advisors responded "
            f"(quorum {COUNCIL_QUORUM})"
        )

    # 2. anonymous peer review (relabel A-E at random)
    rng = rng or random.Random()
    responded = list(opinions)
    shuffled = responded[:]
    rng.shuffle(shuffled)
    label_map = {label: lens for label, lens in zip("ABCDE", shuffled)}
    anon_block = "\n\n".join(
        f"OPINION {label}:\n{opinions[lens]}" for label, lens in label_map.items()
    )
    # reviews are best-effort: a failed reviewer is simply absent
    reviews = _fan_out(
        client,
        {name: (REVIEWER_SYSTEM, brief + "\n" + anon_block) for name in responded},
        parallel,
    )

    # 3. chairman synthesis (may overrule the majority)
    review_block = "\n\n".join(f"REVIEW by {n}:\n{r}" for n, r in reviews.items())
    synthesis = client.complete(
        CHAIRMAN_SYSTEM, brief + "\n" + anon_block + "\n\n" + review_block
    )
    first_action, message = _parse_tail(synthesis)
    return CouncilResult(
        used_council=True,
        approach=synthesis,
        first_action=first_action,
        drafted_message=message,
        opinions=opinions,
        reviews=reviews,
        label_map=label_map,
        calls_made=len(opinions) + len(reviews) + 1,  # lenses + reviews + chairman
    )
