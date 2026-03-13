import os
import sys

_PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PLUGIN_ROOT not in sys.path:
    sys.path.append(_PLUGIN_ROOT)

from helpers.extension import Extension
from langfuse_helpers.langfuse_helper import get_langfuse_client, should_sample
from agent import LoopData, Agent


class LangfuseTraceStart(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        try:
            client = get_langfuse_client()
            if not client:
                return

            if not should_sample():
                loop_data.params_persistent["lf_sampled"] = False
                return
            loop_data.params_persistent["lf_sampled"] = True

            agent = self.agent
            context_id = str(agent.context.id) if agent.context else "unknown"

            # Check for parent agent (subordinate nesting)
            superior = agent.get_data(Agent.DATA_NAME_SUPERIOR)
            if superior and hasattr(superior, "loop_data"):
                parent_span = superior.loop_data.params_temporary.get("lf_tool_span")
                if not parent_span:
                    parent_span = superior.loop_data.params_temporary.get("lf_iteration_span")
                if not parent_span:
                    parent_span = superior.loop_data.params_persistent.get("lf_trace")

                if parent_span:
                    try:
                        span = parent_span.span(
                            name=f"agent-{agent.number}-monologue",
                            metadata={"agent_number": agent.number},
                        )
                        loop_data.params_persistent["lf_trace"] = span
                        loop_data.params_persistent["lf_root_trace"] = (
                            superior.loop_data.params_persistent.get("lf_root_trace")
                            or superior.loop_data.params_persistent.get("lf_trace")
                        )
                    except Exception:
                        pass
                    return

            # Top-level agent: create a root trace (Langfuse v2 API)
            user_msg = ""
            if loop_data.user_message:
                user_msg = str(loop_data.user_message.content)

            try:
                root_trace = client.trace(
                    name=f"agent-{agent.number}-monologue",
                    input=user_msg,
                    session_id=context_id,
                    metadata={"agent_number": agent.number},
                )
                loop_data.params_persistent["lf_trace"] = root_trace
                loop_data.params_persistent["lf_root_trace"] = root_trace
                loop_data.params_persistent["lf_trace_id"] = root_trace.trace_id
            except Exception:
                loop_data.params_persistent["lf_sampled"] = False
        except Exception:
            pass
