import logging
import sys

log = logging.getLogger(__name__)


def save_plugin_config(config, plugin_name, agent=None, project_name=None):
    """Reset client after config save so new credentials take effect."""
    try:
        mod = sys.modules.get("_a0_langfuse_lib_langfuse_client")
        if mod is None:
            log.debug("Langfuse client module not loaded yet; nothing to reset.")
            return config
        mod.reset_client()
        log.info("Langfuse client reset after config save")
    except Exception as e:
        log.warning(f"Failed to reset Langfuse client: {e}")
    return config
