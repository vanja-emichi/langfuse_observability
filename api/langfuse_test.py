import importlib.util
import os
import sys

from helpers.api import ApiHandler, Request, Response
from helpers.plugins import get_plugin_config


def _lib(name):
    key = f"_lf_lib_{name}"
    if key in sys.modules:
        return sys.modules[key]
    lib_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "extensions", "python", "lib", f"{name}.py")
    spec = importlib.util.spec_from_file_location(key, lib_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


# Matches the core PASSWORD_PLACEHOLDER pattern
_SECRET_PLACEHOLDER = "***"


class LangfuseTest(ApiHandler):

    async def process(self, input: dict, request: Request) -> dict | Response:
        public_key = input.get("public_key", "")
        secret_key = input.get("secret_key", "")
        host = input.get("host", "https://cloud.langfuse.com")

        # If frontend sent the masked placeholder, use the real stored key
        if secret_key == _SECRET_PLACEHOLDER:
            config = get_plugin_config("langfuse_observability", None) or {}
            secret_key = config.get("langfuse_secret_key", "")

        if not public_key or not secret_key:
            return {"success": False, "error": "Public key and secret key are required"}

        try:
            _lib("langfuse_helper")._ensure_langfuse_installed()
            from langfuse import Langfuse

            client = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                host=host,
            )
            result = client.auth_check()
            client.flush()
            return {"success": result, "error": "" if result else "Authentication failed"}
        except ImportError:
            return {"success": False, "error": "langfuse package not installed. Could not auto-install."}
        except Exception as e:
            return {"success": False, "error": str(e)}
