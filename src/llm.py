"""Provider-agnostic LLM wrapper.

This is the ONLY module that knows we talk to Groq via the OpenAI-compatible
SDK. Every rung calls `complete(messages, tools=None)` and receives an
`LLMResponse`; swapping providers (or the SDK) should touch nothing outside
this file. That isolation is the Phase 2 Definition of Done (§11).

Message format: plain OpenAI-style chat dicts, e.g.
    {"role": "system", "content": "..."}
    {"role": "user", "content": "..."}
Because Groq speaks the OpenAI wire format, this is also the native format —
so rungs never construct provider-specific objects. To continue a tool-calling
conversation, append `response.assistant_message` and then one
`tool_result_message(...)` per tool call before calling `complete` again.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from . import config


class LLMError(RuntimeError):
    """Raised when the provider call fails in a way callers should handle."""


class MissingAPIKeyError(LLMError):
    """Raised when no API key is configured in the environment."""


@dataclass
class ToolCall:
    """A single tool call requested by the model, normalized.

    `arguments` is already parsed from JSON into a dict, so rungs never touch
    the provider's raw string payload.
    """

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Normalized result of one `complete()` call.

    Attributes:
        content:   The assistant's text, or None if it only returned tool
                   calls.
        tool_calls: Zero or more normalized `ToolCall`s.
        input_tokens / output_tokens: From the provider's `usage` field;
                   metrics.py sums these across a rung.
        assistant_message: The assistant turn as an OpenAI-format dict, ready
                   to append to the conversation history for the next call.
        raw:       The untouched SDK response object (debugging only; rungs
                   should not depend on it).
    """

    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    assistant_message: dict[str, Any] = field(default_factory=dict)
    raw: Any = None

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)


# --- Client (lazy singleton) ------------------------------------------------

_client: Any = None


def _get_client() -> Any:
    """Build (once) and return the OpenAI-compatible client pointed at Groq.

    Imported lazily so that merely importing this module (e.g. in tests that
    monkeypatch `complete`) does not require the `openai` package or a key.
    """
    global _client
    if _client is not None:
        return _client

    api_key = config.get_api_key()
    if not api_key:
        raise MissingAPIKeyError(
            f"No API key found. Set {config.API_KEY_ENV_VAR} in your "
            f"environment (or .env) before calling the model."
        )

    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - env setup issue
        raise LLMError(
            "The 'openai' package is required (it provides the "
            "OpenAI-compatible client Groq uses). Install it from "
            "requirements.txt."
        ) from exc

    _client = OpenAI(api_key=api_key, base_url=config.GROQ_BASE_URL)
    return _client


# --- Normalization helpers --------------------------------------------------


def _parse_tool_calls(message: Any) -> list[ToolCall]:
    """Turn SDK tool-call objects into our normalized ToolCall list."""
    import json

    raw_calls = getattr(message, "tool_calls", None) or []
    parsed: list[ToolCall] = []
    for call in raw_calls:
        raw_args = call.function.arguments
        try:
            arguments = json.loads(raw_args) if raw_args else {}
        except (json.JSONDecodeError, TypeError):
            # Model emitted malformed JSON args; surface the raw string so the
            # rung can decide how to handle it rather than crashing here.
            arguments = {"_raw": raw_args}
        parsed.append(
            ToolCall(id=call.id, name=call.function.name, arguments=arguments)
        )
    return parsed


def _assistant_message_to_dict(message: Any) -> dict[str, Any]:
    """Serialize the SDK assistant message to an OpenAI-format history dict."""
    msg: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
    raw_calls = getattr(message, "tool_calls", None) or []
    if raw_calls:
        msg["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments,
                },
            }
            for call in raw_calls
        ]
    return msg


def tool_result_message(tool_call_id: str, content: str) -> dict[str, Any]:
    """Build the OpenAI-format `tool` message that feeds a result back.

    Rungs append one of these (per tool call) after `assistant_message` before
    the next `complete()` call. Keeps the wire format out of rung code.
    """
    return {"role": "tool", "tool_call_id": tool_call_id, "content": content}


# --- The one public entry point ---------------------------------------------


def complete(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    *,
    max_retries: int = 3,
) -> LLMResponse:
    """Call the model once and return a normalized `LLMResponse`.

    Args:
        messages: OpenAI-format chat messages.
        tools:    Optional OpenAI-format tool definitions. When provided, the
                  model may return tool calls (tool_choice="auto").
        max_retries: Transient errors (rate limits / 5xx) are retried with
                  exponential backoff. Groq's free tier is ~30 req/min, so a
                  little backoff keeps the demo from crashing mid-run (§9).

    Raises:
        MissingAPIKeyError: no key configured.
        LLMError:           the call failed after all retries.
    """
    client = _get_client()

    request: dict[str, Any] = {
        "model": config.MODEL,
        "messages": messages,
        "temperature": config.TEMPERATURE,
    }
    if tools:
        request["tools"] = tools
        request["tool_choice"] = "auto"

    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(**request)
            break
        except Exception as exc:  # noqa: BLE001 - normalize provider errors
            last_exc = exc
            if not _is_retryable(exc) or attempt == max_retries - 1:
                raise LLMError(f"LLM call failed: {exc}") from exc
            time.sleep(_backoff_seconds(attempt))
    else:  # pragma: no cover - loop always breaks or raises
        raise LLMError(f"LLM call failed: {last_exc}")

    choice = resp.choices[0]
    message = choice.message
    usage = resp.usage

    return LLMResponse(
        content=message.content,
        tool_calls=_parse_tool_calls(message),
        input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        assistant_message=_assistant_message_to_dict(message),
        raw=resp,
    )


def _is_retryable(exc: Exception) -> bool:
    """Retry on rate limits (429) and transient server errors (5xx)."""
    status = getattr(exc, "status_code", None)
    if status is None:
        # Some SDK errors expose the code on a nested response object.
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    if status == 429:
        return True
    if isinstance(status, int) and 500 <= status < 600:
        return True
    return False


def _backoff_seconds(attempt: int) -> float:
    """Exponential backoff: 1s, 2s, 4s, ..."""
    return float(2**attempt)
