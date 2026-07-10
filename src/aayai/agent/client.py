"""LLM client for the outreach agent: GLM-5.2 over the NVIDIA endpoint.

The concrete NvidiaGLMClient is a thin wrapper over the OpenAI-compatible SDK.
The LLMClient Protocol lets tests inject a deterministic fake, so the agent
loop, council routing and message validators are all provable WITHOUT a live
key or network. The `openai` package and the key are only touched inside
NvidiaGLMClient.__init__, so importing this module is always safe.

Credentials: NVIDIA_API_KEY is read from the environment and never hardcoded.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol

from dotenv import load_dotenv

load_dotenv()  # same pattern as serving.db: pick up NVIDIA_API_KEY from .env

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL = "z-ai/glm-5.2"


@dataclass
class ToolCall:
    """One tool invocation the model asked for."""

    id: str
    name: str
    arguments: dict


@dataclass
class ChatResult:
    """A single model turn: free text and/or tool calls, plus the raw assistant
    message to append back to the running history (OpenAI chat format)."""

    content: str | None
    tool_calls: list[ToolCall]
    assistant_message: dict


class LLMClient(Protocol):
    """Anything that can take a message list (+ tool schemas) and return a turn."""

    def chat(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> ChatResult: ...


class NvidiaGLMClient:
    """GLM-5.2 via the NVIDIA OpenAI-compatible endpoint (key from env only).

    Measured behaviour of this endpoint: requests queue for MINUTES before the
    first token (a ~5-word reply took 282s cold), so the timeout is generous and
    every request STREAMS, a streaming connection stays alive through the queue
    and lets us accumulate content and tool-call deltas as they arrive. One
    retry is allowed because the congested gateway sometimes sheds a queued
    request with a 504 even though the next attempt succeeds.
    """

    def __init__(
        self,
        model: str = MODEL,
        temperature: float = 0.4,
        timeout_s: float = 600.0,
        max_tokens: int = 4096,
    ) -> None:
        api_key = os.environ.get("NVIDIA_API_KEY")
        if not api_key:
            raise RuntimeError(
                "NVIDIA_API_KEY is not set, export it before running the live agent"
            )
        from openai import OpenAI  # imported here so the module stays import-safe

        self._client = OpenAI(
            base_url=NVIDIA_BASE_URL,
            api_key=api_key,
            timeout=timeout_s,
            max_retries=1,  # gateway sheds queued requests with spurious 504s
        )
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def _stream(
        self, messages: list[dict], tools: list[dict] | None
    ) -> tuple[str, list[dict]]:
        """Stream one turn; return (content, raw tool_call dicts)."""
        stream = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools or None,
            tool_choice="auto" if tools else None,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=True,
        )
        content_parts: list[str] = []
        # tool-call deltas arrive fragmented by index; assemble them
        calls: dict[int, dict] = {}
        for chunk in stream:
            if not getattr(chunk, "choices", None):
                continue
            delta = chunk.choices[0].delta
            if delta is None:
                continue
            if delta.content:
                content_parts.append(delta.content)
            for tc in delta.tool_calls or []:
                slot = calls.setdefault(
                    tc.index,
                    {
                        "id": "",
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    },
                )
                if tc.id:
                    slot["id"] = tc.id
                if tc.function and tc.function.name:
                    slot["function"]["name"] = tc.function.name
                if tc.function and tc.function.arguments:
                    slot["function"]["arguments"] += tc.function.arguments
        raw_calls = [calls[i] for i in sorted(calls)]
        return "".join(content_parts), raw_calls

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> ChatResult:
        content, raw_calls = self._stream(messages, tools)
        tool_calls = [
            ToolCall(
                rc["id"] or f"call_{i}",
                rc["function"]["name"],
                json.loads(rc["function"]["arguments"] or "{}"),
            )
            for i, rc in enumerate(raw_calls)
        ]
        assistant_message: dict = {"role": "assistant", "content": content}
        if raw_calls:
            assistant_message["tool_calls"] = raw_calls
        return ChatResult(content or None, tool_calls, assistant_message)

    def complete(self, system: str, user: str, temperature: float | None = None) -> str:
        """One-shot text completion (used by the council lenses; no tools)."""
        old = self.temperature
        if temperature is not None:
            self.temperature = temperature
        try:
            content, _ = self._stream(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                tools=None,
            )
        finally:
            self.temperature = old
        return content
