"""Live tool-calling proof: run this ONCE with a real key to verify GLM-5.2.

    set NVIDIA_API_KEY=...        (PowerShell: $env:NVIDIA_API_KEY="...")
    python -m aayai.agent.proof

It gives the model a goal that requires the leads_list tool, runs the agent
loop, and asserts the model actually called the tool and consumed its result.
Prints the full audit trail. Needs a live key + a populated serving store.
"""

from __future__ import annotations

import sys

from aayai.agent.client import NvidiaGLMClient
from aayai.agent.loop import run_agent
from aayai.agent.tools import LEADS_LIST

SYSTEM = (
    "You are an outreach-planning agent for a bank's relationship managers. "
    "Use the provided tools to fetch REAL leads from the system; never invent "
    "customers or numbers. When you have the data, give a one-line summary."
)
GOAL = (
    "Using the leads_list tool, fetch the act-now leads for personal loans, "
    "then tell me how many there are and name the top one."
)


def main() -> int:
    try:
        client = NvidiaGLMClient()
    except RuntimeError as exc:
        print(f"[proof] {exc}")
        return 2

    result = run_agent(GOAL, [LEADS_LIST], client, system=SYSTEM, max_steps=4)

    print(f"[proof] stopped_reason = {result.stopped_reason}")
    print(f"[proof] tool_calls     = {result.tool_calls}")
    for step in result.steps:
        if step.kind == "tool_call":
            obs = step.detail["observation"]
            n = obs.get("count") if isinstance(obs, dict) else "?"
            print(
                f"  -> {step.detail['name']}({step.detail['arguments']}) => count={n}"
            )
        else:
            print(f"  final: {step.detail.get('content')}")

    if "leads_list" not in result.tool_calls:
        print("[proof] FAIL: the model did not call leads_list")
        return 1
    print("[proof] OK: GLM-5.2 called the tool and consumed the result")
    return 0


if __name__ == "__main__":
    sys.exit(main())
