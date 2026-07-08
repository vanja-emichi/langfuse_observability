"""Pure utility functions for Langfuse generation logging.

This module is self-contained: it owns the truncation constants, sensitive-key
patterns, model pricing table, and all format/normalize/extract helpers that
have no dependency on client state or contextvars.
"""

# ---------------------------------------------------------------------------
# Truncation limits — centralized for clarity and consistent tuning
# ---------------------------------------------------------------------------
MAX_GEN_OUTPUT_CHARS = 2000
MAX_ERROR_INFO_CHARS = 500
MAX_UTILITY_INPUT_CHARS = 1000
MAX_UTILITY_SYSTEM_CHARS = 500
MAX_UTILITY_OUTPUT_CHARS = 2000
MAX_JUDGE_USER_MSG_CHARS = 500
MAX_JUDGE_RESPONSE_CHARS = 1000
MAX_JUDGE_COMMENT_CHARS = 100
MAX_RETRY_ERROR_CHARS = 200
MAX_TOOL_ARG_CHARS = 500
MAX_INPUT_MESSAGES = 5
MAX_SYSTEM_PROMPT_CHARS = 500


# ---------------------------------------------------------------------------
# Sensitive Data Filtering
# ---------------------------------------------------------------------------

_SENSITIVE_KEY_PATTERNS = (
    "key", "token", "secret", "password", "passwd", "auth", "credential",
    "api_key", "apikey", "access_key", "private_key", "session_key",
)


# ---------------------------------------------------------------------------
# Cost Calculation
# ---------------------------------------------------------------------------

_MODEL_PRICING = {
    # Per 1M tokens, USD. Source: provider pricing pages.
    # ZAI (Zhipu) models
    "glm-5.2": {"input": 1.40, "output": 4.40},
    "glm-5.1": {"input": 0.60, "output": 2.20},
    # Venice AI - Claude models (source: api.venice.ai/api/v1/models)
    "claude-fable-5": {"input": 12.0, "output": 60.0, "cache_input": 1.2},
    "claude-sonnet-5": {"input": 3.0, "output": 15.0, "cache_input": 0.3},
    "claude-opus-4-8": {"input": 6.0, "output": 30.0, "cache_input": 0.6},
    "claude-opus-4-8-fast": {"input": 12.0, "output": 60.0, "cache_input": 1.2},
    "claude-opus-4-7": {"input": 6.0, "output": 30.0, "cache_input": 0.6},
    "claude-opus-4-7-fast": {"input": 36.0, "output": 180.0, "cache_input": 3.6},
    "claude-opus-4-6": {"input": 6.0, "output": 30.0, "cache_input": 0.6},
    "claude-opus-4-5": {"input": 6.0, "output": 30.0, "cache_input": 0.6},
    "claude-sonnet-4-6": {"input": 3.6, "output": 18.0, "cache_input": 0.36},
    "claude-sonnet-4-5": {"input": 3.75, "output": 18.75, "cache_input": 0.375},
}


def _get_attr_or_key(obj, key, dump_pydantic=True):
    """Get a value from a dict (via .get) or an object (via getattr).

    Optionally converts Pydantic models to dicts via model_dump().
    """
    val = obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)
    if dump_pydantic and val and hasattr(val, "model_dump"):
        val = val.model_dump()
    return val


def _normalize_usage(usage):
    """Normalize usage from Chat Completions or Responses API into Langfuse format.

    Captures reasoning and cached token details as separate usage types
    for granular cost tracking on reasoning models like glm-5.2.
    """
    # Extract main token counts (prompt_tokens/input_tokens are aliases)
    input_tokens = _get_attr_or_key(usage, "prompt_tokens") or _get_attr_or_key(usage, "input_tokens") or 0
    output_tokens = _get_attr_or_key(usage, "completion_tokens") or _get_attr_or_key(usage, "output_tokens") or 0
    total_tokens = _get_attr_or_key(usage, "total_tokens") or 0
    if not input_tokens and not output_tokens:
        return {}
    result = {
        "input": input_tokens,
        "output": output_tokens,
        "total": total_tokens,
        "unit": "TOKENS",
    }
    # Extract reasoning token details (glm-5.2, OpenAI o-series, etc.)
    details = _get_attr_or_key(usage, "completion_tokens_details")
    if details:
        reasoning = _get_attr_or_key(details, "reasoning_tokens", dump_pydantic=False) or 0
        if reasoning:
            result["reasoning"] = reasoning
    # Extract cached input token details
    prompt_details = _get_attr_or_key(usage, "prompt_tokens_details")
    if prompt_details:
        cached = _get_attr_or_key(prompt_details, "cached_tokens", dump_pydantic=False) or 0
        if cached:
            result["cached_input"] = cached
    return result


