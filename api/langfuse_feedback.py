"""Langfuse user feedback API endpoint.

Accepts POST {context_id, score, comment, log_no?, message_id?} and creates a
Langfuse score on the server-resolved trace for that specific assistant message.

score: 1 (thumbs up) or 0 (thumbs down)
data_type: BOOLEAN, name: "user-feedback"
"""

from helpers.api import ApiHandler, Request, Response
from agent import AgentContext
import importlib.util
import json
import os
import sys


_sk = "_a0_langfuse_lib__shared"
if _sk not in sys.modules:
    _sp = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "extensions", "python", "lib", "_shared.py",
    )
    _ss = importlib.util.spec_from_file_location(_sk, _sp)
    sys.modules[_sk] = importlib.util.module_from_spec(_ss)
    _ss.loader.exec_module(sys.modules[_sk])
_lib = sys.modules[_sk].lib


class LangfuseFeedback(ApiHandler):
    @classmethod
    def requires_csrf(cls) -> bool:
        return True

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]

    @staticmethod
    def _json_response(status: int, payload: dict) -> Response:
        return Response(
            response=json.dumps(payload),
            status=status,
            mimetype="application/json",
        )

    async def process(self, input: dict, request: Request) -> dict | Response:
        import logging
        log = logging.getLogger(__name__)

        context_id = str(input.get("context_id", "") or "").strip()
        score = input.get("score")  # 1 or 0
        comment = input.get("comment", "")
        log_no = input.get("log_no")
        message_id = str(input.get("message_id", "") or "").strip()

        if not context_id:
            return self._json_response(400, {"error": "context_id required"})

        if score not in (0, 1):
            return self._json_response(400, {"error": "score must be 0 or 1"})

        if log_no in (None, "") and not message_id:
            return self._json_response(400, {"error": "assistant message identity required"})

        context = AgentContext.get(context_id)
        if not context:
            return self._json_response(404, {"error": "context not found"})

        agent = context.streaming_agent or context.agent0
        if not agent:
            return self._json_response(404, {"error": "agent not found"})

        lf = _lib("langfuse_client")
        trace_id = lf.resolve_feedback_target(agent, log_no=log_no, message_id=message_id)
        if not trace_id:
            return self._json_response(404, {"error": "no feedback target available for this assistant message"})

        try:
            client = lf.get_client()
            if not client:
                return self._json_response(503, {"error": "Langfuse not initialized"})
            client.create_score(
                trace_id=trace_id,
                name="user-feedback",
                value=score,
                data_type="BOOLEAN",
                comment=comment or None,
            )
            return {"ok": True, "score": score}
        except Exception as e:
            log.warning(f"Langfuse feedback API error: {e}")
            return self._json_response(500, {"error": "internal server error"})
