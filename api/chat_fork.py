import importlib.util
import os
import sys

from helpers.api import ApiHandler, Input, Output, Request, Response
from agent import AgentContext


def _lib(name):
    key = f"_lf_lib_{name}"
    if key in sys.modules:
        return sys.modules[key]
    lib_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "extensions", "python", "lib", f"{name}.py")
    spec = importlib.util.spec_from_file_location(key, lib_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


class ChatFork(ApiHandler):
    async def process(self, input: Input, request: Request) -> Output:
        context_id = input.get("context_id", "")
        if not context_id:
            return {"success": False, "error": "context_id is required"}

        # Get source context
        source = AgentContext.get(context_id)
        if not source:
            return {"success": False, "error": f"Context {context_id} not found"}

        # Optional: fork at a specific log position
        fork_at_log_no = input.get("fork_at_log_no", None)
        if fork_at_log_no is not None:
            fork_at_log_no = int(fork_at_log_no)

        try:
            new_context = _lib("fork_helper").fork_context(source, fork_at_log_no=fork_at_log_no)
        except Exception as e:
            return {"success": False, "error": f"Fork failed: {e}"}

        # Notify other tabs about the new context
        from helpers.state_monitor_integration import mark_dirty_all
        mark_dirty_all(reason="api.chat_fork.ChatFork")

        return {
            "success": True,
            "context_id": new_context.id,
            "name": new_context.name,
        }
