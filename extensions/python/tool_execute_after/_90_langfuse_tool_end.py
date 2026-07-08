"""Langfuse v3 TOOL observation end on tool_execute_after.

Updates the TOOL observation created in tool_execute_before with the
tool result and ends it.
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


class LangfuseToolEnd(Extension):

    async def execute(self, response=None, tool_name: str = "", **kwargs):
        try:
            lf = _lib("langfuse_client")

            lf = _lib("langfuse_client")

            agent = self.agent
            if not agent or not hasattr(agent, "loop_data"):
                return

            tool_list_key = f"lf_tool_obs_list_{tool_name}"
            obs_list = agent.loop_data.params_temporary.get(tool_list_key, [])
            if not obs_list:
                return
            obs = obs_list.pop()
            if not obs_list:
                agent.loop_data.params_temporary.pop(tool_list_key, None)
            if not obs:
                return

            # Extract output message from response
            output = ""
            if response:
                output = getattr(response, "message", "") or ""
            output_str = str(output)
            output_str = lf._h._sanitize_for_capture(output_str)
            if len(output_str) > lf.MAX_GEN_OUTPUT_CHARS:
                output_str = output_str[: lf.MAX_GEN_OUTPUT_CHARS]

            try:
                obs.update(output=output_str)
            except Exception:
                pass
            try:
                obs.end()
            except Exception:
                pass

        except Exception as e:
            logger.debug(f"Langfuse tool end failed: {e}")
