"""Langfuse v4 client singleton and LLM generation logger.

Creates traces/observations via the Langfuse SDK's own OTel pipeline.
LLM GENERATION observations are created manually via a LiteLLM CustomLogger
that uses the SDK trace_context parameter to link to our existing trace.
This avoids the separate-OTel-provider conflict that prevented trace merging
with langfuse_otel.
"""

import contextvars
import logging
import os
import random
import sys
from datetime import datetime

from typing import Any, Optional

logger = logging.getLogger(__name__)

_current_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("_current_trace_id", default="")
_current_session_id: contextvars.ContextVar[str] = contextvars.ContextVar("_current_session_id", default="")
_current_parent_obs: contextvars.ContextVar[Any] = contextvars.ContextVar("_current_parent_obs", default=None)
_current_iteration_span_id: contextvars.ContextVar[str] = contextvars.ContextVar("_current_iteration_span_id", default="")
_utility_llm_result: contextvars.ContextVar[Any] = contextvars.ContextVar("_utility_llm_result", default=None)
_current_loaded_skills: contextvars.ContextVar[str] = contextvars.ContextVar("_current_loaded_skills", default="")

_STREAM_ACLOSE_DRAIN_TIMEOUT_S = 0.25
_STREAM_ACLOSE_MAX_CHUNKS = 32
_FEEDBACK_TARGETS_KEY = "lf_feedback_targets"
_MAX_FEEDBACK_TARGETS = 256

# Load pure helpers from _helpers.py (truncation constants, cost tables, format/extract functions)
import importlib.util as _ilu
_sk = "_a0_langfuse_lib__helpers"
if _sk not in sys.modules:
    _sp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_helpers.py")
    _spec = _ilu.spec_from_file_location(_sk, _sp)
    sys.modules[_sk] = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(sys.modules[_sk])
_h = sys.modules[_sk]

# Re-export helper constants for module-level access (backward compat for extensions/tests)
MAX_GEN_OUTPUT_CHARS = _h.MAX_GEN_OUTPUT_CHARS
MAX_ERROR_INFO_CHARS = _h.MAX_ERROR_INFO_CHARS
MAX_UTILITY_INPUT_CHARS = _h.MAX_UTILITY_INPUT_CHARS
MAX_UTILITY_SYSTEM_CHARS = _h.MAX_UTILITY_SYSTEM_CHARS
MAX_UTILITY_OUTPUT_CHARS = _h.MAX_UTILITY_OUTPUT_CHARS
MAX_JUDGE_USER_MSG_CHARS = _h.MAX_JUDGE_USER_MSG_CHARS
MAX_JUDGE_RESPONSE_CHARS = _h.MAX_JUDGE_RESPONSE_CHARS
MAX_JUDGE_COMMENT_CHARS = _h.MAX_JUDGE_COMMENT_CHARS
MAX_RETRY_ERROR_CHARS = _h.MAX_RETRY_ERROR_CHARS
MAX_TOOL_ARG_CHARS = _h.MAX_TOOL_ARG_CHARS
MAX_INPUT_MESSAGES = _h.MAX_INPUT_MESSAGES
MAX_SYSTEM_PROMPT_CHARS = _h.MAX_SYSTEM_PROMPT_CHARS
_SENSITIVE_KEY_PATTERNS = _h._SENSITIVE_KEY_PATTERNS
_MODEL_PRICING = _h._MODEL_PRICING


def set_trace_context(trace_id: str, session_id: str) -> None:
    _current_trace_id.set(trace_id)
    _current_session_id.set(session_id)


def clear_trace_context() -> None:
    _current_trace_id.set("")
    _current_session_id.set("")
    _current_parent_obs.set(None)
    _current_iteration_span_id.set("")
    _utility_llm_result.set(None)


def set_parent_observation(obs) -> None:
    """Set the current iteration/span observation so GENERATION children nest under it."""
    _current_parent_obs.set(obs)


def clear_parent_observation() -> None:
    _current_parent_obs.set(None)


def set_iteration_span_id(span_id: str) -> None:
    """Store the current iteration's span_id so GENERATION observations can nest under it."""
    _current_iteration_span_id.set(span_id)


def get_iteration_span_id() -> str:
    """Return the current iteration's span_id, or empty string if not set."""
    return _current_iteration_span_id.get("")


def clear_iteration_span_id() -> None:
    _current_iteration_span_id.set("")


def set_loaded_skills(skills: str) -> None:
    _current_loaded_skills.set(skills)


def get_loaded_skills() -> str:
    return _current_loaded_skills.get("")


def clear_loaded_skills() -> None:
    _current_loaded_skills.set("")


def remember_feedback_target(agent, trace_id: str, log_no: int | None = None, message_id: str | None = None) -> None:
    """Persist a bounded server-side mapping from assistant message identity to trace_id."""
    try:
        if not agent or not trace_id:
            return
        normalized_message_id = str(message_id or "").strip()
        normalized_log_no = int(log_no) if log_no is not None and str(log_no) != "" else None
        if normalized_log_no is None and not normalized_message_id:
            return
        entries = agent.get_data(_FEEDBACK_TARGETS_KEY) or []
        if not isinstance(entries, list):
            entries = []
        filtered = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            same_log = normalized_log_no is not None and entry.get("log_no") == normalized_log_no
            same_msg = normalized_message_id and entry.get("message_id") == normalized_message_id
            if same_log or same_msg:
                continue
            filtered.append(entry)
        filtered.append({
            "trace_id": trace_id,
            "log_no": normalized_log_no,
            "message_id": normalized_message_id,
        })
        if len(filtered) > _MAX_FEEDBACK_TARGETS:
            filtered = filtered[-_MAX_FEEDBACK_TARGETS:]
        agent.set_data(_FEEDBACK_TARGETS_KEY, filtered)
    except Exception:
        pass


def resolve_feedback_target(agent, log_no: int | None = None, message_id: str | None = None) -> str:
    """Resolve the trace_id for a specific assistant message identity stored server-side."""
    try:
        if not agent:
            return ""
        normalized_message_id = str(message_id or "").strip()
        normalized_log_no = int(log_no) if log_no is not None and str(log_no) != "" else None
        if normalized_log_no is None and not normalized_message_id:
            return ""
        entries = agent.get_data(_FEEDBACK_TARGETS_KEY) or []
        if not isinstance(entries, list):
            return ""

        trace_from_log = ""
        trace_from_msg = ""
        for entry in reversed(entries):
            if not isinstance(entry, dict):
                continue
            if normalized_log_no is not None and entry.get("log_no") == normalized_log_no and not trace_from_log:
                trace_from_log = str(entry.get("trace_id") or "")
            if normalized_message_id and entry.get("message_id") == normalized_message_id and not trace_from_msg:
                trace_from_msg = str(entry.get("trace_id") or "")
            if (normalized_log_no is None or trace_from_log) and (not normalized_message_id or trace_from_msg):
                break

        if normalized_log_no is not None and normalized_message_id:
            if not trace_from_log or not trace_from_msg or trace_from_log != trace_from_msg:
                return ""
            return trace_from_log
        return trace_from_log or trace_from_msg
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Config Resolution
# ---------------------------------------------------------------------------

