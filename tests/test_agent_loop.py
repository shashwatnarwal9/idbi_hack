"""Agent loop mechanics, proven offline with a deterministic fake LLM client.

No key or network: a fake client emits a tool call then a final answer, so we
can assert the loop runs plan -> tool -> observe -> repeat -> stop, feeds the
observation back, and enforces the max-steps cap (never loops forever).
"""

import json

from aayai.agent.client import ChatResult, ToolCall
from aayai.agent.loop import run_agent
from aayai.agent.tools import Tool


def _counting_tool():
    calls = {"n": 0, "last_args": None}

    def fn(**kwargs):
        calls["n"] += 1
        calls["last_args"] = kwargs
        return {"count": 1, "leads": [{"customer_id": "CUST01001", "name": "A B"}]}

    tool = Tool(
        name="leads_list",
        description="fake",
        parameters={"type": "object", "properties": {}, "required": []},
        fn=fn,
    )
    return tool, calls


def _assistant_toolcall(call_id: str, name: str, args: dict) -> dict:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }
        ],
    }


class FakeToolThenAnswer:
    """Turn 1: call the tool. Turn 2 (after seeing the result): final answer."""

    def __init__(self):
        self.turn = 0

    def chat(self, messages, tools=None):
        self.turn += 1
        if self.turn == 1:
            args = {"quadrant": "act_now"}
            return ChatResult(
                None,
                [ToolCall("call_1", "leads_list", args)],
                _assistant_toolcall("call_1", "leads_list", args),
            )
        # The tool observation must be present in history before we answer.
        assert any(m.get("role") == "tool" for m in messages)
        return ChatResult(
            "There is 1 act-now lead: A B.",
            [],
            {"role": "assistant", "content": "There is 1 act-now lead: A B."},
        )


class AlwaysCallsTool:
    """Never answers, used to prove the max-steps cap stops the loop."""

    def chat(self, messages, tools=None):
        return ChatResult(
            None,
            [ToolCall("c", "leads_list", {})],
            _assistant_toolcall("c", "leads_list", {}),
        )


def test_loop_calls_tool_feeds_result_then_finishes():
    tool, calls = _counting_tool()
    res = run_agent("list act-now leads", [tool], FakeToolThenAnswer(), max_steps=5)

    assert calls["n"] == 1  # the tool actually ran once
    assert calls["last_args"] == {"quadrant": "act_now"}  # model's args passed through
    assert res.tool_calls == ["leads_list"]
    assert res.stopped_reason == "answered"
    assert res.final_text == "There is 1 act-now lead: A B."
    # the observation was recorded for auditing and fed back to the model
    obs = [s for s in res.steps if s.kind == "tool_call"][0].detail["observation"]
    assert obs["count"] == 1


def test_loop_respects_max_steps_no_infinite_loop():
    tool, calls = _counting_tool()
    res = run_agent("x", [tool], AlwaysCallsTool(), max_steps=3)
    assert res.stopped_reason == "max_steps"
    assert res.final_text is None
    assert calls["n"] == 3  # exactly max_steps tool runs, then it stops


def test_unknown_tool_is_reported_not_raised():
    class CallsMissing:
        def __init__(self):
            self.turn = 0

        def chat(self, messages, tools=None):
            self.turn += 1
            if self.turn == 1:
                return ChatResult(
                    None,
                    [ToolCall("c", "does_not_exist", {})],
                    _assistant_toolcall("c", "does_not_exist", {}),
                )
            return ChatResult("done", [], {"role": "assistant", "content": "done"})

    tool, _ = _counting_tool()
    res = run_agent("x", [tool], CallsMissing(), max_steps=4)
    obs = [s for s in res.steps if s.kind == "tool_call"][0].detail["observation"]
    assert "error" in obs and "unknown tool" in obs["error"]
