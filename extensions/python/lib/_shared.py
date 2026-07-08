"""Shared helper for dynamic module loading from the lib/ directory.

All extension files use this to load langfuse_client.py (and any future lib
modules) under a stable sys.modules key so that hooks.py and the runtime
share the same module instance.
"""

import importlib.util
import os
import sys


def lib(name):
    """Load a module from extensions/python/lib/ by name, cached in sys.modules."""
    key = f"_a0_langfuse_lib_{name}"
    if key in sys.modules:
        return sys.modules[key]
    lib_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"{name}.py",
    )
    spec = importlib.util.spec_from_file_location(key, lib_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod
