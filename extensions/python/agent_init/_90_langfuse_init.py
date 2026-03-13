import importlib.util
import os
import sys

from helpers.extension import Extension


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


class LangfuseInit(Extension):

    def execute(self, **kwargs):
        try:
            _lib("langfuse_helper").get_langfuse_client()
        except Exception:
            pass
