"""Langfuse v4 LLM-as-a-Judge evaluation (Task 11).

Runs after agent response completes, evaluates quality using glm-5.2.
Creates quality-judge NUMERIC score (0.0-1.0) on current trace.
Disabled by default — requires langfuse_judge_enabled: true in config.
Runs BEFORE _90_langfuse_flush.py (sort order: _20 < _90) so trace context
is still active when the judge runs.
"""

import asyncio
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


class LangfuseJudge(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        try:
            lf = _lib("langfuse_client")
            config = lf.get_langfuse_config()
            if not config.get("langfuse_judge_enabled", False):
                return
            user_msg = str(loop_data.user_message.content) if loop_data.user_message else ""
            agent_response = str(loop_data.last_response or "")
            if user_msg and agent_response:
                await lf.run_judge_evaluation(user_msg, agent_response)
        except Exception as e:
            logger.debug(f"Langfuse judge evaluation failed: {e}")
