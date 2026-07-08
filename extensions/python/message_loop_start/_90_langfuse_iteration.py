"""Langfuse v3 iteration AGENT observation on message_loop_start.

Creates an AGENT observation nested under the root trace so each iteration
of the agent loop appears as a distinct child in the Langfuse trace tree.
The iteration span_id is stored in a contextvar so GENERATION observations
can nest under the correct iteration via parent_span_id.
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


class LangfuseIterationStart(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        try:
            if not loop_data.params_persistent.get("lf_sampled"):
                return
            lf = _lib("langfuse_client")
            client = lf.get_client()
            if not client:
                return
            trace_id = lf._current_trace_id.get("")
            if not trace_id:
                return

            parent_obs = lf._current_parent_obs.get(None)
            if not parent_obs:
                # Fallback: use client directly (first iteration before parent set)
                return

            iteration = loop_data.iteration
            obs = parent_obs.start_observation(
                name=f"iteration-{iteration}",
                as_type="agent",
                input={"iteration": iteration},
                metadata={"iteration": iteration},
            )

            # Store iteration span_id so GENERATION observations can nest under it
            span_id = getattr(obs, "id", "")
            lf.set_iteration_span_id(str(span_id) if span_id else "")

            # Store observation + span_id in loop_data for end hook and subordinate lookup
            loop_data.params_temporary["lf_iteration_obs"] = obs
            loop_data.params_temporary["lf_iteration_obs_id"] = str(span_id) if span_id else ""

            # Read loaded skills from agent context for trace tagging
            try:
                loaded = self.agent.context.get_data("loaded_skills")
                if loaded:
                    skill_names = []
                    if isinstance(loaded, list):
                        for s in loaded:
                            name = s if isinstance(s, str) else getattr(s, "name", str(s))
                            skill_names.append(str(name))
                    elif isinstance(loaded, str):
                        skill_names = [loaded]
                    if skill_names:
                        lf.set_loaded_skills(",".join(skill_names))
            except Exception:
                pass

        except Exception as e:
            logger.debug(f"Langfuse iteration start failed: {e}")
