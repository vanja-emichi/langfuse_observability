"""Persist assistant-message -> trace mappings for Langfuse feedback resolution.

hist_add_ai_response is a sync extensible method. We capture the rendered log
identity that the WebUI exposes (log no + shared message id) and bind it to the
current Langfuse trace so later thumbs feedback can target the correct trace
server-side.
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


class LangfuseFeedbackTargetCapture(Extension):

    def execute(self, data: dict = {}, **kwargs):
        try:
            if not self.agent:
                return
            loop_data = getattr(self.agent, "loop_data", None)
            if not loop_data:
                return
            trace_id = loop_data.params_persistent.get("lf_trace_id")
            if not trace_id:
                return

            result = data.get("result")
            args = data.get("args") or ()
            kwargs_in = data.get("kwargs") or {}
            message_id = str(kwargs_in.get("id") or getattr(result, "id", "") or "").strip()

            log_item = loop_data.params_temporary.get("log_item_response") or loop_data.params_temporary.get("log_item_generating")
            if not log_item:
                return

            lf = _lib("langfuse_client")
            lf.remember_feedback_target(
                self.agent,
                trace_id,
                log_no=getattr(log_item, "no", None),
                message_id=message_id,
            )
        except Exception as e:
            logger.debug(f"Langfuse feedback target capture failed: {e}")
