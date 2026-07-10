"""Daily outreach refresh: plan the top leads into PROPOSED interactions.

    python -m aayai.agent.run_planner --rm rm-1 --top 5 --product personal

For each top lead without an open interaction it derives the timing window
from real signals, proposes a slot, runs the strategist (full council only for
high-stakes leads), and writes a PLANNED, UNAPPROVED row. Also prints the
reminders now due. Wire this to a daily cadence via the Airflow task
`outreach_refresh`.

Requires NVIDIA_API_KEY (the strategist is live GLM-5.2).
"""

from __future__ import annotations

import argparse

from aayai.agent.client import NvidiaGLMClient
from aayai.agent.planner import plan_outreach
from aayai.agent.tools import leads_list
from aayai.serving import interactions as ix
from aayai.serving.db import connect


def refresh(rm_id: str, product: str, quadrant: str, top: int) -> int:
    client = NvidiaGLMClient()
    conn = connect()
    try:
        ix.ensure_table(conn)
        leads = leads_list(quadrant=quadrant, product=product, limit=top)["leads"]
        planned = 0
        for lead in leads:
            open_rows = [
                r
                for r in ix.list_interactions(conn, cust_id=lead["customer_id"])
                if r["status"] in ("planned", "contacted")
            ]
            if open_rows:
                print(f"[planner] {lead['customer_id']}: open interaction exists, skip")
                continue
            outcome = plan_outreach(conn, lead, rm_id, client)
            tag = "council" if outcome.used_council else "single-pass"
            if outcome.created:
                row = outcome.interaction
                print(
                    f"[planner] {lead['customer_id']}: planned #{row['id']} "
                    f"({tag}) at {row['scheduled_at']} | why: {row['why_now']}"
                )
                planned += 1
            else:
                print(f"[planner] {lead['customer_id']}: skipped, {outcome.reason}")

        due = ix.reminders_due(conn, rm_id)
        print(f"[planner] reminders due for {rm_id}: {len(due)}")
        for d in due:
            print(
                f"  due #{d['id']} {d['cust_id']} at {d['scheduled_at']} [{d['status']}]"
            )
        return planned
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="Plan outreach for the top leads")
    ap.add_argument("--rm", default="rm-1")
    ap.add_argument("--product", default="personal")
    ap.add_argument("--quadrant", default="act_now")
    ap.add_argument("--top", type=int, default=5)
    args = ap.parse_args()
    n = refresh(args.rm, args.product, args.quadrant, args.top)
    print(f"[planner] {n} new interaction(s) proposed, awaiting human approval")


if __name__ == "__main__":
    main()
