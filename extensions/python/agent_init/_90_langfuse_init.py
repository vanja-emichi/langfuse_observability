"""Langfuse initialization on agent startup."""

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


class LangfuseInit(Extension):

    def execute(self, **kwargs):
        try:
            lf = _lib("langfuse_client")
            client = lf.get_client()
            # Validate credentials at startup
            if client:
                client.auth_check()
                logger.info("Langfuse auth check passed")
        except Exception as e:
            logger.warning(f"Langfuse auth check failed: {e}")