def _find_usage(chunk):
    """Extract usage from Chat Completions chunks or Responses API events."""
    if hasattr(chunk, "usage") and chunk.usage:
        return chunk.usage
    if hasattr(chunk, "get"):
        usage = chunk.get("usage")
        if usage:
            return usage
        response = chunk.get("response")
        if response:
            if hasattr(response, "usage") and response.usage:
                return response.usage
            if hasattr(response, "get"):
                usage = response.get("usage")
                if usage:
                    return usage
    if hasattr(chunk, "response") and chunk.response:
        resp = chunk.response
        if hasattr(resp, "usage") and resp.usage:
            return resp.usage
    return None


def _extract_delta_text(chunk):
    """Extract text delta from Chat Completions chunks or Responses API events."""
    # Chat Completions: choices[0].delta.content
    if hasattr(chunk, "choices") and chunk.choices:
        delta = getattr(chunk.choices[0], "delta", None)
        if delta:
            content = getattr(delta, "content", None)
            if content:
                return content
    elif hasattr(chunk, "get"):
        choices = chunk.get("choices", [])
        if choices and isinstance(choices[0], dict):
            delta = choices[0].get("delta", {})
            if isinstance(delta, dict) and delta.get("content"):
                return delta["content"]
    # Responses API: delta is a string on output_text.delta events
    if hasattr(chunk, "delta"):
        delta = chunk.delta
        if isinstance(delta, str) and delta:
            return delta
    elif hasattr(chunk, "get"):
        delta = chunk.get("delta")
        if isinstance(delta, str) and delta:
            return delta
    # Responses API: text attribute
    if hasattr(chunk, "text") and chunk.text:
        return chunk.text
    return None


# ---------------------------------------------------------------------------
# Prompt Formatting (ported from v1 langfuse_observability plugin)
# ---------------------------------------------------------------------------

def _is_sensitive_key(key) -> bool:
    key_lower = str(key).lower()
    return any(pat in key_lower for pat in _SENSITIVE_KEY_PATTERNS)


def _truncate_capture_string(value: str, max_val_len: int) -> str:
    value = value if isinstance(value, str) else str(value)
    return value[:max_val_len] if len(value) > max_val_len else value


def _sanitize_for_capture(value, max_val_len: int = MAX_TOOL_ARG_CHARS, key_hint=None):
    """Recursively redact sensitive keys and truncate captured values.

    Preserves dict/list structure so nested secrets stay redacted instead of being
    flattened into a single raw string.
    """
    if key_hint is not None and _is_sensitive_key(key_hint):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            k: _sanitize_for_capture(v, max_val_len=max_val_len, key_hint=k)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [
            _sanitize_for_capture(item, max_val_len=max_val_len)
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            _sanitize_for_capture(item, max_val_len=max_val_len)
            for item in value
        )
    if isinstance(value, str):
        return _truncate_capture_string(value, max_val_len)
    return value


def _stringify(content) -> str:
    """Convert any message content to a readable string."""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        if "raw_content" in content:
            preview = content.get("preview")
            if preview:
                return _truncate_capture_string(preview, MAX_TOOL_ARG_CHARS)
            sanitized = _sanitize_for_capture(content.get("raw_content", ""), max_val_len=MAX_TOOL_ARG_CHARS)
            return str(sanitized)
        sanitized = _sanitize_for_capture(content.get("content", content), max_val_len=MAX_TOOL_ARG_CHARS)
        return str(sanitized)
    if isinstance(content, list):
        parts = []
        for item in content:
            s = _stringify(item)
            if s:
                parts.append(s)
        return "\n".join(parts)
    return str(_sanitize_for_capture(content, max_val_len=MAX_TOOL_ARG_CHARS))


