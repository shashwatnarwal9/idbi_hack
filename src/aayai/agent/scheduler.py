"""Outreach scheduler: timing windows from RULES over the data, never guesses.

Each window names the SIGNAL that opened it (emi_ending, recent
enquiry/eligibility check, quadrant cadence), so every why_now downstream
traces to something real in the serving store. The agent's only freedom is
turning a window + RM availability into a concrete proposed slot; a human then
approves before anything lands on a calendar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

# window rules (all named constants)
EMI_ENDING_WINDOW_DAYS = 14  # an ending EMI opens a two-week window
WARM_EVENT_MAX_AGE_DAYS = 14  # enquiry/eligibility check counts as warm this long
WARM_WINDOW_DAYS = 3  # a warm lead should be acted on within days
ACT_NOW_WINDOW_DAYS = 2  # act_now leads get near-term slots
NURTURE_SPACING_DAYS = 21  # nurture gets spaced follow-ups
WORKING_HOURS = (time(10, 0), time(17, 0))  # proposed slots stay in office hours
SLOT_MINUTES = 30


@dataclass
class Window:
    """An outreach window opened by one named signal."""

    signal: str  # machine name, e.g. "emi_ending"
    why_now: str  # human sentence tracing to that signal
    opens: datetime
    closes: datetime
    priority: int  # lower = more urgent


def timing_windows(
    *,
    now: datetime,
    quadrant: str,
    emi_ending: bool = False,
    ending_stream: str | None = None,
    days_since_strong_event: int | None = None,
    last_event_type: str | None = None,
) -> list[Window]:
    """Derive every open window for a lead from its real signals, best first."""
    windows: list[Window] = []

    if emi_ending:
        stream = f" ({ending_stream})" if ending_stream else ""
        windows.append(
            Window(
                signal="emi_ending",
                why_now=(
                    f"An existing EMI{stream} has ended or is ending, freeing up "
                    "repayment capacity right now"
                ),
                opens=now,
                closes=now + timedelta(days=EMI_ENDING_WINDOW_DAYS),
                priority=1,
            )
        )

    if (
        days_since_strong_event is not None
        and days_since_strong_event <= WARM_EVENT_MAX_AGE_DAYS
    ):
        what = last_event_type or "a loan enquiry"
        windows.append(
            Window(
                signal="recent_strong_event",
                why_now=(
                    f"Customer made {what} {days_since_strong_event} day(s) ago; "
                    "intent is warm and cooling"
                ),
                opens=now,
                closes=now + timedelta(days=WARM_WINDOW_DAYS),
                priority=0,
            )
        )

    if quadrant == "act_now":
        windows.append(
            Window(
                signal="quadrant_act_now",
                why_now="High capacity and high intent (act-now quadrant)",
                opens=now,
                closes=now + timedelta(days=ACT_NOW_WINDOW_DAYS),
                priority=2,
            )
        )
    elif quadrant == "nurture":
        windows.append(
            Window(
                signal="quadrant_nurture",
                why_now=(
                    "High capacity, intent still forming (nurture cadence: "
                    f"spaced follow-up every {NURTURE_SPACING_DAYS} days)"
                ),
                opens=now + timedelta(days=NURTURE_SPACING_DAYS),
                closes=now + timedelta(days=NURTURE_SPACING_DAYS + 7),
                priority=5,
            )
        )

    return sorted(windows, key=lambda w: (w.priority, w.opens))


def propose_slots(
    window: Window,
    busy: list[tuple[datetime, datetime]],
    *,
    max_slots: int = 3,
) -> list[datetime]:
    """Concrete slot proposals inside a window, avoiding the RM's busy times.

    Steps through working hours in SLOT_MINUTES increments from the window's
    open; a slot is offered if it does not overlap any busy interval. Proposals
    only, nothing is written until a human approves.
    """
    slots: list[datetime] = []
    slot_len = timedelta(minutes=SLOT_MINUTES)
    cursor = max(
        window.opens,
        window.opens.replace(
            hour=WORKING_HOURS[0].hour, minute=0, second=0, microsecond=0
        ),
    )
    while cursor < window.closes and len(slots) < max_slots:
        end_of_day = cursor.replace(
            hour=WORKING_HOURS[1].hour, minute=0, second=0, microsecond=0
        )
        if cursor.time() < WORKING_HOURS[0]:
            cursor = cursor.replace(
                hour=WORKING_HOURS[0].hour, minute=0, second=0, microsecond=0
            )
        if cursor >= end_of_day:
            cursor = (cursor + timedelta(days=1)).replace(
                hour=WORKING_HOURS[0].hour, minute=0, second=0, microsecond=0
            )
            continue
        slot_end = cursor + slot_len
        if not any(b0 < slot_end and cursor < b1 for b0, b1 in busy):
            slots.append(cursor)
        cursor += slot_len
    return slots
