"""Langfuse v4 prompt sync upload (Task 10).

Uploads the assembled A0 system prompt to Langfuse prompt management for
versioning and auditing. Runs on the system_prompt hook after assembly.
Disabled by default — requires langfuse_prompt_sync_enabled: true in config.
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


class LangfusePromptSync(Extension):

    async def execute(self, system_prompt: list = [], loop_data: LoopData = LoopData(), **kwargs):
        try:
            lf = _lib("langfuse_client")
            config = lf.get_langfuse_config()
            if not config.get("langfuse_prompt_sync_enabled", False):
                return
            if system_prompt:
                lf.upload_prompt("a0-system-prompt", system_prompt)
        except Exception as e:
            logger.debug(f"Langfuse prompt sync upload failed: {e}")
