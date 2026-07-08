"""Langfuse v3 iteration AGENT observation end on message_loop_end.

Ends the iteration AGENT observation created in message_loop_start and clears
the iteration span_id contextvar.
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


class LangfuseIterationEnd(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        try:
            if not loop_data.params_persistent.get("lf_sampled"):
                return
            lf = _lib("langfuse_client")

            obs = loop_data.params_temporary.get("lf_iteration_obs")
            if obs:
                try:
                    obs.update(output={"iteration": loop_data.iteration})
                except Exception:
                    pass
                try:
                    obs.end()
                except Exception:
                    pass

            # Clear iteration span_id for safety; next iteration sets a new one
            lf.clear_iteration_span_id()

        except Exception as e:
            logger.debug(f"Langfuse iteration end failed: {e}")
