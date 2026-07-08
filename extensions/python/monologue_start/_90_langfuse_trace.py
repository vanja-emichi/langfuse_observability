"""Langfuse v4 trace creation on monologue start."""

import importlib.util
import logging
import os
import sys

from helpers.extension import Extension
from agent import LoopData, Agent

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


class LangfuseTraceStart(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        try:
            lf = _lib("langfuse_client")
            if not lf.should_sample():
                loop_data.params_persistent["lf_sampled"] = False
                return
            client = lf.get_client()
            if not client:
                loop_data.params_persistent["lf_sampled"] = False
                return
            # Ensure transport module is patched (may not have been available during agent_init)
            lf._wrap_litellm_calls()
            lf._wrap_rate_limiters()
            loop_data.params_persistent["lf_sampled"] = True

            agent = self.agent
            context_id = str(agent.context.id) if agent.context else "unknown"
            user_msg = str(loop_data.user_message.content) if loop_data.user_message else ""

            from langfuse import propagate_attributes

            # Check for parent agent (subordinate nesting)
            # Path 1: chain-delegated subordinates (Agent.DATA_NAME_SUPERIOR)
            # Path 2: parallel subordinates (_parallel_parent_context_id)
            superior = agent.get_data(Agent.DATA_NAME_SUPERIOR)
            parent_trace_id = None
            parent_span_id = None
            if superior and hasattr(superior, "loop_data"):
                parent_trace_id = superior.loop_data.params_persistent.get("lf_trace_id")
            if not parent_trace_id:
                # Check parallel worker parent context
                from agent import AgentContext
                _pctx_key = "_parallel_parent_context_id"
                parent_ctx_id = agent.context.get_data(_pctx_key) if agent.context else None
                if parent_ctx_id:
                    parent_ctx = AgentContext.get(parent_ctx_id)
                    if parent_ctx and parent_ctx.agent0 and hasattr(parent_ctx.agent0, "loop_data"):
                        parent_trace_id = parent_ctx.agent0.loop_data.params_persistent.get("lf_trace_id")
                        parent_span_id = parent_ctx.agent0.loop_data.params_temporary.get("lf_iteration_obs_id")

            # Identify user via A0 persistent runtime ID for per-instance tracking
            user_id = os.getenv("A0_PERSISTENT_RUNTIME_ID", "")
            is_subordinate = parent_trace_id is not None
            agent_profile = getattr(agent.config, "profile", "") or ""
            agent_label = f"agent-{agent.number}"
            if agent_profile and agent_profile != "agent0":
                agent_label += f"-{agent_profile}"
            prop_cm = propagate_attributes(
                trace_name=f"{agent_label}-monologue",
                session_id=context_id,
                user_id=user_id if user_id else None,
                tags=["agent-zero", f"agent-{agent.number}"] + (["subordinate"] if is_subordinate else []) + ([f"profile-{agent_profile}"] if agent_profile and agent_profile != "agent0" else []),
                metadata={"agent_number": agent.number, "is_subordinate": is_subordinate, "profile": agent_profile},
            )
            prop_cm.__enter__()

            # Build trace_context: if parent_span_id available, nest subordinate
            # AGENT observation directly under parent's current iteration
            trace_ctx = None
            if parent_trace_id and parent_span_id:
                trace_ctx = {"trace_id": parent_trace_id, "parent_span_id": parent_span_id}
            elif parent_trace_id:
                trace_ctx = {"trace_id": parent_trace_id}

            obs_cm = client.start_as_current_observation(
                name=f"{agent_label}-monologue",
                as_type="agent",
                input=user_msg,
                trace_context=trace_ctx,
                metadata={"agent_number": agent.number, "is_subordinate": is_subordinate, "profile": agent_profile},
                end_on_exit=False,
            )
            root_obs = obs_cm.__enter__()

            trace_id = client.get_current_trace_id()

            # Fix trace-level input to show user message (not system prompt from OTel propagation)
            try:
                client.set_current_trace_io(input={"role": "user", "content": user_msg[:5000]})
            except Exception:
                pass

            loop_data.params_persistent["lf_prop_cm"] = prop_cm
            loop_data.params_persistent["lf_obs_cm"] = obs_cm
            loop_data.params_persistent["lf_root_obs"] = root_obs
            loop_data.params_persistent["lf_trace_id"] = trace_id

            # Task 2: mark this trace as pending (cleared only on normal completion
            # in monologue_end). If still set at the NEXT monologue_start, the task
            # was killed/stopped and gets scored user-stopped=0.
            agent.set_data("lf_pending_trace_id", trace_id)

            # Set module-level vars so LangfuseGenerationLogger can link to this trace
            lf.set_trace_context(trace_id, context_id)
            # Set root obs as initial parent so first-iteration GENERATIONs can nest
            lf.set_parent_observation(root_obs)

        except Exception as e:
            logger.debug(f"Langfuse trace creation failed: {e}")
            loop_data.params_persistent["lf_sampled"] = False
