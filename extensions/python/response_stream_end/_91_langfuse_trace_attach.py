import importlib.util
import os
import sys

from helpers.extension import Extension
from agent import LoopData


def _lib(name):
    key = f"_lf_lib_{name}"
    if key in sys.modules:
        return sys.modules[key]
    lib_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib", f"{name}.py")
    spec = importlib.util.spec_from_file_location(key, lib_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


class LangfuseTraceAttach(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        if not loop_data.params_persistent.get("lf_sampled"):
            return

        trace_id = loop_data.params_persistent.get("lf_trace_id")
        if not trace_id:
            return

        log_item = loop_data.params_temporary.get("log_item_response")
        if not log_item:
            return

        # Build Langfuse trace URL using the root trace object (v2 API)
        trace_url = ""
        root_trace = loop_data.params_persistent.get("lf_root_trace") or loop_data.params_persistent.get("lf_trace")
        if root_trace:
            try:
                trace_url = root_trace.get_trace_url() or ""
            except Exception:
                pass

        try:
            log_item.update(kvps={"trace_id": trace_id, "trace_url": trace_url})
        except Exception:
            pass
