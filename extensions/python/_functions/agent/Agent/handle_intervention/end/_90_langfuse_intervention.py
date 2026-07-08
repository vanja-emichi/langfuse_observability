"""Track user interventions via handle_intervention @extensible hook.

Scores user-intervention: 0 (BOOLEAN) when InterventionException fires.
DeepWiki confirmed handle_intervention IS @extensible (agent.py:1079).
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


class LangfuseIntervention(Extension):

    async def execute(self, data: dict = {}, **kwargs):
        try:
            exception = data.get("exception")
            if exception is None:
                return
            # Only score on InterventionException
            exc_name = type(exception).__name__
            if exc_name != "InterventionException":
                return

            lf = _lib("langfuse_client")
            trace_id = lf._current_trace_id.get("")
            if not trace_id:
                return
            client = lf.get_client()
            if not client:
                return

            client.create_score(
                trace_id=trace_id,
                name="user-intervention",
                value=0,
                data_type="BOOLEAN",
            )
        except Exception as e:
            logger.debug(f"Langfuse intervention scoring failed: {e}")
