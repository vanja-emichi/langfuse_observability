"""Langfuse v3 Narrative Tap - Log.log() end hook.

Captures ALL narrative events from A0's central logging chokepoint via the
native @extensible decorator on Log.log(). Each log entry becomes a Langfuse
EVENT observation on the current trace.
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


class LangfuseNarrativeTap(Extension):

    # Skip low-value, high-frequency log types that create noise
    _SKIP_TYPES = {"progress", "info", "hint", "response", "agent", "tool", "code_exe", "subagent", "util", "input", "user", "browser", "mcp"}

    def execute(self, data: dict = {}, **kwargs):
        try:
            lib = _lib("langfuse_client")
            if not lib:
                return

            trace_id = lib._current_trace_id.get("")
            if not trace_id:
                return

            client = lib.get_client()
            if not client:
                return

            # @extensible passes data dict with keys: args, kwargs, result, exception
            data_args = data.get("args", ())
            data_kwargs = data.get("kwargs", {}) or {}

            log_type = data_kwargs.get("type", "")
            heading = data_kwargs.get("heading", "")
            content = data_kwargs.get("content", "")
            kvps = data_kwargs.get("kvps", None)

            if not log_type and len(data_args) >= 2:
                log_type = data_args[1]
                heading = data_args[2] if len(data_args) > 2 else heading
                content = data_args[3] if len(data_args) > 3 else content
                kvps = data_args[4] if len(data_args) > 4 else kvps

            # Filter: skip noisy types entirely
            if log_type in self._SKIP_TYPES:
                return

            # Filter: skip entries with no meaningful content (streaming noise)
            if not heading and not content and not kvps:
                return

            metadata = lib._build_log_metadata(log_type, heading, content, kvps)

            obs = client.start_observation(
                name="log-" + str(log_type),
                as_type="event",
                trace_context={"trace_id": trace_id},
                metadata=metadata,
            )
            obs.end()
        except Exception as e:
            logger.debug("Langfuse narrative tap error: " + str(e))
