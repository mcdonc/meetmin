"""Tests for the model-compatible chat wrapper."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from openai import BadRequestError

from meetmin import chat
from meetmin.chat import chat_completion


def _bad_request(message: str) -> BadRequestError:
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    response = httpx.Response(400, request=request)
    return BadRequestError(message, response=response, body=None)


class ScriptedCompletions:
    """create() replays a script of exceptions-to-raise / values-to-return."""

    def __init__(self, script):
        self.script = list(script)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class ScriptedClient:
    def __init__(self, script):
        self.chat = SimpleNamespace(completions=ScriptedCompletions(script))


OK = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])


def test_adapts_max_tokens_to_max_completion_tokens():
    client = ScriptedClient([
        _bad_request("Unsupported parameter: 'max_tokens' is not supported with this "
                     "model. Use 'max_completion_tokens' instead."),
        OK,
    ])
    result = chat_completion(client, model="reasoning-a", messages=[], max_tokens=50)
    assert result is OK
    calls = client.chat.completions.calls
    assert "max_tokens" in calls[0]
    assert calls[1].get("max_completion_tokens") == 50
    assert "max_tokens" not in calls[1]
    assert chat._TOKEN_PARAM["reasoning-a"] == "max_completion_tokens"


def test_adapts_unsupported_temperature():
    client = ScriptedClient([
        _bad_request("Unsupported value: 'temperature' does not support 0.2 with this "
                     "model. Only the default (1) value is supported."),
        OK,
    ])
    result = chat_completion(
        client, model="reasoning-b", messages=[], temperature=0.2
    )
    assert result is OK
    assert "temperature" not in client.chat.completions.calls[1]
    assert chat._ALLOW_TEMPERATURE["reasoning-b"] is False


def test_adapts_both_params():
    client = ScriptedClient([
        _bad_request("Use 'max_completion_tokens' instead."),
        _bad_request("'temperature' does not support 0.2"),
        OK,
    ])
    result = chat_completion(
        client, model="reasoning-c", messages=[], temperature=0.2, max_tokens=50
    )
    assert result is OK
    assert len(client.chat.completions.calls) == 3


def test_unrelated_bad_request_reraises():
    client = ScriptedClient([_bad_request("you are out of quota")])
    with pytest.raises(BadRequestError):
        chat_completion(client, model="reasoning-d", messages=[], max_tokens=50)


def test_remembers_adaptation_across_calls():
    client = ScriptedClient([
        _bad_request("Use 'max_completion_tokens' instead."),
        OK,
        OK,  # second chat_completion should succeed on the FIRST attempt
    ])
    chat_completion(client, model="reasoning-e", messages=[], max_tokens=50)
    chat_completion(client, model="reasoning-e", messages=[], max_tokens=50)
    # 3 scripted items consumed = 2 (first, adapted) + 1 (second, no retry).
    assert len(client.chat.completions.calls) == 3
    assert "max_completion_tokens" in client.chat.completions.calls[2]
