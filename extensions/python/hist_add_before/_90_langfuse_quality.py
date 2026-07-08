"""Restore quality signal scoring (DeepWiki gap fix).

SYNC hook: pattern-matches 4 quality signals in history content and
scores each as BOOLEAN(0).
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


class LangfuseQualitySignal(Extension):

    def execute(self, content_data: dict = None, ai: bool = False, **kwargs):
        try:
            lf = _lib("langfuse_client")
            content = ""
            if content_data and isinstance(content_data, dict):
                content = str(content_data.get("content", ""))
            lf.score_quality_signal(content)
        except Exception as e:
            logger.debug(f"Langfuse quality signal scoring failed: {e}")
