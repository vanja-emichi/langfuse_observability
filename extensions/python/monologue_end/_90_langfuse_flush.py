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


class LangfuseFlush(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        if not loop_data.params_persistent.get("lf_sampled"):
            return

        try:
            client = _lib("langfuse_helper").get_langfuse_client()
            if not client:
                return

            trace = loop_data.params_persistent.get("lf_trace")
            if trace:
                try:
                    trace.update(
                        output=loop_data.last_response[:2000] if loop_data.last_response else "",
                    )
                except Exception:
                    pass

            try:
                client.flush()
            except Exception:
                pass

            loop_data.params_persistent.pop("lf_trace", None)
            loop_data.params_persistent.pop("lf_root_trace", None)
            loop_data.params_persistent.pop("lf_sampled", None)
        except Exception:
            pass