_config_cache = None


def get_langfuse_config() -> dict[str, Any]:
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    from helpers.plugins import get_plugin_config
    config = get_plugin_config("a0_langfuse", None) or {}
    env_public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    env_secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")
    config_public_key = config.get("langfuse_public_key")
    config_secret_key = config.get("langfuse_secret_key")
    public_key = config_public_key or env_public_key
    secret_key = config_secret_key or env_secret_key
    host = config.get("langfuse_host") or os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    enabled = config.get("langfuse_enabled", False)
    sample_rate = float(config.get("langfuse_sample_rate", 1.0))
    flush_at = int(config.get("langfuse_flush_at", 15))
    flush_interval = float(config.get("langfuse_flush_interval", 5.0))
    environment = config.get("langfuse_environment") or os.getenv("LANGFUSE_TRACING_ENVIRONMENT", "")
    if not environment:
        try:
            if "--dockerized=true" in sys.argv or "--dockerized=True" in sys.argv:
                environment = "production"
            else:
                environment = "development"
        except Exception:
            environment = "production"
    # Only auto-enable when keys come from env vars (legacy convenience),
    # NOT from plugin config — explicit config must set langfuse_enabled: true
    if not enabled and not config_public_key and not config_secret_key and env_public_key and env_secret_key:
        enabled = True
    _config_cache = {
        "enabled": enabled, "public_key": public_key, "secret_key": secret_key,
        "host": host, "sample_rate": sample_rate,
        "flush_at": flush_at, "flush_interval": flush_interval,
        "environment": environment,
    }
    return _config_cache


# ---------------------------------------------------------------------------
# Client Lifecycle Globals
# ---------------------------------------------------------------------------

_client = None
_client_initialized = False
_callbacks_registered = False
_generation_logger = None
_original_acompletion = None
_original_completion = None
_original_aresponses = None
_original_responses = None
_original_transport_acomplete = None
_original_transport_astream = None
_original_models_unified_call = None
_original_models_unified_turn = None


def _get_release() -> Optional[str]:
    """Return the A0 version string for Langfuse release tagging.

    Returns None if helpers.settings is unavailable or version cannot be read.
    Never raises - observability must never break A0.
    """
    try:
        settings_mod = sys.modules.get("helpers.settings")
        if settings_mod is None:
            from helpers import settings as settings_mod  # type: ignore
        s = settings_mod.get_settings()
        if isinstance(s, dict):
            return s.get("version")
        return getattr(s, "version", None)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Task 2: Implicit Feedback Scores (module-level dedup set)
# ---------------------------------------------------------------------------

_scored_trace_ids: dict = {}  # bounded LRU-like cache, see _mark_scored
_MAX_SCORED_CACHE = 1000


def _mark_scored(trace_id: str) -> None:
    """Track scored trace IDs with bounded cache to prevent memory leak."""
    _scored_trace_ids[trace_id] = True
    if len(_scored_trace_ids) > _MAX_SCORED_CACHE:
        # Remove oldest 20% to amortize cleanup cost
        trim = int(_MAX_SCORED_CACHE * 0.2)
        for key in list(_scored_trace_ids.keys())[:trim]:
            _scored_trace_ids.pop(key, None)


def handle_monologue_start_feedback(agent) -> None:
    """Score the previous trace as implicit feedback at the start of a new monologue.

    Completion-flag pattern (Task 2): 'lf_pending_trace_id' is set when a trace
    starts and cleared only by normal completion in monologue_end. If it is
    still set here, the previous task was killed/stopped -> score 0.
    Otherwise, if 'lf_last_trace_id' is set (previous trace completed normally
    and the user sent a new message), that is a positive follow-up signal.
    Uses module-level _scored_trace_ids set for deduplication across subordinates.
    Never raises - observability must never break A0.
    """
    try:
        client = get_client()
        if not client:
            return
        pending_trace_id = agent.get_data("lf_pending_trace_id")
        if pending_trace_id and pending_trace_id not in _scored_trace_ids:
            _mark_scored(pending_trace_id)
            client.create_score(
                trace_id=pending_trace_id, name="user-stopped", value=0, data_type="BOOLEAN"
            )
            agent.set_data("lf_pending_trace_id", None)
            return
        last_trace_id = agent.get_data("lf_last_trace_id")
        if last_trace_id and last_trace_id not in _scored_trace_ids:
            _mark_scored(last_trace_id)
            client.create_score(
                trace_id=last_trace_id, name="user-followup", value=1, data_type="BOOLEAN"
            )
            agent.set_data("lf_last_trace_id", None)
    except Exception as e:
        logger.debug(f"Implicit feedback scoring failed: {e}")


# ---------------------------------------------------------------------------
# Task 3: Error & Quality Signal Scoring (current-trace BOOLEAN scores)
# ---------------------------------------------------------------------------

_QUALITY_SIGNAL_PATTERNS = (
    ("misformat", "did not match the required schema"),
    ("repeat", "sent the same message again"),
    ("tool-not-found", "not found. Available tools"),
    ("critical-error", "This error has occurred:"),
)


def score_framework_error(message: str) -> None:
    """Score framework-error=0 (BOOLEAN) on the current trace via error_format hook.

    Never raises - observability must never break A0 error recovery.
    """
    try:
        trace_id = _current_trace_id.get("")
        if not trace_id:
            return
        client = get_client()
        if not client:
            return
        client.create_score(
            trace_id=trace_id, name="framework-error", value=0,
            data_type="BOOLEAN", comment=message,
        )
    except Exception as e:
        logger.debug(f"Framework error scoring failed: {e}")


def score_quality_signal(content: str) -> None:
    """Match hist_add_before content against 4 verified quality signal patterns.

    Scores the first matching signal 0 (BOOLEAN) on the current trace.
    No match -> no score. Never raises.
    """
    try:
        if not content:
            return
        trace_id = _current_trace_id.get("")
        if not trace_id:
            return
        for name, pattern in _QUALITY_SIGNAL_PATTERNS:
            if pattern in content:
                client = get_client()
                if not client:
                    return
                client.create_score(
                    trace_id=trace_id, name=name, value=0,
                    data_type="BOOLEAN", comment=None,
                )
                return
    except Exception as e:
        logger.debug(f"Quality signal scoring failed: {e}")