def _format_generation_input(messages, max_system_chars: int = MAX_SYSTEM_PROMPT_CHARS) -> str | list | None:
    """Build a clean, readable prompt for Langfuse UI.

    Return type contract:
    - None: when messages is falsy, empty, or produces no content after filtering
    - str: markdown-joined message sections for text-only messages,
           or when LangfuseMedia import fails (graceful fallback)
    - list[str | LangfuseMedia]: mixed text sections and image media objects
      when image_url content blocks are present and LangfuseMedia is available

    Only the first MAX_INPUT_MESSAGES messages are processed.
    System messages are truncated to max_system_chars for security/readability.
    """
    if not isinstance(messages, list) or not messages:
        return str(messages)[:MAX_GEN_OUTPUT_CHARS] if messages else None

    # Detect if any message has image_url content blocks
    has_images = False
    for msg in messages[:MAX_INPUT_MESSAGES]:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content", "")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "image_url":
                    has_images = True
                    break
        if has_images:
            break

    if not has_images:
        # Original text-only path
        sections = []
        for msg in messages[:MAX_INPUT_MESSAGES]:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role", "unknown")
            content = _stringify(msg.get("content", ""))
            if not content.strip():
                continue
            if role == "system":
                if len(content) > max_system_chars:
                    content = content[:max_system_chars] + f"\n... ({len(content)} chars total, truncated)"
                sections.append(f"# System\n\n{content}")
            elif role == "user":
                sections.append(f"# User\n\n{content}")
            elif role == "assistant":
                sections.append(f"# Assistant\n\n{content}")
            else:
                sections.append(f"# {role.title()}\n\n{content}")
        return "\n\n---\n\n".join(sections) if sections else None

    # Multi-modality path: build list of text sections + LangfuseMedia objects
    try:
        from langfuse.media import LangfuseMedia
    except Exception:
        # Graceful fallback: treat as text with truncated data URIs
        sections = []
        for msg in messages[:MAX_INPUT_MESSAGES]:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            parts.append(block.get("text", ""))
                        elif block.get("type") == "image_url":
                            url = block.get("image_url", {}).get("url", "")
                            parts.append(f"[image: {url[:50]}...]" if len(url) > 50 else f"[image: {url}]")
                content = "\n".join(parts)
            else:
                content = _stringify(content)
            if not content.strip():
                continue
            sections.append(f"# {role.title()}\n\n{content}")
        return "\n\n---\n\n".join(sections) if sections else None

    result = []
    for msg in messages[:MAX_INPUT_MESSAGES]:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, str):
            if content.strip():
                if role == "system" and len(content) > max_system_chars:
                    content = content[:max_system_chars] + f"\n... ({len(content)} chars total, truncated)"
                result.append(f"# {role.title()}\n\n{content}")
        elif isinstance(content, list):
            text_parts = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif block.get("type") == "image_url":
                    url = block.get("image_url", {}).get("url", "")
                    if url.startswith("data:"):
                        try:
                            media = LangfuseMedia(base64_data_uri=url)
                            result.append(media)
                        except Exception:
                            text_parts.append(f"[image: conversion failed]")
                    else:
                        text_parts.append(f"[image_url: {url[:80]}]")
            if text_parts:
                combined = "\n".join(text_parts)
                if combined.strip():
                    result.append(f"# {role.title()}\n\n{combined}")
    return result if result else None


def _filter_sensitive_args(args: dict, max_val_len: int = MAX_TOOL_ARG_CHARS) -> dict:
    """Filter sensitive keys and truncate values in tool arguments."""
    if not isinstance(args, dict):
        return args
    return _sanitize_for_capture(args, max_val_len=max_val_len)


def _compute_cost_details(model: str, usage: dict) -> dict | None:
    """Compute cost_details from token counts and known model pricing.

    Returns only numeric values — Langfuse requires cost_details to be
    Dict[str, float]. Do NOT include currency as a string value.

    Key naming: uses 'total' (NOT 'overall') so Langfuse's backend
    calculatedTotalCost aggregation recognizes the field.
    """
    if not usage or not model:
        return None
    base_model = model.split("/")[-1] if "/" in model else model
    pricing = _MODEL_PRICING.get(base_model)
    if not pricing:
        return None
    input_tokens = usage.get("input", 0)
    output_tokens = usage.get("output", 0)
    reasoning_tokens = usage.get("reasoning", 0)
    cached_tokens = usage.get("cached_input", 0)
    # Reasoning tokens are billed as output tokens
    billable_output = output_tokens + reasoning_tokens
    # Cached input tokens cost cache_input rate instead of input rate
    billable_input = input_tokens - cached_tokens if cached_tokens <= input_tokens else 0
    input_cost = (billable_input / 1_000_000) * pricing["input"]
    if "cache_input" in pricing and cached_tokens:
        input_cost += (cached_tokens / 1_000_000) * pricing["cache_input"]
    output_cost = (billable_output / 1_000_000) * pricing["output"]
    total_cost = input_cost + output_cost
    return {
        "input": round(input_cost, 6),
        "output": round(output_cost, 6),
        "total": round(total_cost, 6),
    }
