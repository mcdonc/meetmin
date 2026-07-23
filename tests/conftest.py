"""Shared test fakes: a minimal stand-in for the OpenAI client.

The stub mimics only what meetmin uses: ``client.chat.completions.create(...)``
returning an object whose ``.choices[0].message`` has ``.content`` and
``.tool_calls`` (each with ``.id`` and ``.function.{name,arguments}``). Scripted
responses are popped in order, so a test can drive a multi-step tool loop.
"""

from __future__ import annotations

import json
from types import SimpleNamespace


def tool_call(name: str, arguments: dict, call_id: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=call_id or f"call_{name}",
        type="function",
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def assistant_tool_turn(*calls: SimpleNamespace) -> SimpleNamespace:
    """A model turn that issues one or more tool calls."""
    return SimpleNamespace(content=None, tool_calls=list(calls))


def assistant_final(text: str) -> SimpleNamespace:
    """A model turn with a plain-text final answer (no tool calls)."""
    return SimpleNamespace(content=text, tool_calls=None)


class FakeCompletions:
    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def create(self, **kwargs) -> SimpleNamespace:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("FakeClient ran out of scripted responses")
        message = self._responses.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeClient:
    """Drop-in for openai.OpenAI, scripted with a list of message turns."""

    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self.chat = SimpleNamespace(completions=FakeCompletions(responses))
