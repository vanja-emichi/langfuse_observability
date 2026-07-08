"""Restore raw exception scoring (DeepWiki gap fix).

Captures ALL exceptions (including non-repairable) as raw-exception: 0
(BOOLEAN) with location + exception info.
"""

import importlib.util
import logging
import os
import sys

from helpers.extension import Extension

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


class LangfuseRawException(Extension):

    async def execute(self, data: dict = {}, **kwargs):
        try:
            lf = _lib("langfuse_client")
            # @extensible passes data with args, kwargs, result, exception
            args = data.get("args", ())
            exception = data.get("exception")
            # handle_exception(self, location, exception) — location is args[1]
            location = str(args[1]) if len(args) >= 2 else "unknown"
            if exception:
                lf.capture_raw_exception(location, exception)
        except Exception as e:
            logger.debug(f"Langfuse raw exception scoring failed: {e}")
