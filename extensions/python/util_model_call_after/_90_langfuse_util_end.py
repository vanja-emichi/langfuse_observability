"""Restore utility model SPAN end tracking (DeepWiki gap fix).

Updates SPAN observation with output and ends it.
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


class LangfuseUtilModelEnd(Extension):

    async def execute(self, call_data: dict = None, response: str = "", **kwargs):
        try:
            lf = _lib("langfuse_client")
            lf.end_util_model_span(call_data or {}, response or "")
        except Exception as e:
            logger.debug(f"Langfuse util model end failed: {e}")
