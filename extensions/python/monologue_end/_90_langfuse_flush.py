"""Langfuse v4 flush and cleanup on monologue end."""

import importlib.util
import json
import logging
import os
import sys

from helpers.extension import Extension
from agent import LoopData

logger = logging.getLogger(__name__)

_sk = "_a0_langfuse_lib__shared"
if _sk not in sys.modules:
    _d = os.path.dirname(os.path.abspath(__file__))
    while not os.path.exists(os.path.join(_d, "lib", "_shared.py")):
        _d = os.path.dirname(_d)
    _spec = importlib.util.spec_from_file_location(_sk, os.path.join(_d, "lib", "_shared.py"))
    sys.modules[_sk] = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(sys.modules[_sk])
_lib = sys.modules[_sk].lib


def _extract_response_output(raw):
    """Extract clean response text from raw LLM output.

    The agent's last_response may be:
    - A JSON string with tool_name='response' and tool_args.text
    - A JSON string with a 'text' key
    - Plain text already
    """
    if not raw:
        return ""
    if isinstance(raw, dict):
        data = raw
    elif isinstance(raw, str):
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return raw[:5000]
    else:
        return str(raw)[:5000]
    # Tool response: extract tool_args.text
    if data.get("tool_name") == "response":
        tool_args = data.get("tool_args", {})
        text = tool_args.get("text", "")
        if text:
            return str(text)[:5000]
    # Generic 'text' key
    if "text" in data:
        return str(data["text"])[:5000]
    # Fallback: stringify the dict
    return json.dumps(data)[:5000]


class LangfuseFlush(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        if not loop_data.params_persistent.get("lf_sampled"):
            return
        try:
            lf = _lib("langfuse_client")
            client = lf.get_client()
            if not client:
                return

            obs = loop_data.params_persistent.get("lf_root_obs")
            if obs:
                try:
                    output = _extract_response_output(loop_data.last_response)
                    obs.update(output=output)
                except Exception as e:
                    logger.debug(f"Output update failed: {e}")
                try:
                    obs.end()
                except Exception:
                    pass

            # Exit observation context manager before propagate_attributes
            obs_cm = loop_data.params_persistent.get("lf_obs_cm")
            if obs_cm:
                try:
                    obs_cm.__exit__(None, None, None)
                except Exception:
                    pass

            prop_cm = loop_data.params_persistent.get("lf_prop_cm")
            if prop_cm:
                try:
                    prop_cm.__exit__(None, None, None)
                except Exception:
                    pass

            try:
                client.flush()
            except Exception as e:
                logger.debug(f"Flush failed: {e}")

            # Gap 1 fix: Ensure SDK sends buffered traces before context cleanup.
            # The Langfuse SDK flush is non-blocking; scheduler/background tasks
            # may complete before the internal batching queue sends data.
            try:
                import time as _time
                import asyncio
                await asyncio.sleep(1)
            except Exception:
                pass

            # Task 2: normal completion reached - clear the pending flag and
            # record this trace as the last completed one for follow-up scoring
            # at the next monologue_start.
            try:
                trace_id = loop_data.params_persistent.get("lf_trace_id")
                if trace_id:
                    self.agent.set_data("lf_pending_trace_id", None)
                    self.agent.set_data("lf_last_trace_id", trace_id)
            except Exception as e:
                logger.debug(f"Implicit feedback flag update failed: {e}")

            # Task 4: flush feature tags from collected tool names
            try:
                trace_id = loop_data.params_persistent.get("lf_trace_id")
                tools_used = loop_data.params_persistent.get("lf_tools_used", [])
                if trace_id:
                    lf.add_feature_tags(trace_id, tools_used)
            except Exception as e:
                logger.debug(f"Feature tag flush failed: {e}")

            # Add skill tags to trace
            try:
                trace_id = loop_data.params_persistent.get("lf_trace_id")
                skills_str = lf.get_loaded_skills()
                if trace_id and skills_str:
                    skill_tags = [f"skill-{s.strip()}" for s in skills_str.split(",") if s.strip()]
                    if skill_tags:
                        client.update_trace(trace_id=trace_id, tags=skill_tags)
            except Exception as e:
                logger.debug(f"Skill tag flush failed: {e}")

            # CRITICAL: Clear contextvars
            lf.clear_trace_context()

            for key in ("lf_prop_cm", "lf_obs_cm", "lf_root_obs", "lf_trace_id", "lf_sampled"):
                loop_data.params_persistent.pop(key, None)
        except Exception as e:
            logger.debug(f"Monologue end failed: {e}")
