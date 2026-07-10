"""The agent loop: a model using tools on environmental feedback until done.

send goal + tool schemas -> model may call tools -> we run them and feed the
results back -> repeat, until the model answers with no tool call or a max-steps
cap is hit (so it can never spin forever). Every tool call and observation is
recorded on the result for auditing.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from aayai.agent.client import LLMClient
from aayai.agent.tools import Tool

log = logging.getLogger("aayai.agent")


@dataclass
class AgentStep:
    """One recorded step: a tool call (with its observation) or the final answer."""

    kind: str  # "tool_call" | "final"
    detail: dict


@dataclass
class AgentResult:
    final_text: str | None
    steps: list[AgentStep] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)  # names invoked, in order
    stopped_reason: str = "answered"  # "answered" | "max_steps"


def run_agent(
    goal: str,
    tools: list[Tool],
    client: LLMClient,
    *,
    system: str | None = None,
    max_steps: int = 6,
) -> AgentResult:
    """Drive the tool-use loop and return the final answer plus a full audit."""
    tool_by_name = {t.name: t for t in tools}
    schemas = [t.schema() for t in tools]

    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": goal})

    result = AgentResult(final_text=None)
    for _ in range(max_steps):
        turn = client.chat(messages, tools=schemas)
        messages.append(turn.assistant_message)

        if not turn.tool_calls:  # the model answered -> done
            result.final_text = turn.content
            result.steps.append(AgentStep("final", {"content": turn.content}))
            result.stopped_reason = "answered"
            return result

        for call in turn.tool_calls:
            result.tool_calls.append(call.name)
            tool = tool_by_name.get(call.name)
            if tool is None:
                observation: object = {"error": f"unknown tool '{call.name}'"}
            else:
                try:
                    observation = tool.fn(**call.arguments)
                except Exception as exc:  # tool failures are fed back, not raised
                    observation = {"error": f"{exc.__class__.__name__}: {exc}"}
            log.info("agent tool_call %s(%s)", call.name, call.arguments)
            result.steps.append(
                AgentStep(
                    "tool_call",
                    {
                        "name": call.name,
                        "arguments": call.arguments,
                        "observation": observation,
                    },
                )
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(observation, default=str),
                }
            )

    # hit the cap without a final answer, stop cleanly, never loop forever
    result.stopped_reason = "max_steps"
    result.steps.append(AgentStep("final", {"content": None, "note": "max_steps"}))
    return result
