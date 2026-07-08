"""Langfuse v4 prompt override download (Task 10).

Downloads a Langfuse prompt and overrides the A0 system prompt before it
enters the message loop. Supports replace and prepend modes.
Disabled by default — requires langfuse_prompt_override_enabled: true in config.
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


class LangfusePromptOverride(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        try:
            lf = _lib("langfuse_client")
            config = lf.get_langfuse_config()
            if not config.get("langfuse_prompt_override_enabled", False):
                return
            mode = config.get("langfuse_prompt_override_mode", "prepend")
            if loop_data.system:
                loop_data.system = lf.apply_prompt_override(
                    "a0-system-prompt", loop_data.system, mode=mode
                )
        except Exception as e:
            logger.debug(f"Langfuse prompt override failed: {e}")
