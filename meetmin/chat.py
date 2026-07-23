"""Model-compatible wrapper around Chat Completions.

Newer reasoning models (e.g. the gpt-5 / o-series) reject parameters the older
chat models accept: they require ``max_completion_tokens`` instead of
``max_tokens`` and only allow the default ``temperature``. Since meetmin aims to
work against arbitrary OpenAI-compatible endpoints, we don't hard-code a model
list — instead we try the classic parameters and, on a 400 that names the
offending parameter, adapt and retry, remembering the fix per model so it costs
at most one extra round-trip the first time.
"""

from __future__ import annotations

from openai import BadRequestError

# Learned per-model quirks, so adaptation happens once and is reused.
_TOKEN_PARAM: dict[str, str] = {}  # model -> "max_tokens" | "max_completion_tokens"
_ALLOW_TEMPERATURE: dict[str, bool] = {}  # model -> whether a custom temperature works


def chat_completion(
    client,
    *,
    model: str,
    messages: list,
    temperature: float | None = None,
    max_tokens: int | None = None,
    tools: list | None = None,
    tool_choice: str | None = None,
):
    """Call ``client.chat.completions.create`` with parameters the model accepts.

    Adapts ``max_tokens`` -> ``max_completion_tokens`` and drops an unsupported
    ``temperature`` on demand, based on the API's 400 error, and caches the
    outcome per model.
    """
    token_param = _TOKEN_PARAM.get(model, "max_tokens")
    allow_temperature = _ALLOW_TEMPERATURE.get(model, True)
    last_exc: BadRequestError | None = None

    for _ in range(3):
        kwargs: dict = {"model": model, "messages": messages}
        if max_tokens is not None:
            kwargs[token_param] = max_tokens
        if allow_temperature and temperature is not None:
            kwargs["temperature"] = temperature
        if tools is not None:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice or "auto"

        try:
            return client.chat.completions.create(**kwargs)
        except BadRequestError as exc:
            last_exc = exc
            msg = str(exc)
            adjusted = False
            if token_param == "max_tokens" and "max_completion_tokens" in msg:
                token_param = _TOKEN_PARAM[model] = "max_completion_tokens"
                adjusted = True
            if allow_temperature and "temperature" in msg:
                allow_temperature = _ALLOW_TEMPERATURE[model] = False
                adjusted = True
            if not adjusted:
                raise

    assert last_exc is not None
    raise last_exc
