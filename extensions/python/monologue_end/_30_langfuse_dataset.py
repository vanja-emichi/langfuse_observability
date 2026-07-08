"""Langfuse v4 automatic dataset export (monologue_end).

Runs AFTER the judge hook (_20) but BEFORE the flush hook (_90) so trace context
is still active. Exports successful traces as Langfuse dataset items for future
experiments. Disabled by default — requires langfuse_dataset_export_enabled: true.
"""

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
    _spec = importlib.util.spec_from_file_location(
        _sk, os.path.join(_d, "lib", "_shared.py")
    )
    sys.modules[_sk] = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(sys.modules[_sk])
_lib = sys.modules[_sk].lib


def _extract_response_output(raw):
    """Extract clean response text from raw LLM output.

    Duplicated from _90_langfuse_flush.py because extension hooks are loaded
    via importlib and cannot import each other.
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
    if data.get("tool_name") == "response":
        tool_args = data.get("tool_args", {})
        text = tool_args.get("text", "")
        if text:
            return str(text)[:5000]
    if "text" in data:
        return str(data["text"])[:5000]
    return json.dumps(data)[:5000]


class LangfuseDatasetExport(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        try:
            if not loop_data.params_persistent.get("lf_sampled"):
                return
            trace_id = loop_data.params_persistent.get("lf_trace_id")
            if not trace_id:
                return

            lf = _lib("langfuse_client")
            config = lf.get_langfuse_config()
            if not config.get("langfuse_dataset_export_enabled", False):
                return

            # Only export normal completions — verify last_response is a
            # 'response' tool call (not an error, stop, or empty).
            raw = loop_data.last_response
            if not raw:
                return
            try:
                resp_data = json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, ValueError):
                return
            if not isinstance(resp_data, dict) or resp_data.get("tool_name") != "response":
                return

            # Extract user message and response text
            user_message = ""
            if loop_data.user_message:
                user_message = str(loop_data.user_message.content or "")
            if not user_message:
                return
            expected_output = _extract_response_output(raw)
            if not expected_output:
                return

            dataset_name = config.get("langfuse_dataset_name", "a0-traces")
            session_id = loop_data.params_persistent.get("lf_session_id", "")

            lf.export_dataset_item(
                dataset_name=dataset_name,
                input_data={"role": "user", "content": user_message[:5000]},
                expected_output=expected_output,
                trace_id=trace_id,
                metadata={"session": session_id} if session_id else {},
            )
        except Exception as e:
            logger.debug(f"Dataset export hook failed: {e}")
