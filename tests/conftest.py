"""Test configuration: ensure A0 framework modules are importable."""
import sys
import os

_a0_root = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if _a0_root not in sys.path:
    sys.path.insert(0, _a0_root)
