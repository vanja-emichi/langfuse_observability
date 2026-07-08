"""Langfuse v4 implicit feedback scoring on monologue start (Task 2).

Runs before _90_langfuse_trace.py (which creates the new trace and sets
lf_pending_trace_id) so it can inspect state left by the *previous* monologue:

- lf_pending_trace_id still set -> previous task was killed/stopped -> score 0
- lf_last_trace_id set (no pending) -> previous trace completed normally and
  the user just sent a follow-up message -> score 1
"""

import importlib.util
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


class LangfuseImplicitFeedback(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        try:
            lf = _lib("langfuse_client")
            lf.handle_monologue_start_feedback(self.agent)
        except Exception as e:
            logger.debug(f"Langfuse implicit feedback scoring failed: {e}")