def capture_raw_exception(location: str, exception: BaseException) -> None:
    """Score raw-exception=0 (BOOLEAN) on the current trace with location + exception info.

    Complements score_framework_error (which only fires for RepairableException)
    by capturing ALL exceptions via handle_exception/end/. Never raises.
    """
    try:
        trace_id = _current_trace_id.get("")
        if not trace_id:
            return
        client = get_client()
        if not client:
            return
        comment = f"{location}: {type(exception).__name__}: {exception}"[:MAX_ERROR_INFO_CHARS]
        client.create_score(
            trace_id=trace_id, name="raw-exception", value=0,
            data_type="BOOLEAN", comment=comment,
        )
    except Exception as e:
        logger.debug(f"Raw exception capture failed: {e}")


# ---------------------------------------------------------------------------
# v3 Narrative Tap: Log.log() metadata builder
# ---------------------------------------------------------------------------

MAX_LOG_HEADING_CHARS = 200
MAX_LOG_CONTENT_CHARS = 500
MAX_LOG_KVPS_CHARS = 500


def _build_log_metadata(log_type, heading="", content="", kvps=None):
    """Build sanitized Langfuse metadata dict from a Log.log() call.

    Transforms narrative log entries into structured metadata for SPAN
    observations. All string fields are passed through _sanitize_for_capture
    from _helpers.py for sensitive-data filtering.
    """
    meta = {
        "log_type": str(log_type or "")[:MAX_LOG_HEADING_CHARS],
        "heading": str(_h._sanitize_for_capture(str(heading or ""), max_val_len=MAX_LOG_HEADING_CHARS)),
    }

    if content:
        meta["content"] = str(_h._sanitize_for_capture(str(content), max_val_len=MAX_LOG_CONTENT_CHARS))[:MAX_LOG_CONTENT_CHARS]

    if kvps:
        try:
            sanitized = _h._sanitize_for_capture(kvps, max_val_len=MAX_LOG_KVPS_CHARS)
            meta["kvps"] = sanitized
        except Exception:
            meta["kvps"] = "<sanitization_failed>"

    return meta


# ---------------------------------------------------------------------------
# Task 6: API Fallback Detection + Process Chain Completion

# ---------------------------------------------------------------------------

_api_fallback: contextvars.ContextVar = contextvars.ContextVar("_api_fallback", default=False)
_chain_start_time: contextvars.ContextVar = contextvars.ContextVar("_chain_start_time", default=None)


