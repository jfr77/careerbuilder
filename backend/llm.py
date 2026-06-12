"""The single LLM gateway for carreerbuilder.

Every Anthropic API call in the entire app goes through complete() below —
routers never import the anthropic SDK themselves, and the frontend never
calls the API. If ANTHROPIC_API_KEY is unset the app keeps working; LLM
features raise LLMUnavailable, which routes translate into a clear 503.
"""

import json
import os
import re

MODEL = "claude-sonnet-4-20250514"


class LLMUnavailable(Exception):
    """ANTHROPIC_API_KEY is not set."""


class LLMError(Exception):
    """The API call failed or returned something unusable."""


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


_client = None


def _get_client():
    global _client
    if not available():
        raise LLMUnavailable(
            "ANTHROPIC_API_KEY is not set — set it in the backend environment to enable LLM features."
        )
    if _client is None:
        import anthropic

        _client = anthropic.Anthropic()
    return _client


def complete(messages, system=None, tools=None, max_tokens=1500):
    """The one helper. messages: Anthropic-format list. Returns the API Message.

    Raises LLMUnavailable (no key) or LLMError (call failed).
    """
    client = _get_client()
    kwargs = {"model": MODEL, "max_tokens": max_tokens, "messages": messages}
    if system:
        kwargs["system"] = system
    if tools:
        kwargs["tools"] = tools
    try:
        return client.messages.create(**kwargs)
    except LLMUnavailable:
        raise
    except Exception as e:  # network, auth, rate limit — degrade gracefully
        raise LLMError(f"Anthropic API call failed: {e}") from e


def complete_text(prompt, system=None, max_tokens=1500) -> str:
    """Convenience wrapper around complete() for plain prompt→text calls."""
    msg = complete([{"role": "user", "content": prompt}], system=system, max_tokens=max_tokens)
    return "".join(b.text for b in msg.content if b.type == "text")


def complete_json(prompt, system=None, max_tokens=1500):
    """Prompt→parsed JSON, tolerating markdown fences around the payload."""
    text = complete_text(prompt, system=system, max_tokens=max_tokens)
    cleaned = re.sub(r"```(?:json)?|```", "", text).strip()
    # tolerate prose before/after the JSON object or array
    start = min((i for i in (cleaned.find("{"), cleaned.find("[")) if i != -1), default=-1)
    if start == -1:
        raise LLMError(f"LLM did not return JSON: {text[:200]}")
    end = max(cleaned.rfind("}"), cleaned.rfind("]"))
    try:
        return json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as e:
        raise LLMError(f"LLM returned invalid JSON: {e}") from e
