"""Langfuse Observability plugin initializer.

Called by Agent Zero when the user clicks Initialize on the plugin page.
Installs the langfuse Python package into the framework venv.

Can be run standalone: python initialize.py
"""

import logging
import subprocess
import sys

log = logging.getLogger(__name__)


def _run(cmd: list, timeout: int = 300) -> tuple[int, str, str]:
    """Run a subprocess command. Returns (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s: {' '.join(cmd)}"
    except Exception as e:
        return -1, "", str(e)


def initialize(plugin_dir: str = None) -> bool:
    """Install langfuse Python package into the framework venv."""
    print("\n=== Langfuse Observability Plugin Initialization ===")
    success = True

    print("\nStep 1: Installing langfuse Python package...")
    try:
        import langfuse
        version = getattr(langfuse, "__version__", "unknown")
        print(f"langfuse already installed: {version}")
    except ImportError:
        rc, out, err = _run(
            [sys.executable, "-m", "pip", "install", "--quiet", "langfuse>=4.0.0,<5.0.0"],
            timeout=180,
        )
        if rc == 0:
            try:
                import importlib
                import langfuse as lf
                importlib.reload(lf)
                version = getattr(lf, "__version__", "unknown")
            except Exception:
                version = "installed"
            print(f"langfuse installed: {version}")
        else:
            print(f"pip install langfuse failed:\n{err[-500:]}")
            log.error("pip install langfuse failed: %s", err)
            success = False

    print()
    if success:
        print("Initialization complete - Langfuse Observability plugin is ready.")
        print("   Configure your API keys in the plugin settings.")
    else:
        print("Initialization completed with warnings. Check output above.")
        print("   Manual install: pip install langfuse>=4.0.0,<5.0.0")
    print()
    return success


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    sys.exit(0 if initialize() else 1)