def set_api_fallback() -> None:
    """Mark that a Responses API → Chat Completions fallback occurred.
    Called from _wrapped_aresponses error handler or transport fallback detection.
    Never raises.
    """
    try:
        _api_fallback.set(True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Task 5: Utility Model Call Tracking (background LLM call SPANs)
# ---------------------------------------------------------------------------

_util_span: contextvars.ContextVar = contextvars.ContextVar("_util_span", default=None)


def start_util_model_span(call_data: dict) -> None:
    """Create a SPAN observation for a utility model call (chat naming, skill
    search, compression). Uses current parent observation if available, else
    client root. Stores span in _util_span contextvar for end_util_model_span.
    Never raises.
    """
    try:
        if not _current_trace_id.get(""):
            return
        _utility_llm_result.set(None)
        client = get_client()
        if not client:
            return
        message = _sanitize_for_capture(call_data.get("message", ""), max_val_len=MAX_UTILITY_INPUT_CHARS)
        system = _sanitize_for_capture(call_data.get("system", ""), max_val_len=MAX_UTILITY_SYSTEM_CHARS)
        parent = _current_parent_obs.get()
        if parent:
            obs = parent.start_observation(
                name="utility-model",
                as_type="span",
                input=message,
                metadata={"system": system, "background": call_data.get("background", False)},
            )
        else:
            obs = client.start_as_current_observation(
                name="utility-model",
                as_type="span",
                input=message,
                metadata={"system": system, "background": call_data.get("background", False)},
            )
            obs = obs.__enter__()
        _util_span.set(obs)
    except Exception as e:
        logger.debug(f"Utility model span start failed: {e}")


def end_util_model_span(call_data: dict, response: str) -> None:
    """Update output and end the utility model SPAN. Never raises.
    """
    try:
        obs = _util_span.get()
        if not obs:
            return
        safe_output = _sanitize_for_capture(response, max_val_len=MAX_UTILITY_OUTPUT_CHARS)
        output = safe_output if isinstance(safe_output, str) else str(safe_output)
        llm_result = _utility_llm_result.get()
        provider_model_key = ""
        usage_details = None
        cost_details = None
        if llm_result:
            provider_model_key = str(getattr(llm_result, "provider_model_key", "") or "")
            raw_usage = getattr(llm_result, "usage", None) or {}
            usage_details = _normalize_usage(raw_usage) if raw_usage else None
        if not provider_model_key:
            model_obj = call_data.get("model") if isinstance(call_data, dict) else None
            provider_model_key = str(getattr(model_obj, "model_name", "") or getattr(model_obj, "name", "") or "")
        model_name = provider_model_key.split("/")[-1] if "/" in provider_model_key else provider_model_key
        if model_name and usage_details:
            cost_details = _compute_cost_details(model_name, usage_details)
        obs.update(
            output=output,
            metadata={
                "background": bool(call_data.get("background", False)) if isinstance(call_data, dict) else False,
                "provider_model_key": provider_model_key,
                "usage": usage_details,
                "cost_details": cost_details,
            },
        )
        obs.end()
        _util_span.set(None)
        _utility_llm_result.set(None)
    except Exception as e:
        logger.debug(f"Utility model span end failed: {e}")


# ---------------------------------------------------------------------------
# Task 10: Prompt Sync Bridge (upload A0 prompts + optional override)
# ---------------------------------------------------------------------------


def upload_prompt(name: str, sections: list) -> None:
    """Upload assembled prompt sections to Langfuse prompt management.

    Joins sections and creates a text prompt in Langfuse with production label.
    Never raises - prompt sync is best-effort.
    """
    try:
        client = get_client()
        if not client:
            return
        prompt_text = "\n\n".join(str(s) for s in sections if s)
        client.create_prompt(
            name=name,
            prompt=prompt_text,
            type="text",
            labels=["production"],
            tags=["agent-zero", "auto-synced"],
        )
    except Exception as e:
        logger.debug(f"Prompt upload failed: {e}")


def apply_prompt_override(name: str, sections: list, mode: str = "replace") -> list:
    """Download and apply a Langfuse prompt override to A0 prompt sections.

    Modes:
    - replace: replaces the first (main) section with the Langfuse prompt
    - prepend: inserts the Langfuse prompt as a new first section

    Returns the (possibly modified) sections list. Never raises.
    """
    try:
        client = get_client()
        if not client:
            return sections
        prompt = client.get_prompt(name=name, type="text")
        override_text = getattr(prompt, "prompt", None) or ""
        if not override_text:
            return sections
        if mode == "replace":
            if sections:
                sections[0] = override_text
            else:
                sections = [override_text]
        elif mode == "prepend":
            sections.insert(0, override_text)
        return sections
    except Exception as e:
        logger.debug(f"Prompt override failed: {e}")
        return sections


# ---------------------------------------------------------------------------
# Task 11: LLM-as-a-Judge (glm-5.2 quality evaluation on sampled traces)
# ---------------------------------------------------------------------------

async def run_judge_evaluation(user_message: str, agent_response: str) -> None:
    """Evaluate response quality using glm-5.2 and create a NUMERIC score.

    Uses litellm.acompletion() with A0's provider config. Creates quality-judge
    NUMERIC score (0.0-1.0) on current trace. Disabled by default — requires
    langfuse_judge_enabled: true and langfuse_judge_sample_rate > 0.0 in config.
    Never raises.
    """
    try:
        config = get_langfuse_config()
        if not config.get("langfuse_judge_enabled", False):
            return
        sample_rate = float(config.get("langfuse_judge_sample_rate", 0.0))
        if sample_rate <= 0.0:
            return
        if sample_rate < 1.0 and random.random() >= sample_rate:
            return
        trace_id = _current_trace_id.get("")
        if not trace_id:
            return
        client = get_client()
        if not client:
            return

        import litellm
        judge_prompt = (
            "You are a quality evaluator. Score the following AI response on a scale of 0.0 to 1.0. "
            "Respond with ONLY a single decimal number between 0.0 and 1.0.\n\n"
            f"User question: {user_message[:MAX_JUDGE_USER_MSG_CHARS]}\n\n"
            f"AI response: {agent_response[:MAX_JUDGE_RESPONSE_CHARS]}\n\n"
            "Score (0.0-1.0):"
        )
        response = await litellm.acompletion(
            model="glm-5.2",
            messages=[{"role": "user", "content": judge_prompt}],
            temperature=0.0,
            max_tokens=10,
        )
        score_text = response.choices[0].message.content.strip()
        try:
            score = float(score_text)
            score = max(0.0, min(1.0, score))
        except ValueError:
            score = 0.5

        client.create_score(
            trace_id=trace_id, name="quality-judge", value=score,
            data_type="NUMERIC",
            comment=f"LLM judge evaluation: {score_text[:MAX_JUDGE_COMMENT_CHARS]}",
        )
    except Exception as e:
        logger.debug(f"Judge evaluation failed: {e}")

_TOOL_CATEGORY_MAP = {
    "code_execution_tool": "coding",
    "code_execution_remote": "coding",
    "text_editor": "coding",
    "text_editor_remote": "coding",
    "search_engine": "research",
    "call_subordinate": "delegation",
    "office_artifact": "document",
    "browser": "browsing",
}


def add_feature_tags(trace_id: str, tool_names: list) -> None:
    """Map tool names to feature categories and tag the trace via ingestion.

    Uses the private _create_trace_tags_via_ingestion (VERIFIED: SDK v4 has no
    public update_current_trace; batch_evaluation.py uses the same private method).
    Never raises.
    """
    try:
        if not trace_id:
            return
        categories = set()
        for tool in tool_names:
            cat = _TOOL_CATEGORY_MAP.get(tool)
            if cat:
                categories.add(cat)
        if not categories:
            categories.add("conversation")
        if _api_fallback.get():
            categories.add("api-fallback")
            _api_fallback.set(False)
        client = get_client()
        if not client:
            return
        if hasattr(client, "_create_trace_tags_via_ingestion"):
            client._create_trace_tags_via_ingestion(
                trace_id=trace_id, tags=sorted(categories)
            )
    except Exception as e:
        logger.debug(f"Feature tag ingestion failed: {e}")


# ---------------------------------------------------------------------------
# Dataset Export
# ---------------------------------------------------------------------------

def export_dataset_item(
    dataset_name: str,
    input_data,
    expected_output,
    trace_id: str,
    metadata=None,
) -> None:
    """Export a trace as a dataset item for future experiments. Never raises."""
    try:
        if not dataset_name or not trace_id:
            return
        client = get_client()
        if not client:
            return
        client.create_dataset_item(
            dataset_name=dataset_name,
            input=input_data,
            expected_output=expected_output,
            source_trace_id=trace_id,
            metadata=metadata or {},
        )
        logger.debug(
            f"Dataset item exported to '{dataset_name}' from trace {trace_id[:12]}"
        )
    except Exception as e:
        logger.debug(f"Dataset item export failed: {e}")


# ---------------------------------------------------------------------------
# Gap 2: Rate Limiting & Retry Tracking
# ---------------------------------------------------------------------------

_original_apply_rate_limiter = None
_original_apply_rate_limiter_sync = None


def track_rate_limit(model_key: str, current: int, limit: int) -> None:
    """Score rate-limit event on current trace. Never raises."""
    try:
        trace_id = _current_trace_id.get("")
        if not trace_id:
            return
        client = get_client()
        if not client:
            return
        client.create_score(
            trace_id=trace_id, name="rate-limited", value=0,
            data_type="BOOLEAN",
            comment=f"{model_key}: {current}/{limit}",
        )
        _api_fallback.set(True)  # reuse tag mechanism for trace tagging
    except Exception as e:
        logger.debug(f"Rate limit tracking failed: {e}")


def track_retry(attempt: int, error: str) -> None:
    """Score retry event on current trace. Never raises."""
    try:
        trace_id = _current_trace_id.get("")
        if not trace_id:
            return
        client = get_client()
        if not client:
            return
        client.create_score(
            trace_id=trace_id, name="retry-attempted", value=float(attempt),
            data_type="NUMERIC",
            comment=f"Attempt {attempt}: {error[:MAX_RETRY_ERROR_CHARS]}",
        )
    except Exception as e:
        logger.debug(f"Retry tracking failed: {e}")


def _wrap_rate_limiters() -> None:
    """Wrap apply_rate_limiter functions to detect rate limiting events."""
    global _original_apply_rate_limiter, _original_apply_rate_limiter_sync
    try:
        models_mod = sys.modules.get("models")
        if models_mod is None:
            return
        if _original_apply_rate_limiter is not None:
            return  # Already wrapped

        if hasattr(models_mod, "apply_rate_limiter"):
            _original_apply_rate_limiter = models_mod.apply_rate_limiter

            async def _wrapped_rate_limiter(model_config, input_text, rate_limiter_callback=None):
                async def _tracking_callback(msg, key, current, limit):
                    track_rate_limit(key, current, limit)
                    if rate_limiter_callback:
                        return await rate_limiter_callback(msg, key, current, limit)
                    return False
                return await _original_apply_rate_limiter(model_config, input_text, _tracking_callback)
            models_mod.apply_rate_limiter = _wrapped_rate_limiter

        if hasattr(models_mod, "apply_rate_limiter_sync"):
            _original_apply_rate_limiter_sync = models_mod.apply_rate_limiter_sync

            def _wrapped_rate_limiter_sync(model_config, input_text, rate_limiter_callback=None):
                def _tracking_callback(msg, key, current, limit):
                    track_rate_limit(key, current, limit)
                    if rate_limiter_callback:
                        return rate_limiter_callback(msg, key, current, limit)
                    return False
                return _original_apply_rate_limiter_sync(model_config, input_text, _tracking_callback)
            models_mod.apply_rate_limiter_sync = _wrapped_rate_limiter_sync
    except Exception as e:
        logger.debug(f"Rate limiter wrapping failed: {e}")


def _is_transient_retry_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code in (408, 429, 500, 502, 503, 504) or status_code >= 500
    return False


def _wrap_transport_tracking() -> None:
    """Attach retry/utility tracking to the real LiteLLMTransport async call path."""
    global _original_transport_acomplete, _original_transport_astream
    try:
        transport_mod = sys.modules.get("helpers.litellm_transport")
        if transport_mod is None:
            import helpers.litellm_transport as transport_mod  # type: ignore
        transport_cls = getattr(transport_mod, "LiteLLMTransport", None)
        if transport_cls is None:
            return

        if _original_transport_acomplete is None and hasattr(transport_cls, "acomplete"):
            _original_transport_acomplete = transport_cls.acomplete

            async def _tracked_acomplete(self, *args, **kwargs):
                call_index = int(getattr(self, "_lf_retry_call_index", 0) or 0) + 1
                setattr(self, "_lf_retry_call_index", call_index)
                try:
                    result = await _original_transport_acomplete(self, *args, **kwargs)
                    # Reset counter on success so retries report accurate attempt numbers
                    setattr(self, "_lf_retry_call_index", 0)
                    if getattr(self, "last_result", None) is not None:
                        _utility_llm_result.set(self.last_result)
                    return result
                except Exception as e:
                    if _is_transient_retry_error(e):
                        track_retry(call_index + 1, f"{type(e).__name__}: {e}")
                    raise

            transport_cls.acomplete = _tracked_acomplete

        if _original_transport_astream is None and hasattr(transport_cls, "astream"):
            _original_transport_astream = transport_cls.astream

            async def _tracked_astream(self, *args, **kwargs):
                call_index = int(getattr(self, "_lf_retry_call_index", 0) or 0) + 1
                setattr(self, "_lf_retry_call_index", call_index)
                try:
                    async for chunk in _original_transport_astream(self, *args, **kwargs):
                        yield chunk
                    # Reset counter on success so retries report accurate attempt numbers
                    setattr(self, "_lf_retry_call_index", 0)
                    if getattr(self, "last_result", None) is not None:
                        _utility_llm_result.set(self.last_result)
                except Exception as e:
                    if _is_transient_retry_error(e):
                        track_retry(call_index + 1, f"{type(e).__name__}: {e}")
                    raise

            transport_cls.astream = _tracked_astream
    except Exception as e:
        logger.debug(f"Transport tracking wrap failed: {e}")


def get_client():
    """Return the Langfuse singleton client, initializing on first call."""
    global _client, _client_initialized
    config = get_langfuse_config()
    if not config["enabled"] or not config["public_key"] or not config["secret_key"]:
        _client = None
        _client_initialized = False
        return None
    if _client_initialized and _client is not None:
        return _client
    try:
        from langfuse import Langfuse
        _client = Langfuse(
            public_key=config["public_key"],
            secret_key=config["secret_key"],
            host=config["host"],
            flush_at=config["flush_at"],
            flush_interval=config["flush_interval"],
            environment=config["environment"],
            release=_get_release(),
        )
        _client_initialized = True
        _register_callbacks()
        logger.info("Langfuse v4 client initialized")
        return _client
    except ImportError:
        logger.warning("langfuse package not installed")
        _client = None
        _client_initialized = False
        return None
    except Exception as e:
        logger.warning(f"Failed to initialize Langfuse: {e}")
        _client = None
        _client_initialized = False
        return None


def reset_client():
    """Flush and tear down the client, remove all callbacks, restore originals."""
    global _client, _client_initialized, _config_cache, _callbacks_registered
    global _generation_logger, _original_acompletion, _original_completion
    global _original_aresponses, _original_responses
    global _original_transport_acomplete, _original_transport_astream
    if _client:
        try:
            _client.flush()
        except Exception as e:
            logger.debug(f"Flush error: {e}")
    _client = None
    _client_initialized = False
    _config_cache = None
    try:
        import litellm
        if _generation_logger is not None:
            litellm.logging_callback_manager.remove_callback_from_list_by_object(
                litellm.success_callback, _generation_logger, require_self=False)
            litellm.logging_callback_manager.remove_callback_from_list_by_object(
                litellm.failure_callback, _generation_logger, require_self=False)
            litellm.logging_callback_manager.remove_callback_from_list_by_object(
                litellm._async_success_callback, _generation_logger, require_self=False)
            litellm.logging_callback_manager.remove_callback_from_list_by_object(
                litellm._async_failure_callback, _generation_logger, require_self=False)
            _generation_logger = None
        _callbacks_registered = False
        # Restore transport module local references FIRST (before clearing globals)
        lt = sys.modules.get('helpers.litellm_transport')
        if lt is not None:
            if _original_acompletion is not None and hasattr(lt, 'acompletion'):
                lt.acompletion = _original_acompletion
            if _original_completion is not None and hasattr(lt, 'completion'):
                lt.completion = _original_completion
            if _original_aresponses is not None and hasattr(lt, 'aresponses'):
                lt.aresponses = _original_aresponses
            if _original_responses is not None and hasattr(lt, 'responses'):
                lt.responses = _original_responses
        # Restore original litellm module functions and clear globals
        if _original_acompletion is not None:
            litellm.acompletion = _original_acompletion
            _original_acompletion = None
        if _original_completion is not None:
            litellm.completion = _original_completion
            _original_completion = None
        if _original_aresponses is not None:
            litellm.aresponses = _original_aresponses
            _original_aresponses = None
        if _original_responses is not None:
            litellm.responses = _original_responses
            _original_responses = None
        transport_mod = sys.modules.get('helpers.litellm_transport')
        if transport_mod is not None:
            transport_cls = getattr(transport_mod, 'LiteLLMTransport', None)
            if transport_cls is not None:
                if _original_transport_acomplete is not None:
                    transport_cls.acomplete = _original_transport_acomplete
                    _original_transport_acomplete = None
                if _original_transport_astream is not None:
                    transport_cls.astream = _original_transport_astream
                    _original_transport_astream = None
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

def should_sample() -> bool:
    rate = get_langfuse_config().get("sample_rate", 1.0)
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    return random.random() < rate


# ---------------------------------------------------------------------------
# Helpers — imported from _helpers.py, re-exported for backward compatibility
# ---------------------------------------------------------------------------
_get_attr_or_key = _h._get_attr_or_key
_normalize_usage = _h._normalize_usage
_find_usage = _h._find_usage
_extract_delta_text = _h._extract_delta_text
_stringify = _h._stringify
_format_generation_input = _h._format_generation_input
_sanitize_for_capture = _h._sanitize_for_capture
_filter_sensitive_args = _h._filter_sensitive_args
_compute_cost_details = _h._compute_cost_details


# ---------------------------------------------------------------------------
# Streaming Generation Wrapper
# ---------------------------------------------------------------------------

class _StreamingGenerationWrapper:
    """Wraps a streaming response iterator to capture usage and create GENERATION on completion.

    The observation context is entered at wrapper creation time (before streaming
    starts) to capture accurate start/end latency. Model, usage, and cost data
    are added via .update() when the stream completes.

    A0's LiteLLMTransport consumes streaming iterators directly, which prevents
    LiteLLM's success callbacks from firing. This wrapper intercepts each chunk,
    accumulates usage and output data, and updates the GENERATION observation
    when the iterator is exhausted.
    """

    def __init__(self, iterator, kwargs, trace_id, is_async=True):
        self._iterator = iterator
        self._kwargs = kwargs
        self._trace_id = trace_id
        self._is_async = is_async
        self._usage = {}
        self._model = kwargs.get("model", "unknown")
        self._output_parts = []
        self._generation_finalized = False
        self._first_chunk_time: Optional[datetime] = None
        self._obs = None
        self._obs_cm = None

        # Create and enter observation immediately to capture accurate start time
        self._enter_observation()

    def _enter_observation(self):
        """Create and enter the GENERATION observation context at stream start.

        Model name MUST be passed here (not just in .update()) because Langfuse
        sets providedModelName from the span attribute at creation time.
        """
        try:
            client = get_client()
            if not client:
                return
            messages = self._kwargs.get("messages", [])
            input_data = _format_generation_input(messages)
            parent_obs = _current_parent_obs.get()
            model_name = self._model.split("/")[-1] if "/" in self._model else self._model

            common_kwargs = dict(
                name="llm-generation",
                as_type="generation",
                model=model_name,
                input=input_data,
                metadata={
                    "session_id": _current_session_id.get(),
                    "source": "streaming_wrapper",
                },
            )

            iteration_span_id = get_iteration_span_id()
            if iteration_span_id:
                # Nest under iteration AGENT via parent_span_id
                self._obs_cm = client.start_as_current_observation(
                    trace_context={"trace_id": self._trace_id, "parent_span_id": iteration_span_id},
                    **common_kwargs,
                )
            elif parent_obs:
                # Nest under the current iteration span for proper hierarchy
                self._obs_cm = parent_obs.start_as_current_observation(**common_kwargs)
            elif self._trace_id:
                # Fallback: link to trace via trace_context (GENERATION will be
                # a direct child of the trace root, not under an iteration)
                self._obs_cm = client.start_as_current_observation(
                    trace_context={"trace_id": self._trace_id},
                    **common_kwargs,
                )

            if self._obs_cm:
                self._obs = self._obs_cm.__enter__()
        except Exception as e:
            logger.debug(f"Observation creation failed: {e}")
            self._obs_cm = None
            self._obs = None

    def __aiter__(self):
        return self

    def __iter__(self):
        return self

    async def __anext__(self):
        try:
            chunk = await self._iterator.__anext__()
            self._on_chunk(chunk)
            return chunk
        except StopAsyncIteration:
            self._finalize_generation()
            raise
        except Exception:
            self._finalize_generation(error=True)
            raise

    async def aclose(self):
        """Ensure GENERATION is finalized when the stream is closed externally.

        A0's transport calls aclose() on the iterator in its finally block,
        which may happen before all chunks (especially the usage-bearing
        final chunk) have been consumed. Drain a bounded amount of remaining
        data to capture usage without hanging cleanup on slow or stuck streams.
        """
        try:
            import asyncio
            drained = 0
            while drained < _STREAM_ACLOSE_MAX_CHUNKS:
                try:
                    chunk = await asyncio.wait_for(
                        self._iterator.__anext__(),
                        timeout=_STREAM_ACLOSE_DRAIN_TIMEOUT_S,
                    )
                    self._on_chunk(chunk)
                    drained += 1
                except asyncio.TimeoutError:
                    break
                except StopAsyncIteration:
                    break
                except Exception:
                    break
        except Exception:
            pass
        self._finalize_generation()
        # Propagate to inner iterator
        close = getattr(self._iterator, "aclose", None)
        if close:
            try:
                await close()
            except Exception:
                pass

    def __next__(self):
        try:
            chunk = next(self._iterator)
            self._on_chunk(chunk)
            return chunk
        except StopIteration:
            self._finalize_generation()
            raise
        except Exception:
            self._finalize_generation(error=True)
            raise

    def _on_chunk(self, chunk):
        """Track first-chunk timestamp, extract usage and output from each chunk."""
        if self._first_chunk_time is None:
            self._first_chunk_time = datetime.now()
        try:
            usage = _find_usage(chunk)
            if usage:
                self._usage = _normalize_usage(usage)
        except Exception:
            pass
        try:
            text = _extract_delta_text(chunk)
            if text:
                self._output_parts.append(text)
        except Exception:
            pass

    def _finalize_generation(self, error=False):
        """Update the observation with model/usage/cost/output and exit context."""
        if self._generation_finalized:
            return
        self._generation_finalized = True

        if not self._obs:
            return

        try:
            model_name = self._model.split("/")[-1] if "/" in self._model else self._model
            output = "".join(self._output_parts)[:MAX_GEN_OUTPUT_CHARS] if self._output_parts else None
            cost_details = _compute_cost_details(model_name, self._usage)
            error_info = "streaming error" if error else ""

            # Extract agent decision data from output JSON (per DeepWiki best practice)
            gen_metadata = {
                "session_id": _current_session_id.get(),
                "error": error_info,
                "source": "streaming_wrapper",
            }
            if output:
                try:
                    import json as _json
                    parsed = _json.loads(output)
                    for key in ("thoughts", "headline", "tool_name"):
                        if key in parsed:
                            val = str(parsed[key])
                            if len(val) > 500:
                                val = val[:500] + "..."
                            gen_metadata[key] = val
                    if "tool_args" in parsed:
                        args_str = str(parsed["tool_args"])
                        gen_metadata["tool_args"] = args_str[:500] + "..." if len(args_str) > 500 else args_str
                except Exception:
                    pass

            # Add active skills to GENERATION metadata
            active_skills = get_loaded_skills()
            if active_skills:
                gen_metadata["active_skills"] = active_skills

            self._obs.update(
                model=model_name,
                output=output,
                usage_details=self._usage if self._usage else None,
                cost_details=cost_details,
                completion_start_time=self._first_chunk_time,
                level="ERROR" if error else "DEFAULT",
                metadata=gen_metadata,
            )
        except Exception as e:
            logger.debug(f"Generation finalize error: {e}")
        finally:
            # Exit the context manager to record end time and flush the span
            if self._obs_cm:
                try:
                    self._obs_cm.__exit__(None, None, None)
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# LiteLLM Call Wrapping
# ---------------------------------------------------------------------------

def _wrap_litellm_calls():
    """Wrap litellm transport functions to inject trace_id and stream_options.

    CRITICAL: Must patch helpers.litellm_transport local imports, not just
    litellm module attributes. The transport module uses `from litellm import
    acompletion` which creates local bound references that bypass module-level
    monkey-patching.

    CRITICAL: Use sys.modules.get('helpers.litellm_transport') instead of
    `from helpers import litellm_transport`. When this module is loaded via
    importlib.util.spec_from_file_location (as A0 extensions are), A0's
    package paths are NOT set up, so the direct import throws ModuleNotFoundError.
    """
    global _original_acompletion, _original_completion
    global _original_aresponses, _original_responses
    import litellm

    # Guard: skip if litellm module already patched AND transport module already patched
    _lt = sys.modules.get('helpers.litellm_transport')
    _lt_patched = False
    if _lt is not None:
        _fn = getattr(_lt, 'acompletion', None)
        _lt_patched = _fn is not None and getattr(_fn, '__name__', '') == '_wrapped_acompletion'
    if _original_acompletion is not None and (_lt_patched or _lt is None):
        return  # Already wrapped and transport either patched or not available

    # Save originals from litellm module
    _original_acompletion = litellm.acompletion
    _original_completion = litellm.completion
    _original_aresponses = getattr(litellm, 'aresponses', None)
    _original_responses = getattr(litellm, 'responses', None)

    async def _wrapped_acompletion(*args, **kwargs):
        trace_id = _current_trace_id.get("")
        if trace_id:
            metadata = kwargs.setdefault("metadata", {})
            if isinstance(metadata, dict):
                metadata.setdefault("langfuse_trace_id", trace_id)
        if kwargs.get("stream"):
            so = kwargs.setdefault("stream_options", {})
            if isinstance(so, dict):
                so.setdefault("include_usage", True)
            # Prevent LiteLLM from stripping stream_options during Responses API fallback.
            # Transport sets drop_params=True on fallback, which silently removes
            # stream_options for providers using custom api_base.
            kwargs["drop_params"] = False
        response = await _original_acompletion(*args, **kwargs)
        # Wrap streaming responses to capture usage and create GENERATION directly
        if trace_id and kwargs.get("stream") and hasattr(response, "__aiter__"):
            response = _StreamingGenerationWrapper(response, kwargs, trace_id, is_async=True)
        return response

    def _wrapped_completion(*args, **kwargs):
        trace_id = _current_trace_id.get("")
        if trace_id:
            metadata = kwargs.setdefault("metadata", {})
            if isinstance(metadata, dict):
                metadata.setdefault("langfuse_trace_id", trace_id)
        if kwargs.get("stream"):
            so = kwargs.setdefault("stream_options", {})
            if isinstance(so, dict):
                so.setdefault("include_usage", True)
            kwargs["drop_params"] = False
        response = _original_completion(*args, **kwargs)
        # Wrap streaming responses to capture usage and create GENERATION directly
        if trace_id and kwargs.get("stream") and hasattr(response, "__iter__"):
            response = _StreamingGenerationWrapper(response, kwargs, trace_id, is_async=False)
        return response

    async def _wrapped_aresponses(*args, **kwargs):
        trace_id = _current_trace_id.get("")
        if trace_id:
            metadata = kwargs.setdefault("metadata", {})
            if isinstance(metadata, dict):
                metadata.setdefault("langfuse_trace_id", trace_id)
        if kwargs.get("stream"):
            kwargs.setdefault("stream_options", {}).setdefault("include_usage", True)
        try:
            response = await _original_aresponses(*args, **kwargs)
        except Exception as e:
            # Task 6: Detect Responses API → Chat Completions fallback
            if trace_id and type(e).__name__ in ("NotFoundError", "BadRequestError"):
                _api_fallback.set(True)
            raise
        # Wrap streaming responses to capture usage and create GENERATION directly
        if trace_id and kwargs.get("stream") and hasattr(response, "__aiter__"):
            response = _StreamingGenerationWrapper(response, kwargs, trace_id, is_async=True)
        return response

    def _wrapped_responses(*args, **kwargs):
        trace_id = _current_trace_id.get("")
        if trace_id:
            metadata = kwargs.setdefault("metadata", {})
            if isinstance(metadata, dict):
                metadata.setdefault("langfuse_trace_id", trace_id)
        if kwargs.get("stream"):
            kwargs.setdefault("stream_options", {}).setdefault("include_usage", True)
        response = _original_responses(*args, **kwargs)
        # Wrap streaming responses to capture usage and create GENERATION directly
        if trace_id and kwargs.get("stream") and hasattr(response, "__iter__"):
            response = _StreamingGenerationWrapper(response, kwargs, trace_id, is_async=False)
        return response

    # Patch litellm module attributes
    litellm.acompletion = _wrapped_acompletion
    litellm.completion = _wrapped_completion
    if _original_aresponses is not None:
        litellm.aresponses = _wrapped_aresponses
    if _original_responses is not None:
        litellm.responses = _wrapped_responses

    # CRITICAL: Also patch helpers.litellm_transport local imports via sys.modules
    lt = sys.modules.get('helpers.litellm_transport')
    if lt is not None:
        if hasattr(lt, 'acompletion'):
            lt.acompletion = _wrapped_acompletion
        if hasattr(lt, 'completion'):
            lt.completion = _wrapped_completion
        if _original_aresponses is not None and hasattr(lt, 'aresponses'):
            lt.aresponses = _wrapped_aresponses
        if _original_responses is not None and hasattr(lt, 'responses'):
            lt.responses = _wrapped_responses

    logger.info("Wrapped litellm transport (module + litellm_transport locals) for trace_id + stream_options injection")


# ---------------------------------------------------------------------------
# Callback Registration
# ---------------------------------------------------------------------------

def _register_callbacks():
    """Register LangfuseGenerationLogger for LLM GENERATION observations."""
    global _callbacks_registered, _generation_logger
    if _callbacks_registered:
        return
    import litellm
    from litellm.integrations.custom_logger import CustomLogger

    class LangfuseGenerationLogger(CustomLogger):
        """Creates GENERATION observations linked to our SDK trace via trace_context.

        Only handles non-streaming calls. Streaming calls are handled by
        _StreamingGenerationWrapper which wraps the iterator directly.
        """

        def log_success_event(self, kwargs, response_obj, start_time, end_time):
            self._create_generation(kwargs, response_obj, start_time, end_time, error=False)

        def log_failure_event(self, kwargs, response_obj, start_time, end_time):
            self._create_generation(kwargs, response_obj, start_time, end_time, error=True)

        async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
            self._create_generation(kwargs, response_obj, start_time, end_time, error=False)

        async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
            self._create_generation(kwargs, response_obj, start_time, end_time, error=True)

        def _create_generation(self, kwargs, response_obj, start_time, end_time, error=False):
            # Read trace_id from kwargs metadata first (injected by wrapper),
            # then fall back to ContextVar (works when callback runs in same context)
            metadata = kwargs.get("metadata") or {}
            if isinstance(metadata, dict):
                trace_id = metadata.get("langfuse_trace_id", "")
            else:
                trace_id = ""
            if not trace_id:
                trace_id = _current_trace_id.get("")
            if not trace_id:
                return
            # Skip streaming calls — _StreamingGenerationWrapper handles those exclusively
            if kwargs.get("stream"):
                return
            try:
                client = get_client()
                if not client:
                    return

                model = kwargs.get("model", "unknown")
                model_name = model.split("/")[-1] if "/" in model else model
                messages = kwargs.get("messages", [])

                # Extract usage — handles both dict and object response_obj
                usage = {}
                raw_usage = None
                if response_obj and hasattr(response_obj, "get"):
                    raw_usage = response_obj.get("usage")
                elif response_obj and hasattr(response_obj, "usage"):
                    raw_usage = response_obj.usage

                if raw_usage:
                    usage = _normalize_usage(raw_usage)

                # Extract cost — prefer LiteLLM response_cost, fall back to model pricing table
                litellm_params = kwargs.get("litellm_params", {}) or {}
                response_cost = kwargs.get("response_cost") or litellm_params.get("response_cost", 0)
                cost_details = None
                if response_cost:
                    cost_details = {"total": float(response_cost)}
                elif usage:
                    cost_details = _compute_cost_details(model_name, usage)

                # Extract output from choices
                output = None
                if response_obj and hasattr(response_obj, "get"):
                    choices = response_obj.get("choices", [])
                    if choices and isinstance(choices[0], dict):
                        msg = choices[0].get("message", {})
                        output = msg.get("content", "")
                elif response_obj and hasattr(response_obj, "choices"):
                    choices = getattr(response_obj, "choices", [])
                    if choices:
                        msg = getattr(choices[0], "message", None)
                        if msg:
                            output = getattr(msg, "content", "")

                # Truncate for API safety
                if output and isinstance(output, str):
                    output = output[:MAX_GEN_OUTPUT_CHARS]
                input_data = _format_generation_input(messages)

                # Extract real error info from kwargs, not str(True/False)
                error_info = ""
                if error:
                    exception = kwargs.get("exception") or kwargs.get("original_exception")
                    error_info = str(exception)[:MAX_ERROR_INFO_CHARS] if exception else "unknown error"
                    # Skip noise from Responses API 404 fallbacks
                    if "404" in error_info and ("/v4/responses" in error_info or "responses" in error_info.lower()):
                        return

                # Use parent observation if available for proper nesting
                parent_obs = _current_parent_obs.get()

                # Convert LiteLLM start/end times to datetime for completion_start_time
                completion_start = None
                if start_time:
                    try:
                        if isinstance(start_time, datetime):
                            completion_start = start_time
                        else:
                            completion_start = datetime.fromisoformat(str(start_time).replace("Z", "+00:00"))
                    except Exception:
                        pass

                common_kwargs = dict(
                    name="llm-generation",
                    as_type="generation",
                    model=model_name,
                    input=input_data,
                    output=output,
                    usage_details=usage if usage else None,
                    cost_details=cost_details,
                    completion_start_time=completion_start,
                    metadata={"session_id": _current_session_id.get(), "error": error_info, "source": "callback_logger"},
                    level="ERROR" if error else "DEFAULT",
                )

                iteration_span_id = get_iteration_span_id()
                if iteration_span_id:
                    # Nest under the iteration AGENT observation via parent_span_id
                    with client.start_as_current_observation(
                        trace_context={"trace_id": trace_id, "parent_span_id": iteration_span_id},
                        **common_kwargs,
                    ) as _obs:
                        pass
                elif parent_obs:
                    with parent_obs.start_as_current_observation(**common_kwargs) as _obs:
                        pass
                else:
                    with client.start_as_current_observation(
                        trace_context={"trace_id": trace_id},
                        **common_kwargs,
                    ) as _obs:
                        pass
            except Exception as e:
                logger.debug(f"Generation logger error: {e}")

    _generation_logger = LangfuseGenerationLogger()
    # Register in BOTH sync and async callback paths.
    # LiteLLM uses _async_success_callback for async LLM calls (acompletion),
    # which is what A0 uses. Without async registration, the callback never fires.
    litellm.logging_callback_manager.add_litellm_success_callback(_generation_logger)
    litellm.logging_callback_manager.add_litellm_failure_callback(_generation_logger)
    litellm.logging_callback_manager.add_litellm_async_success_callback(_generation_logger)
    litellm.logging_callback_manager.add_litellm_async_failure_callback(_generation_logger)
    _wrap_litellm_calls()
    _wrap_rate_limiters()
    _wrap_transport_tracking()
    _callbacks_registered = True
    logger.info("LangfuseGenerationLogger registered for LLM GENERATION observations")
