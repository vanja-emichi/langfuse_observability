"""Langfuse v3 TOOL observation on tool_execute_before.

Creates a TOOL observation nested under the current iteration AGENT
with input=filtered tool args.
"""

import importlib.util
import logging
import os
import sys

from helpers.extension import Extension

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


class LangfuseToolStart(Extension):

    async def execute(self, tool_args: dict = None, tool_name: str = "", **kwargs):
        try:
            lf = _lib("langfuse_client")
            trace_id = lf._current_trace_id.get("")
            if not trace_id:
                return

            # Get parent observation: prefer iteration AGENT, fall back to root
            parent_obs = None
            agent = self.agent
            if agent and hasattr(agent, "loop_data"):
                parent_obs = agent.loop_data.params_temporary.get("lf_iteration_obs")
            if not parent_obs:
                parent_obs = lf._current_parent_obs.get(None)
            if not parent_obs:
                return

            # Filter sensitive data from tool args
            filtered_args = lf._h._filter_sensitive_args(tool_args or {})

            # Truncate large arg values
            truncated = {}
            for k, v in filtered_args.items():
                val_str = str(v)
                if len(val_str) > lf.MAX_TOOL_ARG_CHARS:
                    val_str = val_str[: lf.MAX_TOOL_ARG_CHARS] + "..."
                truncated[k] = val_str

            obs = parent_obs.start_observation(
                name=f"tool-{tool_name}",
                as_type="tool",
                input=truncated,
                metadata={"tool_name": tool_name},
            )

            # Store for end hook
            if agent and hasattr(agent, "loop_data"):
                tool_list_key = f"lf_tool_obs_list_{tool_name}"
                obs_list = agent.loop_data.params_temporary.get(tool_list_key, [])
                obs_list.append(obs)
                agent.loop_data.params_temporary[tool_list_key] = obs_list

        except Exception as e:
            logger.debug(f"Langfuse tool start failed: {e}")
