"""Tests for a0_langfuse plugin (v4 OTel-native architecture)."""

import importlib.util
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

PLUGIN_BASE = os.path.join(os.path.dirname(__file__), "..", "extensions", "python", "lib")


def _load_client_module():
    path = os.path.join(PLUGIN_BASE, "langfuse_client.py")
    spec = importlib.util.spec_from_file_location("test_langfuse_client", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod



def _load_feedback_api_module():
    path = os.path.join(os.path.dirname(__file__), "..", "api", "langfuse_feedback.py")
    spec = importlib.util.spec_from_file_location("test_langfuse_feedback_api", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def lf():
    mod = _load_client_module()
    mod._client = None
    mod._client_initialized = False
    mod._callbacks_registered = False
    mod._config_cache = None
    mod._original_acompletion = None
    mod._original_completion = None
    mod._original_aresponses = None
    mod._original_responses = None
    if hasattr(mod, '_original_transport_acomplete'):
        mod._original_transport_acomplete = None
    if hasattr(mod, '_original_transport_astream'):
        mod._original_transport_astream = None
    if hasattr(mod, '_original_models_is_transient_error'):
        mod._original_models_is_transient_error = None
    if hasattr(mod, '_original_models_unified_call'):
        mod._original_models_unified_call = None
    if hasattr(mod, '_original_models_unified_turn'):
        mod._original_models_unified_turn = None
    if hasattr(mod, '_scored_trace_ids'):
        mod._scored_trace_ids.clear()
    yield mod
    mod._client = None
    mod._client_initialized = False
    mod._callbacks_registered = False
    mod._config_cache = None
    mod._original_acompletion = None
    mod._original_completion = None
    mod._original_aresponses = None
    mod._original_responses = None
    if hasattr(mod, '_original_transport_acomplete'):
        mod._original_transport_acomplete = None
    if hasattr(mod, '_original_transport_astream'):
        mod._original_transport_astream = None
    if hasattr(mod, '_original_models_is_transient_error'):
        mod._original_models_is_transient_error = None
    if hasattr(mod, '_original_models_unified_call'):
        mod._original_models_unified_call = None
    if hasattr(mod, '_original_models_unified_turn'):
        mod._original_models_unified_turn = None


# Config Resolution Tests

class TestConfigResolution:

    def test_disabled_by_default(self, lf, monkeypatch):
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)
        with patch("helpers.plugins.get_plugin_config", return_value={}):
            config = lf.get_langfuse_config()
        assert config["enabled"] is False
        assert config["public_key"] == ""
        assert config["host"] == "https://cloud.langfuse.com"
        assert config["sample_rate"] == 1.0

    def test_env_vars_override_config(self, lf, monkeypatch):
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-env")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-env")
        monkeypatch.setenv("LANGFUSE_HOST", "https://custom.langfuse.com")
        with patch("helpers.plugins.get_plugin_config", return_value={}):
            config = lf.get_langfuse_config()
        assert config["public_key"] == "pk-env"
        assert config["secret_key"] == "sk-env"
        assert config["host"] == "https://custom.langfuse.com"

    def test_auto_enable_with_env_keys(self, lf, monkeypatch):
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-auto")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-auto")
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)
        with patch("helpers.plugins.get_plugin_config", return_value={"langfuse_enabled": False}):
            config = lf.get_langfuse_config()
        assert config["enabled"] is True

    def test_config_caching(self, lf, monkeypatch):
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        with patch("helpers.plugins.get_plugin_config", return_value={"langfuse_enabled": True}):
            c1 = lf.get_langfuse_config()
            c2 = lf.get_langfuse_config()
        assert c1 is c2  # Same cached dict object


# Sampling Tests

class TestSampling:

    def test_always_sample_at_1(self, lf):
        with patch.object(lf, "get_langfuse_config", return_value={"sample_rate": 1.0}):
            assert lf.should_sample() is True

    def test_never_sample_at_0(self, lf):
        with patch.object(lf, "get_langfuse_config", return_value={"sample_rate": 0.0}):
            assert lf.should_sample() is False

    def test_partial_sampling(self, lf):
        with patch.object(lf, "get_langfuse_config", return_value={"sample_rate": 0.5}):
            with patch("random.random", return_value=0.4):
                assert lf.should_sample() is True
            with patch("random.random", return_value=0.6):
                assert lf.should_sample() is False


# Client Singleton Tests

class TestClientSingleton:

    def test_returns_none_when_disabled(self, lf):
        with patch.object(lf, "get_langfuse_config", return_value={"enabled": False, "public_key": "", "secret_key": ""}):
            assert lf.get_client() is None

    def test_returns_none_without_keys(self, lf):
        with patch.object(lf, "get_langfuse_config", return_value={"enabled": True, "public_key": "", "secret_key": ""}):
            assert lf.get_client() is None

    def test_singleton_caching(self, lf):
        mock_config = {"enabled": True, "public_key": "pk-test", "secret_key": "sk-test", "host": "https://test.langfuse.com", "flush_at": 15, "flush_interval": 5.0, "environment": "production"}
        mock_client = MagicMock()
        with patch.object(lf, "get_langfuse_config", return_value=mock_config):
            with patch("langfuse.Langfuse", return_value=mock_client):
                with patch.object(lf, "_register_callbacks"):
                    c1 = lf.get_client()
                    c2 = lf.get_client()
        assert c1 is c2

    def test_reset_clears_singleton(self, lf):
        lf._client = MagicMock()
        lf._client_initialized = True
        lf.reset_client()
        assert lf._client is None
        assert lf._client_initialized is False

    def test_reset_removes_all_callbacks(self, lf):
        """reset_client() must remove the logger from all 4 LiteLLM callback lists."""
        import litellm
        mock_logger = MagicMock()
        lf._generation_logger = mock_logger
        lf._callbacks_registered = True
        lf._client = MagicMock()
        lf._client_initialized = True
        litellm.success_callback.append(mock_logger)
        litellm.failure_callback.append(mock_logger)
        litellm._async_success_callback.append(mock_logger)
        litellm._async_failure_callback.append(mock_logger)
        lf.reset_client()
        assert mock_logger not in litellm.success_callback
        assert mock_logger not in litellm.failure_callback
        assert mock_logger not in litellm._async_success_callback
        assert mock_logger not in litellm._async_failure_callback
        assert lf._generation_logger is None


# Callback Registration Tests

class TestCallbacks:

    def test_registers_generation_logger(self, lf):
        import litellm
        litellm.success_callback.clear()
        litellm.failure_callback.clear()
        lf._callbacks_registered = False
        lf._generation_logger = None
        lf._register_callbacks()
        assert len(litellm.success_callback) >= 1
        assert lf._callbacks_registered is True
        assert lf._generation_logger is not None

    def test_no_double_registration(self, lf):
        import litellm
        litellm.success_callback.clear()
        litellm.failure_callback.clear()
        lf._callbacks_registered = False
        lf._generation_logger = None
        lf._register_callbacks()
        count_before = len(litellm.success_callback)
        lf._register_callbacks()  # Second call
        assert len(litellm.success_callback) == count_before


# Environment Variable Security Tests

class TestEnvVarSecurity:
    """Verify get_client() does NOT export secrets to os.environ."""

    def test_get_client_does_not_leak_secrets(self, lf, monkeypatch):
        """get_client() must not write API keys into os.environ."""
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_HOST", raising=False)
        monkeypatch.delenv("LANGFUSE_TRACING_ENVIRONMENT", raising=False)
        mock_config = {
            "enabled": True, "public_key": "pk-secret", "secret_key": "sk-secret",
            "host": "https://test.langfuse.com", "flush_at": 15,
            "flush_interval": 5.0, "environment": "production",
        }
        mock_client = MagicMock()
        with patch.object(lf, "get_langfuse_config", return_value=mock_config):
            with patch("langfuse.Langfuse", return_value=mock_client):
                with patch.object(lf, "_register_callbacks"):
                    lf.get_client()
        assert os.environ.get("LANGFUSE_PUBLIC_KEY") is None
        assert os.environ.get("LANGFUSE_SECRET_KEY") is None
        assert os.environ.get("LANGFUSE_HOST") is None

    def test_reset_does_not_pop_env_vars(self, lf, monkeypatch):
        """reset_client() must not pop env vars it never set."""
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "preexisting-pk")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "preexisting-sk")
        lf._client = MagicMock()
        lf._client_initialized = True
        lf.reset_client()
        assert os.environ.get("LANGFUSE_PUBLIC_KEY") == "preexisting-pk"
        assert os.environ.get("LANGFUSE_SECRET_KEY") == "preexisting-sk"

    def test_get_client_passes_environment_param(self, lf, monkeypatch):
        """get_client() should pass environment as a constructor param, not via env var."""
        monkeypatch.delenv("LANGFUSE_TRACING_ENVIRONMENT", raising=False)
        mock_config = {
            "enabled": True, "public_key": "pk-test", "secret_key": "sk-test",
            "host": "https://test.langfuse.com", "flush_at": 15,
            "flush_interval": 5.0, "environment": "staging",
        }
        mock_client = MagicMock()
        with patch.object(lf, "get_langfuse_config", return_value=mock_config):
            with patch("langfuse.Langfuse", return_value=mock_client) as langfuse_mock:
                with patch.object(lf, "_register_callbacks"):
                    lf.get_client()
        call_kwargs = langfuse_mock.call_args.kwargs
        assert call_kwargs.get("environment") == "staging"


# Auto-Enable Logic Tests

class TestAutoEnableLogic:
    """Verify auto-enable only fires for env-var keys, not config keys."""

    def test_config_keys_do_not_auto_enable(self, lf, monkeypatch):
        """langfuse_enabled:false with keys in config must NOT auto-enable."""
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
        config_with_keys = {
            "langfuse_enabled": False,
            "langfuse_public_key": "pk-from-config",
            "langfuse_secret_key": "sk-from-config",
        }
        with patch("helpers.plugins.get_plugin_config", return_value=config_with_keys):
            config = lf.get_langfuse_config()
        assert config["enabled"] is False

    def test_env_keys_do_auto_enable(self, lf, monkeypatch):
        """langfuse_enabled:false with keys from env vars SHOULD auto-enable."""
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-from-env")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-from-env")
        with patch("helpers.plugins.get_plugin_config", return_value={"langfuse_enabled": False}):
            config = lf.get_langfuse_config()
        assert config["enabled"] is True


# Hooks Module Key Tests

class TestHooksModuleKey:
    """Verify hooks.py resets the live sys.modules module, not a fresh throwaway."""

    def test_hooks_uses_live_module_from_sys_modules(self, lf, monkeypatch):
        """hooks.save_plugin_config must call reset_client on the sys.modules instance."""
        import sys
        # Register the module in sys.modules with the key extensions use
        key = "_a0_langfuse_lib_langfuse_client"
        monkeypatch.setitem(sys.modules, key, lf)
        lf._client = MagicMock()
        lf._client_initialized = True
        lf._config_cache = {"test": True}

        # Import and call hooks function
        import importlib.util
        hooks_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "hooks.py",
        )
        spec = importlib.util.spec_from_file_location("_test_hooks", hooks_path)
        hooks_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hooks_mod)
        hooks_mod.save_plugin_config({}, "a0_langfuse")

        # The live module in sys.modules must have been reset
        assert lf._client is None
        assert lf._client_initialized is False
        assert lf._config_cache is None


# Context Isolation Tests (contextvars)

class TestTraceContext:
    """Verify trace context uses contextvars for per-context isolation."""

    def test_set_trace_context(self, lf):
        """set_trace_context sets the current trace id and session id."""
        lf.set_trace_context("new-trace-id", "new-session")
        assert lf._current_trace_id.get() == "new-trace-id"
        assert lf._current_session_id.get() == "new-session"

    def test_clear_trace_context(self, lf):
        """clear_trace_context resets to empty strings via .set('')."""
        lf.set_trace_context("some-trace", "some-session")
        lf.clear_trace_context()
        assert lf._current_trace_id.get() == ""
        assert lf._current_session_id.get() == ""

    def test_context_isolation_between_contexts(self, lf):
        """Context vars must isolate values across copy_context boundaries."""
        import contextvars
        lf.set_trace_context("trace-A", "session-A")
        ctx = contextvars.copy_context()

        def child():
            lf.set_trace_context("trace-B", "session-B")
            return lf._current_trace_id.get(), lf._current_session_id.get()

        child_result = ctx.run(child)
        assert child_result == ("trace-B", "session-B")
        # Parent context must NOT be affected by child mutation
        assert lf._current_trace_id.get() == "trace-A"
        assert lf._current_session_id.get() == "session-A"

    def test_clear_trace_context_does_not_leak(self, lf):
        """Clearing in a child context must not affect parent."""
        import contextvars
        lf.set_trace_context("parent-trace", "parent-session")
        ctx = contextvars.copy_context()

        def child():
            lf.clear_trace_context()
            return lf._current_trace_id.get()

        child_result = ctx.run(child)
        assert child_result == ""
        assert lf._current_trace_id.get() == "parent-trace"


# Generation Logger Tests

class TestGenerationLogger:
    """Tests for LangfuseGenerationLogger._create_generation()."""

    def _get_logger(self, lf):
        """Register callbacks to instantiate the LangfuseGenerationLogger."""
        import litellm
        litellm.success_callback.clear()
        litellm.failure_callback.clear()
        litellm._async_success_callback.clear()
        litellm._async_failure_callback.clear()
        lf._callbacks_registered = False
        lf._generation_logger = None
        lf._original_acompletion = None
        lf._original_completion = None
        lf._original_aresponses = None
        lf._original_responses = None
        lf._register_callbacks()
        return lf._generation_logger

    def test_create_generation_with_dict_response(self, lf):
        """Dict-style response_obj with usage should extract token counts."""
        mock_client = MagicMock()
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.set_trace_context("trace-1", "session-1")
            logger_obj = self._get_logger(lf)
            kwargs = {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]}
            response_obj = {
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                "choices": [{"message": {"content": "hello"}}],
            }
            logger_obj._create_generation(kwargs, response_obj, None, None, error=False)
        mock_client.start_as_current_observation.assert_called_once()
        call_kwargs = mock_client.start_as_current_observation.call_args.kwargs
        assert call_kwargs["usage_details"]["input"] == 10
        assert call_kwargs["usage_details"]["output"] == 5

    def test_create_generation_with_object_response(self, lf):
        """Attribute-style response_obj with usage should extract token counts."""
        from types import SimpleNamespace
        mock_client = MagicMock()
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.set_trace_context("trace-2", "session-2")
            logger_obj = self._get_logger(lf)
            usage_obj = SimpleNamespace(prompt_tokens=100, completion_tokens=50, total_tokens=150)
            msg = SimpleNamespace(content="response text")
            choice = SimpleNamespace(message=msg)
            response_obj = SimpleNamespace(usage=usage_obj, choices=[choice])
            kwargs = {"model": "claude-3", "messages": [{"role": "user", "content": "test"}]}
            logger_obj._create_generation(kwargs, response_obj, None, None, error=False)
        call_kwargs = mock_client.start_as_current_observation.call_args.kwargs
        assert call_kwargs["usage_details"]["input"] == 100
        assert call_kwargs["usage_details"]["output"] == 50

    def test_create_generation_without_trace_id_returns_early(self, lf):
        """Empty trace_id should cause early return without calling client."""
        mock_client = MagicMock()
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.clear_trace_context()
            logger_obj = self._get_logger(lf)
            logger_obj._create_generation({}, {}, None, None, error=False)
        mock_client.start_as_current_observation.assert_not_called()

    def test_create_generation_truncates_output(self, lf):
        """Output longer than 2000 chars must be truncated."""
        mock_client = MagicMock()
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.set_trace_context("trace-3", "session-3")
            logger_obj = self._get_logger(lf)
            long_output = "x" * 3000
            kwargs = {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]}
            response_obj = {"choices": [{"message": {"content": long_output}}]}
            logger_obj._create_generation(kwargs, response_obj, None, None, error=False)
        call_kwargs = mock_client.start_as_current_observation.call_args.kwargs
        assert len(call_kwargs["output"]) == 2000

    def test_create_generation_truncates_input_messages(self, lf):
        """More than 5 messages must be truncated to 5."""
        mock_client = MagicMock()
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.set_trace_context("trace-4", "session-4")
            logger_obj = self._get_logger(lf)
            messages = [{"role": "user", "content": f"msg {i}"} for i in range(10)]
            kwargs = {"model": "gpt-4", "messages": messages}
            response_obj = {"choices": [{"message": {"content": "ok"}}]}
            logger_obj._create_generation(kwargs, response_obj, None, None, error=False)
        call_kwargs = mock_client.start_as_current_observation.call_args.kwargs
        # Input is now a formatted markdown string, check it contains only first 5 messages
        input_str = call_kwargs["input"]
        assert isinstance(input_str, str)
        assert "msg 0" in input_str
        assert "msg 4" in input_str
        assert "msg 5" not in input_str

    def test_create_generation_handles_exception(self, lf):
        """Exceptions inside _create_generation must be swallowed silently."""
        with patch.object(lf, "get_client", side_effect=RuntimeError("boom")):
            lf.set_trace_context("trace-5", "session-5")
            logger_obj = self._get_logger(lf)
            # Should not raise
            logger_obj._create_generation({}, {}, None, None, error=False)

    def test_create_generation_skips_streaming(self, lf):
        """Streaming calls should be skipped — _StreamingGenerationWrapper handles those."""
        mock_client = MagicMock()
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.set_trace_context("trace-stream", "session-stream")
            logger_obj = self._get_logger(lf)
            kwargs = {
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            }
            response_obj = {"choices": [{"message": {"content": "ok"}}]}
            logger_obj._create_generation(kwargs, response_obj, None, None, error=False)
        mock_client.start_as_current_observation.assert_not_called()

    def test_create_generation_extracts_cost(self, lf):
        """response_cost in kwargs should populate cost_details."""
        mock_client = MagicMock()
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.set_trace_context("trace-6", "session-6")
            logger_obj = self._get_logger(lf)
            kwargs = {
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "hi"}],
                "response_cost": 0.0025,
            }
            response_obj = {"choices": [{"message": {"content": "ok"}}]}
            logger_obj._create_generation(kwargs, response_obj, None, None, error=False)
        call_kwargs = mock_client.start_as_current_observation.call_args.kwargs
        assert call_kwargs["cost_details"]["total"] == 0.0025
        # Currency must NOT be in cost_details — Langfuse requires Dict[str, float]
        assert "currency" not in call_kwargs["cost_details"]


# Error Extraction Tests

class TestErrorExtraction:
    """Verify error metadata extraction from failure events."""

    def test_error_extraction_from_failure_event(self, lf):
        """metadata['error'] should contain actual exception text, not 'True'."""
        mock_client = MagicMock()
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.set_trace_context("trace-err", "session-err")
            # Register callbacks to get the logger instance
            import litellm
            litellm.success_callback.clear()
            litellm.failure_callback.clear()
            lf._callbacks_registered = False
            lf._generation_logger = None
            lf._register_callbacks()
            logger_obj = lf._generation_logger
            kwargs = {
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "hi"}],
                "exception": ValueError("API rate limit exceeded"),
            }
            response_obj = {"choices": []}
            logger_obj._create_generation(kwargs, response_obj, None, None, error=True)
        call_kwargs = mock_client.start_as_current_observation.call_args.kwargs
        assert "rate limit exceeded" in call_kwargs["metadata"]["error"]
        assert call_kwargs["metadata"]["error"] != "True"


# Metadata Injection Tests

class TestMetadataInjection:
    """Verify trace_id injection via LiteLLM wrapper and metadata-first reading in _create_generation."""

    def _get_logger(self, lf):
        """Register callbacks to instantiate the LangfuseGenerationLogger."""
        import litellm
        litellm.success_callback.clear()
        litellm.failure_callback.clear()
        litellm._async_success_callback.clear()
        litellm._async_failure_callback.clear()
        lf._callbacks_registered = False
        lf._generation_logger = None
        lf._original_acompletion = None
        lf._original_completion = None
        lf._original_aresponses = None
        lf._original_responses = None
        lf._register_callbacks()
        return lf._generation_logger

    def test_create_generation_reads_trace_id_from_metadata(self, lf):
        """_create_generation should use langfuse_trace_id from kwargs metadata."""
        mock_client = MagicMock()
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.clear_trace_context()
            logger_obj = self._get_logger(lf)
            kwargs = {
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "hi"}],
                "metadata": {"langfuse_trace_id": "from-metadata"},
            }
            response_obj = {"choices": [{"message": {"content": "ok"}}]}
            logger_obj._create_generation(kwargs, response_obj, None, None, error=False)
        mock_client.start_as_current_observation.assert_called_once()
        call_kwargs = mock_client.start_as_current_observation.call_args.kwargs
        assert call_kwargs["trace_context"]["trace_id"] == "from-metadata"

    def test_create_generation_metadata_overrides_contextvar(self, lf):
        """Metadata trace_id should take precedence over ContextVar."""
        mock_client = MagicMock()
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.set_trace_context("from-contextvar", "sess")
            logger_obj = self._get_logger(lf)
            kwargs = {
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "hi"}],
                "metadata": {"langfuse_trace_id": "from-metadata"},
            }
            response_obj = {"choices": [{"message": {"content": "ok"}}]}
            logger_obj._create_generation(kwargs, response_obj, None, None, error=False)
        call_kwargs = mock_client.start_as_current_observation.call_args.kwargs
        assert call_kwargs["trace_context"]["trace_id"] == "from-metadata"

    def test_create_generation_falls_back_to_contextvar(self, lf):
        """Without metadata trace_id, should fall back to ContextVar."""
        mock_client = MagicMock()
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.set_trace_context("from-cv", "sess")
            logger_obj = self._get_logger(lf)
            kwargs = {
                "model": "gpt-4",
                "messages": [{"role": "user", "content": "hi"}],
            }
            response_obj = {"choices": [{"message": {"content": "ok"}}]}
            logger_obj._create_generation(kwargs, response_obj, None, None, error=False)
        call_kwargs = mock_client.start_as_current_observation.call_args.kwargs
        assert call_kwargs["trace_context"]["trace_id"] == "from-cv"

    def test_wrap_litellm_calls_saves_originals(self, lf):
        """After _register_callbacks, originals should be saved."""
        import litellm
        litellm.success_callback.clear()
        litellm.failure_callback.clear()
        lf._callbacks_registered = False
        lf._generation_logger = None
        lf._original_acompletion = None
        lf._original_completion = None
        lf._register_callbacks()
        assert lf._original_acompletion is not None
        assert lf._original_completion is not None
        # Restore to avoid polluting other tests
        litellm.acompletion = lf._original_acompletion
        litellm.completion = lf._original_completion
        lf._original_acompletion = None
        lf._original_completion = None

    def test_reset_restores_original_litellm_calls(self, lf):
        """reset_client should restore original litellm functions and clear globals."""
        import litellm
        litellm.success_callback.clear()
        litellm.failure_callback.clear()
        lf._callbacks_registered = False
        lf._generation_logger = None
        lf._original_acompletion = None
        lf._original_completion = None
        lf._client = MagicMock()
        lf._client_initialized = True
        lf._register_callbacks()
        assert lf._original_acompletion is not None
        lf.reset_client()
        assert lf._original_acompletion is None
        assert lf._original_completion is None

    def test_sync_completion_wrapper_injects_metadata(self, lf):
        """Wrapped litellm.completion should inject langfuse_trace_id into metadata."""
        import litellm
        # Save state
        saved_orig_completion = lf._original_completion
        saved_litellm_completion = litellm.completion

        # Reset so _wrap_litellm_calls wraps fresh
        lf._original_acompletion = None
        lf._original_completion = None

        # Install a mock as the 'original' so the wrapper calls our mock, not real litellm
        captured_kwargs = {}
        def mock_completion(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return "mock-result"
        litellm.completion = mock_completion

        # Now wrap — this saves mock_completion as _original_completion
        lf._wrap_litellm_calls()
        assert lf._original_completion is mock_completion

        # Set trace context and call the wrapper
        lf.set_trace_context("wrapper-test-trace", "sess")
        result = litellm.completion(model="gpt-4", messages=[{"role": "user", "content": "hi"}])
        assert result == "mock-result"
        assert captured_kwargs.get("metadata", {}).get("langfuse_trace_id") == "wrapper-test-trace"

        # Cleanup
        litellm.completion = saved_litellm_completion
        lf._original_completion = saved_orig_completion
        lf._original_acompletion = None
        lf.clear_trace_context()

    def test_stream_options_injected_when_streaming(self, lf):
        """Verify stream_options.include_usage is injected for streaming calls."""
        import asyncio
        import litellm

        # Save state
        saved_orig_acompletion = lf._original_acompletion
        saved_litellm_acompletion = litellm.acompletion

        # Install a mock as the 'original' so the wrapper calls our mock
        captured_kwargs = {}
        async def mock_acompletion(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return MagicMock()

        # Reset and set up for fresh wrapping
        lf._original_acompletion = None
        lf._original_completion = None
        litellm.acompletion = mock_acompletion

        # Wrap — saves mock_acompletion as _original_acompletion
        lf._wrap_litellm_calls()

        # Set trace context
        lf.set_trace_context("test-trace", "test-session")

        # Call the wrapper with stream=True
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                litellm.acompletion(model="test", messages=[], stream=True)
            )
        finally:
            loop.close()

        assert "stream_options" in captured_kwargs
        assert captured_kwargs["stream_options"]["include_usage"] is True

        # Cleanup
        litellm.acompletion = saved_litellm_acompletion
        lf._original_acompletion = saved_orig_acompletion
        lf._original_completion = None
        lf.clear_trace_context()


# Regression tests: Responses API streaming GENERATION capture

class TestResponsesApiStreamingWrapper:
    """Verify that _wrapped_aresponses/_wrapped_responses wrap streaming iterators."""

    def test_aresponses_wraps_streaming_response(self, lf):
        """_wrapped_aresponses must wrap streaming iterators with _StreamingGenerationWrapper."""
        import asyncio
        import litellm

        saved_aresponses = lf._original_aresponses
        saved_litellm_aresponses = getattr(litellm, "aresponses", None)

        captured_kwargs = {}
        class FakeStream:
            def __aiter__(self):
                return self
            async def __anext__(self):
                raise StopAsyncIteration

        async def mock_aresponses(*args, **kwargs):
            captured_kwargs.update(kwargs)
            return FakeStream()

        lf._original_aresponses = None
        lf._original_acompletion = None
        lf._original_completion = None
        litellm.aresponses = mock_aresponses

        lf._wrap_litellm_calls()
        lf.set_trace_context("responses-test-trace", "sess")

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                litellm.aresponses(model="test", messages=[], stream=True)
            )
        finally:
            loop.close()

        assert isinstance(result, lf._StreamingGenerationWrapper)
        assert result._trace_id == "responses-test-trace"
        assert captured_kwargs.get("stream_options", {}).get("include_usage") is True

        litellm.aresponses = saved_litellm_aresponses
        lf._original_aresponses = saved_aresponses
        lf._original_acompletion = None
        lf._original_completion = None
        lf.clear_trace_context()

    def test_aresponses_does_not_wrap_non_streaming(self, lf):
        """_wrapped_aresponses must NOT wrap non-streaming responses."""
        import asyncio
        import litellm

        saved_aresponses = lf._original_aresponses
        saved_litellm_aresponses = getattr(litellm, "aresponses", None)

        async def mock_aresponses(*args, **kwargs):
            return {"id": "non-streaming-result"}

        lf._original_aresponses = None
        lf._original_acompletion = None
        lf._original_completion = None
        litellm.aresponses = mock_aresponses

        lf._wrap_litellm_calls()
        lf.set_trace_context("test-trace", "sess")

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                litellm.aresponses(model="test", messages=[], stream=False)
            )
        finally:
            loop.close()

        assert not isinstance(result, lf._StreamingGenerationWrapper)
        assert result == {"id": "non-streaming-result"}

        litellm.aresponses = saved_litellm_aresponses
        lf._original_aresponses = saved_aresponses
        lf._original_acompletion = None
        lf._original_completion = None
        lf.clear_trace_context()

    def test_aresponses_no_wrap_without_trace_id(self, lf):
        """_wrapped_aresponses must NOT wrap when trace_id is empty."""
        import asyncio
        import litellm

        saved_aresponses = lf._original_aresponses
        saved_litellm_aresponses = getattr(litellm, "aresponses", None)

        class FakeStream:
            def __aiter__(self):
                return self
            async def __anext__(self):
                raise StopAsyncIteration

        async def mock_aresponses(*args, **kwargs):
            return FakeStream()

        lf._original_aresponses = None
        lf._original_acompletion = None
        lf._original_completion = None
        litellm.aresponses = mock_aresponses

        lf._wrap_litellm_calls()
        lf.clear_trace_context()

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                litellm.aresponses(model="test", messages=[], stream=True)
            )
        finally:
            loop.close()

        assert not isinstance(result, lf._StreamingGenerationWrapper)

        litellm.aresponses = saved_litellm_aresponses
        lf._original_aresponses = saved_aresponses
        lf._original_acompletion = None
        lf._original_completion = None


class TestFormatAgnosticHelpers:
    """Verify _normalize_usage, _find_usage, _extract_delta_text handle both formats."""

    def test_normalize_usage_chat_completions_object(self, lf):
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=50, total_tokens=150,
                                completion_tokens_details=None, prompt_tokens_details=None)
        result = lf._normalize_usage(usage)
        assert result["input"] == 100
        assert result["output"] == 50
        assert result["total"] == 150
        assert result["unit"] == "TOKENS"

    def test_normalize_usage_responses_api_object(self, lf):
        """Responses API uses input_tokens/output_tokens instead of prompt_tokens."""
        usage = SimpleNamespace(input_tokens=200, output_tokens=80, total_tokens=280)
        result = lf._normalize_usage(usage)
        assert result["input"] == 200
        assert result["output"] == 80
        assert result["total"] == 280

    def test_normalize_usage_dict(self, lf):
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        result = lf._normalize_usage(usage)
        assert result["input"] == 10
        assert result["output"] == 5

    def test_normalize_usage_extracts_reasoning_tokens(self, lf):
        usage = {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "completion_tokens_details": {"reasoning_tokens": 30},
            "prompt_tokens_details": {"cached_tokens": 20},
        }
        result = lf._normalize_usage(usage)
        assert result["input"] == 100
        assert result["output"] == 50
        assert result["reasoning"] == 30
        assert result["cached_input"] == 20

    def test_compute_cost_details_glm52(self, lf):
        """Cost should be computed from token counts and model pricing."""
        usage = {"input": 1000000, "output": 500000, "total": 1500000, "unit": "TOKENS"}
        result = lf._compute_cost_details("glm-5.2", usage)
        assert result is not None
        assert result["input"] == 1.4
        assert result["output"] == 2.2
        assert result["total"] == 3.6
        # Currency must NOT be in cost_details — Langfuse requires Dict[str, float]
        assert "currency" not in result

    def test_compute_cost_details_with_reasoning(self, lf):
        """Reasoning tokens should be billed as output tokens."""
        usage = {"input": 100000, "output": 50000, "total": 150000, "reasoning": 30000, "unit": "TOKENS"}
        result = lf._compute_cost_details("glm-5.2", usage)
        assert result is not None
        # input: 100K/1M * $1.40 = $0.14
        assert abs(result["input"] - 0.14) < 0.001
        # output: (50K + 30K)/1M * $4.40 = $0.352
        assert abs(result["output"] - 0.352) < 0.001

    def test_compute_cost_details_unknown_model(self, lf):
        """Unknown models should return None."""
        result = lf._compute_cost_details("unknown-model", {"input": 100, "output": 50})
        assert result is None

    def test_compute_cost_details_strips_provider_prefix(self, lf):
        """Provider prefix like openai/ should be stripped before lookup."""
        usage = {"input": 1000000, "output": 0, "total": 1000000, "unit": "TOKENS"}
        result = lf._compute_cost_details("openai/glm-5.2", usage)
        assert result is not None
        assert result["input"] == 1.4

    def test_compute_cost_details_empty_usage(self, lf):
        """Empty usage should return None."""
        assert lf._compute_cost_details("glm-5.2", {}) is None
        assert lf._compute_cost_details("glm-5.2", None) is None

    def test_compute_cost_details_claude_fable5(self, lf):
        """Claude Fable 5 via Venice AI pricing: $12/1M in, $60/1M out."""
        usage = {"input": 1000000, "output": 1000000, "total": 2000000, "unit": "TOKENS"}
        result = lf._compute_cost_details("claude-fable-5", usage)
        assert result is not None
        assert result["input"] == 12.0
        assert result["output"] == 60.0
        assert result["total"] == 72.0
        # Must use 'total' key, not 'overall', for Langfuse calculatedTotalCost
        assert "overall" not in result

    def test_compute_cost_details_claude_sonnet5(self, lf):
        """Claude Sonnet 5 via Venice AI pricing: $3/1M in, $15/1M out."""
        usage = {"input": 1000000, "output": 500000, "total": 1500000, "unit": "TOKENS"}
        result = lf._compute_cost_details("claude-sonnet-5", usage)
        assert result is not None
        assert result["input"] == 3.0
        assert result["output"] == 7.5
        assert result["total"] == 10.5

    def test_compute_cost_details_claude_with_cached_input(self, lf):
        """Cached input tokens should be billed at reduced rate."""
        # claude-fable-5: $12/1M input, $1.2/1M cache_input, $60/1M output
        usage = {
            "input": 1000000, "output": 100000, "total": 1100000,
            "cached_input": 800000, "unit": "TOKENS",
        }
        result = lf._compute_cost_details("claude-fable-5", usage)
        assert result is not None
        # regular_input = 1M - 800K = 200K → 200K/1M * $12 = $2.4
        # cached_input = 800K/1M * $1.2 = $0.96
        # total input cost = $2.4 + $0.96 = $3.36
        assert abs(result["input"] - 3.36) < 0.001
        # output: 100K/1M * $60 = $6.0
        assert abs(result["output"] - 6.0) < 0.001

    def test_compute_cost_details_strips_venice_prefix(self, lf):
        """Venice provider prefix should be stripped before lookup."""
        usage = {"input": 1000000, "output": 0, "total": 1000000, "unit": "TOKENS"}
        result = lf._compute_cost_details("venice/claude-sonnet-5", usage)
        assert result is not None
        assert result["input"] == 3.0

    def test_normalize_usage_dict_responses_format(self, lf):
        usage = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
        result = lf._normalize_usage(usage)
        assert result["input"] == 10
        assert result["output"] == 5

    def test_find_usage_chat_completions(self, lf):
        chunk = MagicMock(usage=MagicMock(prompt_tokens=30, completion_tokens=10, total_tokens=40))
        usage = lf._find_usage(chunk)
        assert usage is not None
        assert lf._normalize_usage(usage)["input"] == 30

    def test_find_usage_responses_nested(self, lf):
        """Responses API nests usage under response.usage."""
        usage = SimpleNamespace(input_tokens=50, output_tokens=20, total_tokens=70)
        resp = SimpleNamespace(usage=usage)
        chunk = SimpleNamespace(usage=None, response=resp)
        usage = lf._find_usage(chunk)
        assert usage is not None
        assert lf._normalize_usage(usage)["input"] == 50

    def test_find_usage_responses_dict_nested(self, lf):
        """Responses API dict format: chunk['response']['usage']."""
        chunk = {
            "usage": None,
            "response": {"usage": {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8}},
        }
        usage = lf._find_usage(chunk)
        assert usage is not None
        assert lf._normalize_usage(usage)["input"] == 5

    def test_find_usage_returns_none_when_absent(self, lf):
        resp = SimpleNamespace(usage=None)
        chunk = SimpleNamespace(usage=None, response=resp)
        assert lf._find_usage(chunk) is None

    def test_extract_delta_text_chat_completions(self, lf):
        delta = MagicMock(content="Hello ")
        chunk = MagicMock(choices=[MagicMock(delta=delta)])
        assert lf._extract_delta_text(chunk) == "Hello "

    def test_extract_delta_text_responses_string_delta(self, lf):
        """Responses API output_text.delta events have a string .delta attribute."""
        chunk = MagicMock()
        chunk.choices = None
        chunk.delta = "world!"
        assert lf._extract_delta_text(chunk) == "world!"

    def test_extract_delta_text_returns_none_for_empty(self, lf):
        chunk = MagicMock()
        chunk.choices = []
        chunk.delta = None
        chunk.text = None
        assert lf._extract_delta_text(chunk) is None

    def test_streaming_wrapper_extracts_responses_api_usage(self, lf):
        """_StreamingGenerationWrapper should extract usage from Responses API events."""
        lf._client = None
        lf._client_initialized = False

        class FakeChunk:
            def __init__(self, text, usage=None):
                self.choices = None
                self.delta = text
                self.usage = usage
                self.response = None

        chunks = [
            FakeChunk("Hello ", None),
            FakeChunk("world!", None),
            FakeChunk(None, SimpleNamespace(input_tokens=42, output_tokens=7, total_tokens=49)),
        ]

        class FakeAsyncIterator:
            def __init__(self, items):
                self._items = list(items)
            def __aiter__(self):
                return self
            async def __anext__(self):
                if not self._items:
                    raise StopAsyncIteration
                return self._items.pop(0)

        wrapper = lf._StreamingGenerationWrapper(
            FakeAsyncIterator(chunks),
            {"model": "test-model", "messages": [{"role": "user", "content": "hi"}]},
            "trace-123",
            is_async=True,
        )

        import asyncio
        collected = []
        async def consume():
            async for chunk in wrapper:
                collected.append(chunk)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(consume())
        finally:
            loop.close()

        assert len(collected) == 3
        assert wrapper._output_parts == ["Hello ", "world!"]
        assert wrapper._usage["input"] == 42
        assert wrapper._usage["output"] == 7
        assert wrapper._usage["total"] == 49

    def test_aclose_drains_remaining_chunks_for_usage(self, lf):
        """aclose() must drain remaining chunks to capture usage from final chunk.

        A0's transport calls aclose() which may fire before the final
        usage-bearing chunk has been consumed via __anext__. The usage data
        in streaming comes in the last chunk (before [DONE]).
        """
        lf._client = None
        lf._client_initialized = False

        class FakeChunk:
            def __init__(self, text=None, usage=None):
                self.choices = None if usage else [MagicMock(delta=MagicMock(content=text))]
                self.delta = None
                self.usage = usage
                self.response = None

        class FakeAsyncIterator:
            def __init__(self, items):
                self._items = list(items)
            def __aiter__(self):
                return self
            async def __anext__(self):
                if not self._items:
                    raise StopAsyncIteration
                return self._items.pop(0)

        chunks = [
            FakeChunk(text="Hello"),
            FakeChunk(text=" world!"),
            # Final chunk has usage but NO content
            FakeChunk(usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20, total_tokens=120)),
        ]

        wrapper = lf._StreamingGenerationWrapper(
            FakeAsyncIterator(chunks),
            {"model": "test-model", "messages": [{"role": "user", "content": "hi"}]},
            "trace-aclose-test",
            is_async=True,
        )

        # Consume only the first chunk (simulates transport closing early)
        import asyncio
        async def partial_consume():
            await wrapper.__anext__()  # Only get first chunk
            await wrapper.aclose()     # Transport closes the stream

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(partial_consume())
        finally:
            loop.close()

        # aclose() should have drained the remaining chunks
        assert wrapper._generation_finalized is True
        assert wrapper._usage.get("input") == 100
        assert wrapper._usage.get("output") == 20
        assert wrapper._usage.get("total") == 120


class TestSensitiveDataFiltering:
    """Verify sensitive data filtering for tool arguments in Langfuse spans."""

    def test_filters_api_key(self, lf):
        """Keys containing 'key' should be redacted."""
        result = lf._filter_sensitive_args({"api_key": "sk-secret123", "query": "hello"})
        assert result["api_key"] == "[REDACTED]"
        assert result["query"] == "hello"

    def test_filters_token(self, lf):
        """Keys containing 'token' should be redacted."""
        result = lf._filter_sensitive_args({"access_token": "abc", "code": "print(1)"})
        assert result["access_token"] == "[REDACTED]"
        assert result["code"] == "print(1)"

    def test_filters_password(self, lf):
        """Keys containing 'password' should be redacted."""
        result = lf._filter_sensitive_args({"password": "secret", "passwd": "secret2"})
        assert result["password"] == "[REDACTED]"
        assert result["passwd"] == "[REDACTED]"

    def test_filters_secret_and_credential(self, lf):
        """Keys containing 'secret' or 'credential' should be redacted."""
        result = lf._filter_sensitive_args({"client_secret": "xyz", "credential": "abc"})
        assert result["client_secret"] == "[REDACTED]"
        assert result["credential"] == "[REDACTED]"

    def test_truncates_long_values(self, lf):
        """Non-sensitive values longer than 500 chars should be truncated."""
        long_val = "x" * 600
        result = lf._filter_sensitive_args({"code": long_val})
        assert len(result["code"]) == 500

    def test_preserves_short_values(self, lf):
        """Short non-sensitive values should be unchanged."""
        result = lf._filter_sensitive_args({"code": "print('hello')"})
        assert result["code"] == "print('hello')"

    def test_non_dict_returns_as_is(self, lf):
        """Non-dict input should be returned unchanged."""
        result = lf._filter_sensitive_args("not a dict")
        assert result == "not a dict"

    def test_case_insensitive_key_matching(self, lf):
        """Key matching should be case-insensitive."""
        result = lf._filter_sensitive_args({"API_KEY": "secret", "Token": "abc"})
        assert result["API_KEY"] == "[REDACTED]"
        assert result["Token"] == "[REDACTED]"

    def test_recursively_redacts_nested_dict_and_list_values(self, lf):
        """Nested dict/list values should preserve key-level redaction semantics recursively."""
        result = lf._filter_sensitive_args({
            "payload": {
                "auth": {"token": "nested-secret"},
                "items": [
                    {"password": "pw-1"},
                    {"note": "safe"},
                ],
            }
        })
        assert result["payload"]["auth"] == "[REDACTED]"
        assert result["payload"]["items"][0]["password"] == "[REDACTED]"
        assert result["payload"]["items"][1]["note"] == "safe"

    def test_recursively_truncates_nested_non_sensitive_values(self, lf):
        """Nested non-sensitive string values should still honor max-length limits."""
        result = lf._filter_sensitive_args({
            "payload": {
                "note": "x" * 700,
                "items": [{"detail": "y" * 700}],
            }
        })
        assert len(result["payload"]["note"]) == 500
        assert len(result["payload"]["items"][0]["detail"]) == 500

    def test_format_generation_input_redacts_nested_sensitive_content(self, lf):
        """Prompt capture should redact nested sensitive values before stringifying messages."""
        prompt = lf._format_generation_input([
            {
                "role": "user",
                "content": {
                    "note": "hello",
                    "nested": {"api_key": "sk-secret-value"},
                },
            }
        ])
        assert "[REDACTED]" in prompt
        assert "sk-secret-value" not in prompt


class TestParentObservation:
    """Verify parent observation ContextVar for GENERATION nesting."""

    def test_set_and_get_parent_obs(self, lf):
        """set_parent_observation stores observation for retrieval."""
        lf.clear_parent_observation()
        mock_obs = MagicMock()
        lf.set_parent_observation(mock_obs)
        assert lf._current_parent_obs.get() is mock_obs
        lf.clear_parent_observation()

    def test_clear_parent_obs(self, lf):
        """clear_parent_observation resets to None."""
        lf.set_parent_observation(MagicMock())
        lf.clear_parent_observation()
        assert lf._current_parent_obs.get() is None

    def test_clear_trace_context_clears_parent(self, lf):
        """clear_trace_context should also clear parent observation."""
        lf.set_parent_observation(MagicMock())
        lf.clear_trace_context()
        assert lf._current_parent_obs.get() is None

    def test_context_isolation(self, lf):
        """Parent obs should be isolated between async contexts."""
        import asyncio
        results = {}
        async def set_and_check(key, obs):
            lf.set_parent_observation(obs)
            await asyncio.sleep(0.01)
            results[key] = lf._current_parent_obs.get()
        mock1, mock2 = MagicMock(name="obs1"), MagicMock(name="obs2")
        async def run_both():
            await asyncio.gather(set_and_check("a", mock1), set_and_check("b", mock2))
        asyncio.run(run_both())
        assert results["a"] is mock1
        assert results["b"] is mock2


class TestStreamingWrapperTimestamps:
    """Verify TTFT tracking and latency capture in streaming wrapper."""

    def test_first_chunk_time_tracked(self, lf):
        """_first_chunk_time should be set after processing first chunk."""
        from types import SimpleNamespace
        class FakeSyncIter:
            def __init__(self, items):
                self._items = list(items)
            def __iter__(self):
                return self
            def __next__(self):
                if not self._items:
                    raise StopIteration
                return self._items.pop(0)

        chunks = [
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Hello"))]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=" world"))]),
        ]
        with patch.object(lf, "get_client", return_value=None):
            wrapper = lf._StreamingGenerationWrapper(
                FakeSyncIter(chunks),
                {"model": "test", "messages": [{"role": "user", "content": "hi"}]},
                "trace-ttft-test",
                is_async=False,
            )
            assert wrapper._first_chunk_time is None
            next(wrapper)
            assert wrapper._first_chunk_time is not None

    def test_observation_entered_at_init(self, lf):
        """Observation context should be entered at wrapper init for accurate latency."""
        class FakeSyncIter:
            def __iter__(self):
                return self
            def __next__(self):
                raise StopIteration

        mock_client = MagicMock()
        mock_obs_cm = MagicMock()
        mock_obs = MagicMock()
        mock_obs_cm.__enter__ = MagicMock(return_value=mock_obs)
        mock_obs_cm.__exit__ = MagicMock(return_value=False)
        mock_client.start_as_current_observation = MagicMock(return_value=mock_obs_cm)

        with patch.object(lf, "get_client", return_value=mock_client):
            lf.clear_parent_observation()
            wrapper = lf._StreamingGenerationWrapper(
                FakeSyncIter(),
                {"model": "test", "messages": [{"role": "user", "content": "hi"}]},
                "trace-latency-test",
                is_async=False,
            )
            assert wrapper._obs is mock_obs
            assert wrapper._obs_cm is mock_obs_cm
            mock_obs_cm.__enter__.assert_called_once()

    def test_finalize_calls_update_and_exit(self, lf):
        """_finalize_generation should update obs with model/usage/cost and exit context."""
        class FakeSyncIter:
            def __iter__(self):
                return self
            def __next__(self):
                raise StopIteration

        mock_client = MagicMock()
        mock_obs_cm = MagicMock()
        mock_obs = MagicMock()
        mock_obs_cm.__enter__ = MagicMock(return_value=mock_obs)
        mock_obs_cm.__exit__ = MagicMock(return_value=False)
        mock_client.start_as_current_observation = MagicMock(return_value=mock_obs_cm)

        with patch.object(lf, "get_client", return_value=mock_client):
            lf.clear_parent_observation()
            wrapper = lf._StreamingGenerationWrapper(
                FakeSyncIter(),
                {"model": "glm-5.2", "messages": [{"role": "user", "content": "hi"}]},
                "trace-finalize-test",
                is_async=False,
            )
            wrapper._usage = {"input": 100, "output": 50, "total": 150}
            wrapper._output_parts = ["response text"]
            from datetime import datetime
            wrapper._first_chunk_time = datetime.now()
            wrapper._finalize_generation()

            mock_obs.update.assert_called_once()
            call_kwargs = mock_obs.update.call_args.kwargs
            assert call_kwargs["model"] == "glm-5.2"
            assert call_kwargs["usage_details"]["input"] == 100
            assert call_kwargs["cost_details"] is not None
            assert call_kwargs["completion_start_time"] is not None
            mock_obs_cm.__exit__.assert_called_once()

    def test_finalize_idempotent(self, lf):
        """_finalize_generation should be idempotent."""
        class FakeSyncIter:
            def __iter__(self):
                return self
            def __next__(self):
                raise StopIteration

        mock_client = MagicMock()
        mock_obs_cm = MagicMock()
        mock_obs = MagicMock()
        mock_obs_cm.__enter__ = MagicMock(return_value=mock_obs)
        mock_obs_cm.__exit__ = MagicMock(return_value=False)
        mock_client.start_as_current_observation = MagicMock(return_value=mock_obs_cm)

        with patch.object(lf, "get_client", return_value=mock_client):
            lf.clear_parent_observation()
            wrapper = lf._StreamingGenerationWrapper(
                FakeSyncIter(),
                {"model": "test", "messages": [{"role": "user", "content": "hi"}]},
                "trace-idempotent-test",
                is_async=False,
            )
            wrapper._finalize_generation()
            wrapper._finalize_generation()
            assert mock_obs.update.call_count == 1

    def test_aclose_bounds_drain_and_finalizes_partial_observation(self, lf):
        """aclose() should return promptly on slow streams and still finalize partial observations."""
        import asyncio
        import time
        from types import SimpleNamespace

        class SlowAsyncIter:
            def __init__(self):
                self.calls = 0
                self.closed = False

            def __aiter__(self):
                return self

            async def __anext__(self):
                self.calls += 1
                if self.calls == 1:
                    return SimpleNamespace(
                        choices=[SimpleNamespace(delta=SimpleNamespace(content="Hello"))]
                    )
                await asyncio.sleep(0.5)
                return SimpleNamespace(
                    choices=[SimpleNamespace(delta=SimpleNamespace(content=" late"))]
                )

            async def aclose(self):
                self.closed = True

        mock_client = MagicMock()
        mock_obs_cm = MagicMock()
        mock_obs = MagicMock()
        mock_obs_cm.__enter__ = MagicMock(return_value=mock_obs)
        mock_obs_cm.__exit__ = MagicMock(return_value=False)
        mock_client.start_as_current_observation = MagicMock(return_value=mock_obs_cm)

        with patch.object(lf, "get_client", return_value=mock_client), \
             patch.object(lf, "_STREAM_ACLOSE_DRAIN_TIMEOUT_S", 0.01), \
             patch.object(lf, "_STREAM_ACLOSE_MAX_CHUNKS", 2):
            lf.clear_parent_observation()
            wrapper = lf._StreamingGenerationWrapper(
                SlowAsyncIter(),
                {"model": "glm-5.2", "messages": [{"role": "user", "content": "hi"}]},
                "trace-timeout-test",
                is_async=True,
            )

            async def partial_then_close():
                await wrapper.__anext__()
                started = time.perf_counter()
                await wrapper.aclose()
                return time.perf_counter() - started

            elapsed = asyncio.run(partial_then_close())

        assert elapsed < 0.2
        assert wrapper._generation_finalized is True
        mock_obs.update.assert_called_once()
        mock_obs_cm.__exit__.assert_called_once()
        assert wrapper._iterator.closed is True


class TestReleaseTagging:
    """Task 1: A0 version passed as release= to the Langfuse() constructor."""

    def test_release_tag_set(self, lf):
        """get_client passes release from _get_release() to Langfuse constructor."""
        import sys
        mock_config = {
            "enabled": True, "public_key": "pk-test", "secret_key": "sk-test",
            "host": "https://test.langfuse.com", "flush_at": 15,
            "flush_interval": 5.0, "environment": "production",
        }
        mock_langfuse_module = MagicMock()
        mock_langfuse_cls = MagicMock()
        mock_langfuse_module.Langfuse = mock_langfuse_cls
        with patch.object(lf, "get_langfuse_config", return_value=mock_config), \
             patch.object(lf, "_get_release", return_value="v9.9-test"), \
             patch.object(lf, "_register_callbacks"), \
             patch.dict(sys.modules, {"langfuse": mock_langfuse_module}):
            client = lf.get_client()
            assert client is not None
            _, called_kwargs = mock_langfuse_cls.call_args
            assert called_kwargs.get("release") == "v9.9-test"

    def test_release_none_when_settings_unavailable(self, lf):
        """_get_release returns None gracefully when helpers.settings fails."""
        import sys
        with patch.dict(sys.modules, {"helpers.settings": None, "helpers": None}):
            assert lf._get_release() is None

    def test_release_reads_settings_version(self, lf):
        """_get_release reads settings['version'] via helpers.settings."""
        import sys
        mock_settings_mod = MagicMock()
        mock_settings_mod.get_settings.return_value = {"version": "v2.2-38-gab31aa86"}
        with patch.dict(sys.modules, {"helpers.settings": mock_settings_mod}):
            assert lf._get_release() == "v2.2-38-gab31aa86"


class TestImplicitFeedbackScores:
    """Task 2: score previous trace on follow-up (positive) or stop (negative).

    Uses completion-flag pattern (VERIFIED: monologue_end never fires on killed
    tasks, so stopped-detection reads a pending-trace flag set at trace start
    and cleared only on normal completion).
    """

    def test_stopped_score(self, lf):
        """A pending (uncleared) trace from a killed task scores user-stopped=0."""
        mock_agent = MagicMock()
        mock_agent.get_data.side_effect = lambda key: {
            "lf_pending_trace_id": "trace-killed-123",
            "lf_last_trace_id": None,
        }.get(key)
        mock_client = MagicMock()
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.handle_monologue_start_feedback(mock_agent)

        mock_client.create_score.assert_called_once_with(
            trace_id="trace-killed-123", name="user-stopped", value=0, data_type="BOOLEAN"
        )
        mock_agent.set_data.assert_any_call("lf_pending_trace_id", None)

    def test_followup_score(self, lf):
        """A completed previous trace (no pending) scores user-followup=1."""
        mock_agent = MagicMock()
        mock_agent.get_data.side_effect = lambda key: {
            "lf_pending_trace_id": None,
            "lf_last_trace_id": "trace-done-456",
        }.get(key)
        mock_client = MagicMock()
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.handle_monologue_start_feedback(mock_agent)

        mock_client.create_score.assert_called_once_with(
            trace_id="trace-done-456", name="user-followup", value=1, data_type="BOOLEAN"
        )
        mock_agent.set_data.assert_any_call("lf_last_trace_id", None)

    def test_no_score_first_monologue(self, lf):
        """No previous trace at all (first monologue) creates no score."""
        mock_agent = MagicMock()
        mock_agent.get_data.return_value = None
        mock_client = MagicMock()
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.handle_monologue_start_feedback(mock_agent)

        mock_client.create_score.assert_not_called()

    def test_no_score_when_no_client(self, lf):
        """Never raises and never scores when Langfuse client is unavailable."""
        mock_agent = MagicMock()
        mock_agent.get_data.side_effect = lambda key: {
            "lf_pending_trace_id": "trace-x",
        }.get(key)
        with patch.object(lf, "get_client", return_value=None):
            lf.handle_monologue_start_feedback(mock_agent)  # must not raise


class TestErrorAndQualitySignals:
    """Task 3 (scope corrected): framework-error score + 4 verified quality
    signals (misformat, repeat, tool-not-found, critical-error) + raw
    exception capture. All score the CURRENT trace via _current_trace_id.
    """

    def test_error_score(self, lf):
        """error_format hook scores framework-error=0 on the current trace."""
        mock_client = MagicMock()
        lf._current_trace_id.set("trace-current-1")
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.score_framework_error("Something broke")
        mock_client.create_score.assert_called_once_with(
            trace_id="trace-current-1", name="framework-error", value=0,
            data_type="BOOLEAN", comment="Something broke",
        )

    def test_misformat_score(self, lf):
        """hist_add_before content matching fw.msg_misformat.md scores misformat=0."""
        mock_client = MagicMock()
        lf._current_trace_id.set("trace-current-2")
        content = 'Your last message was not valid JSON or did not match the required schema.'
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.score_quality_signal(content)
        mock_client.create_score.assert_called_once_with(
            trace_id="trace-current-2", name="misformat", value=0, data_type="BOOLEAN", comment=None,
        )

    def test_repeat_score(self, lf):
        """hist_add_before content matching fw.msg_repeat.md scores repeat=0."""
        mock_client = MagicMock()
        lf._current_trace_id.set("trace-current-3")
        content = 'You have sent the same message again. You have to do something else!'
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.score_quality_signal(content)
        mock_client.create_score.assert_called_once_with(
            trace_id="trace-current-3", name="repeat", value=0, data_type="BOOLEAN", comment=None,
        )

    def test_tool_not_found_score(self, lf):
        """hist_add_before content matching fw.tool_not_found.md scores tool-not-found=0."""
        mock_client = MagicMock()
        lf._current_trace_id.set("trace-current-4")
        content = "Tool made_up_tool not found. Available tools: code_execution_tool, response"
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.score_quality_signal(content)
        mock_client.create_score.assert_called_once_with(
            trace_id="trace-current-4", name="tool-not-found", value=0, data_type="BOOLEAN", comment=None,
        )

    def test_critical_error_score(self, lf):
        """hist_add_before content matching fw.msg_critical_error.md scores critical-error=0."""
        mock_client = MagicMock()
        lf._current_trace_id.set("trace-current-5")
        content = "This error has occurred: BadRequestError. Proceed with your original task if possible."
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.score_quality_signal(content)
        mock_client.create_score.assert_called_once_with(
            trace_id="trace-current-5", name="critical-error", value=0, data_type="BOOLEAN", comment=None,
        )

    def test_no_error_no_score(self, lf):
        """Ordinary content matching none of the 4 patterns creates no score."""
        mock_client = MagicMock()
        lf._current_trace_id.set("trace-current-6")
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.score_quality_signal("Just a normal assistant response, nothing wrong here.")
        mock_client.create_score.assert_not_called()

    def test_no_score_without_current_trace(self, lf):
        """No trace_id in context -> never calls create_score, never raises."""
        mock_client = MagicMock()
        lf._current_trace_id.set("")
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.score_framework_error("err")
            lf.score_quality_signal("did not match the required schema")
        mock_client.create_score.assert_not_called()

    def test_capture_raw_exception(self, lf):
        """capture_raw_exception scores raw-exception=0 with location + exception info in comment."""
        mock_client = MagicMock()
        lf._current_trace_id.set("trace-current-7")
        exc = ValueError("boom")
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.capture_raw_exception("message_loop", exc)
        _, kwargs = mock_client.create_score.call_args
        assert kwargs["trace_id"] == "trace-current-7"
        assert kwargs["name"] == "raw-exception"
        assert kwargs["value"] == 0
        assert kwargs["data_type"] == "BOOLEAN"
        assert "message_loop" in kwargs["comment"]
        assert "ValueError" in kwargs["comment"]
        assert "boom" in kwargs["comment"]


class TestFeatureTagging:
    """Task 4: map tool names to feature categories and tag the trace via
    _create_trace_tags_via_ingestion (VERIFIED: update_current_trace does NOT
    exist in SDK v4).
    """

    def test_feature_tag_coding(self, lf):
        """code_execution_tool maps to 'coding'."""
        mock_client = MagicMock()
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.add_feature_tags("trace-1", ["code_execution_tool"])
        mock_client._create_trace_tags_via_ingestion.assert_called_once_with(
            trace_id="trace-1", tags=["coding"]
        )

    def test_feature_tag_research(self, lf):
        """search_engine maps to 'research'."""
        mock_client = MagicMock()
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.add_feature_tags("trace-2", ["search_engine"])
        mock_client._create_trace_tags_via_ingestion.assert_called_once_with(
            trace_id="trace-2", tags=["research"]
        )

    def test_feature_tag_multi(self, lf):
        """Multiple tools map to multiple categories (deduplicated)."""
        mock_client = MagicMock()
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.add_feature_tags("trace-3", ["code_execution_tool", "text_editor", "search_engine", "call_subordinate"])
        _, kwargs = mock_client._create_trace_tags_via_ingestion.call_args
        assert kwargs["trace_id"] == "trace-3"
        assert set(kwargs["tags"]) == {"coding", "research", "delegation"}

    def test_feature_tag_conversation_default(self, lf):
        """Empty tool list maps to 'conversation'."""
        mock_client = MagicMock()
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.add_feature_tags("trace-4", [])
        mock_client._create_trace_tags_via_ingestion.assert_called_once_with(
            trace_id="trace-4", tags=["conversation"]
        )

    def test_feature_tag_no_client(self, lf):
        """Never raises when client unavailable."""
        with patch.object(lf, "get_client", return_value=None):
            lf.add_feature_tags("trace-5", ["code_execution_tool"])

    def test_feature_tag_no_ingestion_method(self, lf):
        """Graceful fallback when SDK lacks _create_trace_tags_via_ingestion."""
        mock_client = MagicMock()
        del mock_client._create_trace_tags_via_ingestion
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.add_feature_tags("trace-6", ["code_execution_tool"])


class TestUtilityModelTracking:
    """Task 5: track background utility LLM calls (chat naming, skill search,
    compression) as tagged SPAN observations.

    VERIFIED: util_model_call hooks provide call_data={model, system, message,
    callback, background} + response string. NO token usage in payload.
    Utility calls use model.unified_call(), NOT the LiteLLM transport we wrap,
    so no double-counting risk with existing GENERATION tracking.
    """

    def test_start_util_model_span(self, lf):
        """start_util_model_span creates a SPAN with input=message under current parent."""
        mock_client = MagicMock()
        mock_parent = MagicMock()
        mock_span = MagicMock()
        mock_parent.start_observation = MagicMock(return_value=mock_span)
        lf.set_parent_observation(mock_parent)
        lf._current_trace_id.set("trace-util-1")
        call_data = {"system": "Summarize", "message": "test message", "background": True}
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.start_util_model_span(call_data)
        mock_parent.start_observation.assert_called_once()
        _, kwargs = mock_parent.start_observation.call_args
        assert kwargs["name"] == "utility-model"
        assert kwargs["as_type"] == "span"
        assert "test message" in str(kwargs["input"])

    def test_end_util_model_span(self, lf):
        """end_util_model_span updates output and ends the span."""
        mock_span = MagicMock()
        lf._util_span.set(mock_span)
        call_data = {}
        response = "summary result"
        lf.end_util_model_span(call_data, response)
        mock_span.update.assert_called_once()
        _, kwargs = mock_span.update.call_args
        assert kwargs["output"] == "summary result"
        mock_span.end.assert_called_once()

    def test_util_span_no_client(self, lf):
        """start_util_model_span never raises without client."""
        lf._current_trace_id.set("")
        with patch.object(lf, "get_client", return_value=None):
            lf.start_util_model_span({"message": "x"})  # must not raise

    def test_util_span_no_parent(self, lf):
        """start_util_model_span uses client directly when no parent observation."""
        mock_client = MagicMock()
        mock_span_cm = MagicMock()
        mock_span = MagicMock()
        mock_span_cm.__enter__ = MagicMock(return_value=mock_span)
        mock_span_cm.__exit__ = MagicMock(return_value=False)
        mock_client.start_as_current_observation = MagicMock(return_value=mock_span_cm)
        lf.clear_parent_observation()
        lf._current_trace_id.set("trace-util-2")
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.start_util_model_span({"message": "hello"})
        mock_client.start_as_current_observation.assert_called_once()

    def test_util_end_no_span(self, lf):
        """end_util_model_span never raises when no span was started."""
        lf._util_span.set(None)
        lf.end_util_model_span({}, "response")  # must not raise

    def test_end_util_model_span_attaches_model_usage_and_cost_metadata(self, lf):
        """Utility spans should capture model/usage/cost metadata when an LLM result is available."""
        from helpers.llm_result import LLMResult

        mock_span = MagicMock()
        lf._util_span.set(mock_span)
        lf._utility_llm_result.set(
            LLMResult(
                provider_model_key="openai/glm-5.2",
                usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            )
        )
        call_data = {"model": SimpleNamespace(model_name="openai/glm-5.2")}

        lf.end_util_model_span(call_data, "summary result")

        _, kwargs = mock_span.update.call_args
        assert kwargs["output"] == "summary result"
        assert kwargs["metadata"]["provider_model_key"] == "openai/glm-5.2"
        assert kwargs["metadata"]["usage"]["input"] == 100
        assert kwargs["metadata"]["usage"]["output"] == 20
        assert kwargs["metadata"]["cost_details"]["total"] > 0
        mock_span.end.assert_called_once()


class TestAPIFallbackAndChain:
    """Task 6: API fallback detection + process chain completion timing.

    VERIFIED: process_chain_end hook fires on AgentContext._process_chain
    (agent.py:307) with kwargs agent + data={}.
    """

    def test_api_fallback_flag(self, lf):
        """set_api_fallback sets a flag readable by feature tag flush."""
        lf._api_fallback.set(False)
        lf.set_api_fallback()
        assert lf._api_fallback.get() is True

    def test_api_fallback_tag_added(self, lf):
        """add_feature_tags includes 'api-fallback' when flag is set."""
        mock_client = MagicMock()
        lf._api_fallback.set(True)
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.add_feature_tags("trace-fb", ["code_execution_tool"])
        _, kwargs = mock_client._create_trace_tags_via_ingestion.call_args
        assert "api-fallback" in kwargs["tags"]
        assert "coding" in kwargs["tags"]

    def test_api_fallback_cleared_after_tag(self, lf):
        """_api_fallback flag is reset to False after add_feature_tags consumes it."""
        mock_client = MagicMock()
        lf._api_fallback.set(True)
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.add_feature_tags("trace-fb2", [])
        assert lf._api_fallback.get() is False

class TestMultiModalityImages:
    """Task 9: convert image_url content blocks to LangfuseMedia objects."""

    def test_image_media_creation(self, lf):
        """_format_generation_input converts base64 data URI image_url to LangfuseMedia."""
        import sys
        mock_media_cls = MagicMock()
        mock_langfuse_mod = MagicMock()
        mock_langfuse_mod.LangfuseMedia = mock_media_cls
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": "What is in this image?"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgo="}},
            ]
        }]
        with patch.dict(sys.modules, {"langfuse.media": mock_langfuse_mod}):
            result = lf._format_generation_input(messages)
        assert isinstance(result, list)
        assert len(result) >= 1
        mock_media_cls.assert_called()
        _, kwargs = mock_media_cls.call_args
        assert "base64_data_uri" in kwargs

    def test_mixed_content_input(self, lf):
        """Mixed text and image content produces both text sections and media objects."""
        import sys
        mock_media_cls = MagicMock()
        mock_langfuse_mod = MagicMock()
        mock_langfuse_mod.LangfuseMedia = mock_media_cls
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": "Check this screenshot"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/4AAQ="}},
                {"type": "text", "text": "and tell me what you see"},
            ]
        }]
        with patch.dict(sys.modules, {"langfuse.media": mock_langfuse_mod}):
            result = lf._format_generation_input(messages)
        assert isinstance(result, list)
        assert len(result) >= 2

    def test_text_only_stays_string(self, lf):
        """Messages without image_url blocks still return string (no change)."""
        messages = [{"role": "user", "content": "Just plain text"}]
        result = lf._format_generation_input(messages)
        assert isinstance(result, str)
        assert "Just plain text" in result


class TestPromptSyncBridge:
    """Task 10: bidirectional prompt sync between A0 and Langfuse.

    UPLOAD: system_prompt hook sends assembled prompt to Langfuse.
    DOWNLOAD: message_loop_prompts_before replaces/prepends Langfuse prompt.
    """

    def test_prompt_sync_upload(self, lf):
        """upload_prompt sends assembled prompt to Langfuse via create_prompt."""
        mock_client = MagicMock()
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.upload_prompt("a0-system-prompt", ["# System\nYou are Agent Zero.", "# Tools\n..."])
        mock_client.create_prompt.assert_called_once()
        _, kwargs = mock_client.create_prompt.call_args
        assert kwargs["name"] == "a0-system-prompt"
        assert "Agent Zero" in kwargs["prompt"]
        assert kwargs["type"] == "text"

    def test_prompt_override_replace(self, lf):
        """apply_prompt_override in replace mode swaps the main system section."""
        mock_client = MagicMock()
        mock_prompt = MagicMock()
        mock_prompt.prompt = "OVERRIDE: You are a different agent now."
        mock_client.get_prompt.return_value = mock_prompt
        sections = ["# System\nOriginal system", "# Tools\nTools here"]
        with patch.object(lf, "get_client", return_value=mock_client):
            result = lf.apply_prompt_override("a0-system-prompt", sections, mode="replace")
        assert "OVERRIDE" in result[0]
        assert len(result) == len(sections)

    def test_prompt_override_prepend(self, lf):
        """apply_prompt_override in prepend mode adds the Langfuse prompt as new first section."""
        mock_client = MagicMock()
        mock_prompt = MagicMock()
        mock_prompt.prompt = "ADDITIONAL: Be extra careful with security."
        mock_client.get_prompt.return_value = mock_prompt
        sections = ["# System\nOriginal system", "# Tools\nTools here"]
        original_len = len(sections)
        with patch.object(lf, "get_client", return_value=mock_client):
            result = lf.apply_prompt_override("a0-system-prompt", sections, mode="prepend")
        assert "ADDITIONAL" in result[0]
        assert len(result) == original_len + 1

    def test_prompt_override_disabled(self, lf):
        """apply_prompt_override returns sections unchanged when not enabled."""
        with patch.object(lf, "get_client", return_value=None):
            result = lf.apply_prompt_override("a0-system-prompt", ["original"], mode="replace")
        assert result == ["original"]


class TestLLMAsAJudge:
    """Task 11: LLM-as-a-Judge evaluates response quality using glm-5.2.

    Uses litellm.acompletion() with A0's provider config. Creates quality-judge
    NUMERIC score (0.0-1.0) on current trace. Disabled by default.
    """

    def test_judge_disabled(self, lf):
        """run_judge_evaluation does nothing when disabled in config."""
        import asyncio
        mock_client = MagicMock()
        lf._current_trace_id.set("trace-judge-1")
        with patch.object(lf, "get_langfuse_config", return_value={"langfuse_judge_enabled": False}), \
             patch.object(lf, "get_client", return_value=mock_client):
            asyncio.run(lf.run_judge_evaluation("hello", "hi there"))
        mock_client.create_score.assert_not_called()

    def test_judge_score_creation(self, lf):
        """run_judge_evaluation creates quality-judge NUMERIC score when enabled."""
        import asyncio
        mock_client = MagicMock()
        lf._current_trace_id.set("trace-judge-2")
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="0.85"))]
        async def mock_acompletion(*args, **kwargs):
            return mock_response
        with patch.object(lf, "get_langfuse_config", return_value={
            "langfuse_judge_enabled": True, "langfuse_judge_sample_rate": 1.0,
            "public_key": "pk", "secret_key": "sk", "host": "http://test"
        }), patch.object(lf, "get_client", return_value=mock_client), \
             patch("litellm.acompletion", side_effect=mock_acompletion):
            asyncio.get_event_loop().run_until_complete(
                lf.run_judge_evaluation("What is Python?", "Python is a programming language.")
            )
        mock_client.create_score.assert_called_once()
        _, kwargs = mock_client.create_score.call_args
        assert kwargs["name"] == "quality-judge"
        assert kwargs["data_type"] == "NUMERIC"
        assert 0.0 <= kwargs["value"] <= 1.0

    def test_judge_sampling(self, lf):
        """run_judge_evaluation respects sample rate (0.0 = never, 1.0 = always)."""
        import asyncio
        lf._current_trace_id.set("trace-judge-3")
        with patch.object(lf, "get_langfuse_config", return_value={
            "langfuse_judge_enabled": True, "langfuse_judge_sample_rate": 0.0
        }), patch.object(lf, "get_client", return_value=MagicMock()):
            asyncio.run(lf.run_judge_evaluation("test", "test"))
        # With sample_rate=0.0, judge should never run


class TestRateAndRetryTracking:
    """Gap 2: track rate limiting and retry events as scores."""

    def test_track_rate_limit(self, lf):
        """track_rate_limit creates rate-limited=0 score on current trace."""
        mock_client = MagicMock()
        lf._current_trace_id.set("trace-rl-1")
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.track_rate_limit("glm-5.2", 150, 100)
        mock_client.create_score.assert_called_once()
        _, kwargs = mock_client.create_score.call_args
        assert kwargs["name"] == "rate-limited"
        assert kwargs["value"] == 0
        assert "150/100" in kwargs["comment"]

    def test_track_retry(self, lf):
        """track_retry creates retry-attempted NUMERIC score."""
        mock_client = MagicMock()
        lf._current_trace_id.set("trace-retry-1")
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.track_retry(2, "TimeoutError: connection timed out")
        mock_client.create_score.assert_called_once()
        _, kwargs = mock_client.create_score.call_args
        assert kwargs["name"] == "retry-attempted"
        assert kwargs["value"] == 2.0
        assert kwargs["data_type"] == "NUMERIC"

    def test_unified_call_retry_path_tracks_retry(self, lf):
        """Retry tracking should fire from the real unified_call retry path, not only direct helper calls."""
        import asyncio
        import helpers.litellm_transport as transport_mod
        import models

        class Transient503(Exception):
            status_code = 503

        calls = {"count": 0}
        saved_acomplete = transport_mod.LiteLLMTransport.acomplete

        async def fake_apply_rate_limiter(*args, **kwargs):
            return None

        async def fake_acomplete(self):
            calls["count"] += 1
            if calls["count"] == 1:
                raise Transient503("temporary outage")
            return {"response_delta": "ok", "reasoning_delta": ""}

        try:
            transport_mod.LiteLLMTransport.acomplete = fake_acomplete
            with patch("models.configure_litellm"), \
                 patch("models.apply_rate_limiter", side_effect=fake_apply_rate_limiter), \
                 patch.object(lf, "track_retry") as track_retry_mock:
                lf._current_trace_id.set("trace-retry-integration")
                lf._wrap_transport_tracking()
                model = models.LiteLLMChatWrapper(model="gpt-4", provider="openai", model_config=None)
                response, reasoning = asyncio.run(
                    model.unified_call(
                        user_message="hello",
                        a0_retry_attempts=1,
                        a0_retry_delay_seconds=0,
                    )
                )

            assert response == "ok"
            assert reasoning == ""
            track_retry_mock.assert_called_once()
            attempt, error = track_retry_mock.call_args.args
            assert attempt == 2
            assert "temporary outage" in error
        finally:
            transport_mod.LiteLLMTransport.acomplete = saved_acomplete
            lf.clear_trace_context()

    def test_rate_limit_no_trace(self, lf):
        """track_rate_limit never raises without trace."""
        lf._current_trace_id.set("")
        lf.track_rate_limit("test", 1, 1)  # must not raise


class TestFeedbackApi:
    """Feedback API should resolve server-side message mappings safely."""

    class DummyAgent:
        def __init__(self):
            self.data = {}
            self.context = SimpleNamespace(agent0=self)

        def get_data(self, key):
            return self.data.get(key)

        def set_data(self, key, value):
            self.data[key] = value

    def test_feedback_uses_message_mapping_instead_of_latest_trace(self, lf):
        """Older-message feedback should use the mapped trace, not lf_last_trace_id/lf_pending_trace_id."""
        import asyncio

        api_mod = _load_feedback_api_module()
        agent = self.DummyAgent()
        agent.set_data("lf_last_trace_id", "trace-latest")
        agent.set_data("lf_pending_trace_id", "trace-pending")
        lf.remember_feedback_target(agent, "trace-older", log_no=7, message_id="msg-7")
        context = SimpleNamespace(agent0=agent, streaming_agent=None)
        handler = api_mod.LangfuseFeedback(MagicMock(), MagicMock())
        mock_client = MagicMock()

        with patch.object(api_mod.AgentContext, "get", return_value=context), \
             patch.object(api_mod, "_lib", return_value=lf), \
             patch.object(lf, "get_client", return_value=mock_client):
            result = asyncio.run(
                handler.process(
                    {
                        "context_id": "ctx-1",
                        "score": 1,
                        "comment": "",
                        "log_no": 7,
                        "message_id": "msg-7",
                    },
                    MagicMock(),
                )
            )

        assert result["ok"] is True
        assert "trace_id" not in result
        _, kwargs = mock_client.create_score.call_args
        assert kwargs["trace_id"] == "trace-older"

    def test_feedback_invalid_mapping_fails_safely(self, lf):
        """Unknown or stale mappings should return 404 without creating feedback."""
        import asyncio

        api_mod = _load_feedback_api_module()
        agent = self.DummyAgent()
        context = SimpleNamespace(agent0=agent, streaming_agent=None)
        handler = api_mod.LangfuseFeedback(MagicMock(), MagicMock())
        mock_client = MagicMock()

        with patch.object(api_mod.AgentContext, "get", return_value=context), \
             patch.object(api_mod, "_lib", return_value=lf), \
             patch.object(lf, "get_client", return_value=mock_client):
            result = asyncio.run(
                handler.process(
                    {
                        "context_id": "ctx-1",
                        "score": 1,
                        "comment": "",
                        "log_no": 999,
                        "message_id": "missing",
                    },
                    MagicMock(),
                )
            )

        assert result.status_code == 404
        mock_client.create_score.assert_not_called()

    def test_feedback_requires_message_identity(self, lf):
        """Feedback API should reject requests that do not identify a specific assistant message."""
        import asyncio

        api_mod = _load_feedback_api_module()
        agent = self.DummyAgent()
        context = SimpleNamespace(agent0=agent, streaming_agent=None)
        handler = api_mod.LangfuseFeedback(MagicMock(), MagicMock())

        with patch.object(api_mod.AgentContext, "get", return_value=context), \
             patch.object(api_mod, "_lib", return_value=lf):
            result = asyncio.run(
                handler.process(
                    {
                        "context_id": "ctx-1",
                        "score": 1,
                        "comment": "",
                    },
                    MagicMock(),
                )
            )

        assert result.status_code == 400


class TestBuildLogMetadata:
    """Tests for _build_log_metadata() narrative tap helper."""

    def test_basic_metadata_with_all_fields(self, lf):
        """Metadata dict should contain log_type, heading, content, and kvps."""
        meta = lf._build_log_metadata(
            "agent",
            "A0: Calling LLM...",
            "Some content here",
            {"thoughts": ["step1", "step2"]},
        )
        assert meta["log_type"] == "agent"
        assert meta["heading"] == "A0: Calling LLM..."
        assert meta["content"] == "Some content here"
        assert "kvps" in meta

    def test_heading_truncated_to_max(self, lf):
        """Heading longer than MAX_LOG_HEADING_CHARS should be truncated."""
        long_heading = "x" * 500
        meta = lf._build_log_metadata("agent", long_heading, "", None)
        assert len(meta["heading"]) == lf.MAX_LOG_HEADING_CHARS

    def test_content_truncated_to_max(self, lf):
        """Content longer than MAX_LOG_CONTENT_CHARS should be truncated."""
        long_content = "y" * 1000
        meta = lf._build_log_metadata("tool", "heading", long_content, None)
        assert len(meta["content"]) == lf.MAX_LOG_CONTENT_CHARS

    def test_no_content_or_kvps_omits_keys(self, lf):
        """When content and kvps are empty/None, their keys should be absent."""
        meta = lf._build_log_metadata("info", "heading", "", None)
        assert "content" not in meta
        assert "kvps" not in meta

    def test_kvps_sanitized(self, lf):
        """kvps should be passed through _sanitize_for_capture."""
        kvps = {"api_key": "sk-secret123", "tool_name": "response"}
        meta = lf._build_log_metadata("agent", "heading", "content", kvps)
        # Sensitive key should be masked by _sanitize_for_capture
        kvps_result = meta["kvps"]
        # The sanitized dict should not contain the raw secret
        assert "sk-secret123" not in str(kvps_result)

    def test_none_heading_and_content_safe(self, lf):
        """None heading/content should not cause errors."""
        meta = lf._build_log_metadata("warning", None, None, None)
        assert meta["log_type"] == "warning"
        assert meta["heading"] == ""
        assert "content" not in meta

    def test_kvps_sanitization_failure_handled(self, lf):
        """If _sanitize_for_capture fails, kvps should show fallback string."""
        # Pass a non-serializable object that will fail sanitization
        bad_kvps = object()  # not a dict, may cause issues
        meta = lf._build_log_metadata("agent", "heading", "content", bad_kvps)
        assert "kvps" in meta  # should have some value, not crash


def _load_narrative_tap_module():
    """Load the narrative tap extension module for testing."""
    import importlib.util as _ilu
    _narrative_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "extensions", "python", "_functions",
        "helpers", "log", "Log", "log", "end", "_90_langfuse_narrative.py",
    )
    _narrative_path = os.path.normpath(_narrative_path)
    _spec = _ilu.spec_from_file_location("_test_narrative_tap", _narrative_path)
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    return _mod


class TestNarrativeTap:
    """Tests for the v3 narrative tap — exercises the actual extension class."""

    def test_kwargs_extraction_via_actual_extension(self, lf):
        """Extension execute() should extract log_type from kwargs and call start_observation."""
        lf._current_trace_id.set("test-trace-id")
        narrative_mod = _load_narrative_tap_module()
        tap_cls = narrative_mod.LangfuseNarrativeTap
        mock_obs = MagicMock()
        mock_client = MagicMock()
        mock_client.start_observation.return_value = mock_obs
        data = {"args": (MagicMock(),), "kwargs": {"type": "error", "heading": "A0: Error occurred", "content": "Error text", "kvps": {"thoughts": ["think1"]}}, "result": MagicMock(), "exception": None}
        with patch.object(narrative_mod, "_lib", return_value=lf), patch.object(lf, "get_client", return_value=mock_client):
            tap_cls(agent=None).execute(data=data)
        mock_client.start_observation.assert_called_once()
        call_kwargs = mock_client.start_observation.call_args.kwargs
        assert call_kwargs["name"] == "log-error"
        assert call_kwargs["as_type"] == "event"
        meta = call_kwargs["metadata"]
        assert meta["log_type"] == "error"
        mock_obs.end.assert_called_once()

    def test_args_fallback_via_actual_extension(self, lf):
        """Extension execute() should fall back to positional args when kwargs has no type."""
        lf._current_trace_id.set("test-trace-id")
        narrative_mod = _load_narrative_tap_module()
        tap_cls = narrative_mod.LangfuseNarrativeTap
        mock_client = MagicMock()
        mock_client.start_observation.return_value = MagicMock()
        data = {"args": (MagicMock(), "warning", "Warning heading", "content", {"key": "val"}), "kwargs": {}, "result": MagicMock(), "exception": None}
        with patch.object(narrative_mod, "_lib", return_value=lf), patch.object(lf, "get_client", return_value=mock_client):
            tap_cls(agent=None).execute(data=data)
        call_kwargs = mock_client.start_observation.call_args.kwargs
        assert call_kwargs["name"] == "log-warning"

    def test_no_trace_id_skips_silently(self, lf):
        """Extension should not create observations when no trace_id is set."""
        lf._current_trace_id.set("")
        narrative_mod = _load_narrative_tap_module()
        tap_cls = narrative_mod.LangfuseNarrativeTap
        mock_client = MagicMock()
        with patch.object(narrative_mod, "_lib", return_value=lf), patch.object(lf, "get_client", return_value=mock_client):
            tap_cls(agent=None).execute(data={"args": (), "kwargs": {"type": "error"}})
        mock_client.start_observation.assert_not_called()

    def test_error_isolation_exception_does_not_propagate(self, lf):
        """Exceptions inside the narrative tap must be swallowed — execute must survive."""
        lf._current_trace_id.set("test-trace-id")
        narrative_mod = _load_narrative_tap_module()
        tap_cls = narrative_mod.LangfuseNarrativeTap
        mock_client = MagicMock()
        mock_client.start_observation.side_effect = RuntimeError("Simulated SDK crash")
        data = {"args": (MagicMock(),), "kwargs": {"type": "error", "heading": "test"}, "result": MagicMock(), "exception": None}
        with patch.object(narrative_mod, "_lib", return_value=lf), patch.object(lf, "get_client", return_value=mock_client):
            tap_cls(agent=None).execute(data=data)
        mock_client.start_observation.assert_called_once()

    def test_full_flow_via_actual_extension(self, lf):
        """Full flow: kwargs payload -> actual extension -> _build_log_metadata -> start_observation."""
        lf._current_trace_id.set("test-trace-id")
        narrative_mod = _load_narrative_tap_module()
        tap_cls = narrative_mod.LangfuseNarrativeTap
        mock_obs = MagicMock()
        mock_client = MagicMock()
        mock_client.start_observation.return_value = mock_obs
        data = {"args": (MagicMock(),), "kwargs": {"type": "warning", "heading": "Warning: high token usage", "content": "Token count exceeded threshold", "kvps": {"threshold": "100000", "current": "150000"}}}
        with patch.object(narrative_mod, "_lib", return_value=lf), patch.object(lf, "get_client", return_value=mock_client):
            tap_cls(agent=None).execute(data=data)
        call_kwargs = mock_client.start_observation.call_args.kwargs
        assert call_kwargs["name"] == "log-warning"
        meta = call_kwargs["metadata"]
        assert meta["log_type"] == "warning"
        assert "threshold" in str(meta.get("kvps", meta))
        assert "kvps" in meta
        mock_obs.end.assert_called_once()

class TestRetryCounterAccuracy:
    """Retry counter must not accumulate across calls on the same transport instance."""

    def test_retry_counter_resets_on_success_acomplete(self, lf):
        """After a successful acomplete call, _lf_retry_call_index must reset to 0."""
        import asyncio
        import types as _types

        class FakeTransport:
            pass

        async def fake_acomplete(self, *args, **kwargs):
            return {"response_delta": "ok"}

        FakeTransport.acomplete = fake_acomplete

        fake_mod = _types.ModuleType("helpers.litellm_transport")
        fake_mod.LiteLLMTransport = FakeTransport

        with patch.dict("sys.modules", {"helpers.litellm_transport": fake_mod}):
            lf._original_transport_acomplete = None
            lf._wrap_transport_tracking()

            fake = FakeTransport()
            fake._lf_retry_call_index = 5
            asyncio.run(fake.acomplete())

        assert getattr(fake, "_lf_retry_call_index", -1) == 0, \
            "Counter should reset to 0 after successful call"

    def test_retry_counter_correct_after_prior_calls(self, lf):
        """After a prior successful call, a retry must report attempt=2, not N+2."""
        import asyncio
        import types as _types

        class Transient503(Exception):
            status_code = 503

        class FakeTransport:
            def __init__(self):
                self._lf_retry_call_index = 0

        state = {"phase": "success_first"}

        async def fake_acomplete(self, *args, **kwargs):
            if state["phase"] == "success_first":
                return {"response_delta": "ok"}
            raise Transient503("temporary outage")

        FakeTransport.acomplete = fake_acomplete

        fake_mod = _types.ModuleType("helpers.litellm_transport")
        fake_mod.LiteLLMTransport = FakeTransport

        lf._current_trace_id.set("trace-accuracy")

        with patch.dict("sys.modules", {"helpers.litellm_transport": fake_mod}):
            lf._original_transport_acomplete = None
            lf._wrap_transport_tracking()

            fake = FakeTransport()

            # First call succeeds — counter should reset to 0
            asyncio.run(fake.acomplete())
            assert fake._lf_retry_call_index == 0, \
                f"Counter should be 0 after successful call, got {fake._lf_retry_call_index}"

            # Second call fails — must report attempt=2 (not accumulated value)
            state["phase"] = "fail"
            with patch.object(lf, "track_retry") as track_retry_mock:
                try:
                    asyncio.run(fake.acomplete())
                except Transient503:
                    pass

        track_retry_mock.assert_called_once()
        attempt, _ = track_retry_mock.call_args.args
        assert attempt == 2, f"Expected attempt=2 after reset, got {attempt}"

    def test_retry_counter_resets_on_success_astream(self, lf):
        """After a successful astream call, _lf_retry_call_index must reset to 0."""
        import asyncio
        import types as _types

        class FakeTransport:
            pass

        async def fake_astream(self, *args, **kwargs):
            yield {"response_delta": "ok"}

        FakeTransport.astream = fake_astream

        fake_mod = _types.ModuleType("helpers.litellm_transport")
        fake_mod.LiteLLMTransport = FakeTransport

        with patch.dict("sys.modules", {"helpers.litellm_transport": fake_mod}):
            lf._original_transport_astream = None
            lf._wrap_transport_tracking()

            fake = FakeTransport()
            fake._lf_retry_call_index = 7

            async def run_stream():
                async for chunk in fake.astream():
                    pass
            asyncio.run(run_stream())

        assert getattr(fake, "_lf_retry_call_index", -1) == 0, \
            "Counter should reset to 0 after successful stream"


class TestFeedbackApiValidation:
    """Feedback API validation paths and edge cases."""

    class DummyAgent:
        def __init__(self):
            self.data = {}
            self.context = SimpleNamespace(agent0=self)

        def get_data(self, key):
            return self.data.get(key)

        def set_data(self, key, value):
            self.data[key] = value

    def test_feedback_rejects_missing_context_id(self, lf):
        """Feedback API must reject requests without context_id."""
        import asyncio

        api_mod = _load_feedback_api_module()
        handler = api_mod.LangfuseFeedback(MagicMock(), MagicMock())

        with patch.object(api_mod, "_lib", return_value=lf):
            result = asyncio.run(
                handler.process(
                    {"score": 1, "comment": "", "log_no": 1, "message_id": "msg-1"},
                    MagicMock(),
                )
            )

        assert result.status_code == 400

    def test_feedback_rejects_invalid_score(self, lf):
        """Feedback API must reject scores that are not 0 or 1."""
        import asyncio

        api_mod = _load_feedback_api_module()
        handler = api_mod.LangfuseFeedback(MagicMock(), MagicMock())

        with patch.object(api_mod, "_lib", return_value=lf):
            result = asyncio.run(
                handler.process(
                    {"context_id": "ctx-1", "score": 5, "comment": "", "log_no": 1, "message_id": "msg-1"},
                    MagicMock(),
                )
            )

        assert result.status_code == 400

    def test_feedback_returns_503_without_client(self, lf):
        """Feedback API should return 503 when Langfuse client is not initialized."""
        import asyncio

        api_mod = _load_feedback_api_module()
        agent = self.DummyAgent()
        lf.remember_feedback_target(agent, "trace-test", log_no=1, message_id="msg-1")
        context = SimpleNamespace(agent0=agent, streaming_agent=None)
        handler = api_mod.LangfuseFeedback(MagicMock(), MagicMock())

        with patch.object(api_mod.AgentContext, "get", return_value=context), \
             patch.object(api_mod, "_lib", return_value=lf), \
             patch.object(lf, "get_client", return_value=None):
            result = asyncio.run(
                handler.process(
                    {"context_id": "ctx-1", "score": 1, "comment": "", "log_no": 1, "message_id": "msg-1"},
                    MagicMock(),
                )
            )

        assert result.status_code == 503

    def test_feedback_returns_404_for_unknown_context(self, lf):
        """Feedback API should return 404 for a context_id that does not exist."""
        import asyncio

        api_mod = _load_feedback_api_module()
        handler = api_mod.LangfuseFeedback(MagicMock(), MagicMock())

        with patch.object(api_mod.AgentContext, "get", return_value=None), \
             patch.object(api_mod, "_lib", return_value=lf):
            result = asyncio.run(
                handler.process(
                    {"context_id": "nonexistent-ctx", "score": 1, "comment": "", "log_no": 1, "message_id": "msg-1"},
                    MagicMock(),
                )
            )

        assert result.status_code == 404

    def test_feedback_returns_404_for_unknown_agent(self, lf):
        """Feedback API should return 404 when context has no agent."""
        import asyncio

        api_mod = _load_feedback_api_module()
        context = SimpleNamespace(agent0=None, streaming_agent=None)
        handler = api_mod.LangfuseFeedback(MagicMock(), MagicMock())

        with patch.object(api_mod.AgentContext, "get", return_value=context), \
             patch.object(api_mod, "_lib", return_value=lf):
            result = asyncio.run(
                handler.process(
                    {"context_id": "ctx-1", "score": 1, "comment": "", "log_no": 1, "message_id": "msg-1"},
                    MagicMock(),
                )
            )

        assert result.status_code == 404

    def test_feedback_rejects_cross_context_injection(self, lf):
        """Whitespace-only context_id must be rejected as basic injection defense."""
        import asyncio

        api_mod = _load_feedback_api_module()
        handler = api_mod.LangfuseFeedback(MagicMock(), MagicMock())

        with patch.object(api_mod, "_lib", return_value=lf):
            result = asyncio.run(
                handler.process(
                    {"context_id": "   ", "score": 1, "comment": "", "log_no": 1, "message_id": "msg-1"},
                    MagicMock(),
                )
            )

        assert result.status_code == 400


# ---------------------------------------------------------------------------
# v3 Tracing Model Tests
# ---------------------------------------------------------------------------

def _load_iteration_start_module():
    """Load the message_loop_start iteration extension module for testing."""
    import importlib.util as _ilu
    _path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "extensions", "python", "message_loop_start", "_90_langfuse_iteration.py",
    )
    _path = os.path.normpath(_path)
    _spec = _ilu.spec_from_file_location("_test_iteration_start", _path)
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    return _mod


def _load_iteration_end_module():
    """Load the message_loop_end iteration end extension module for testing."""
    import importlib.util as _ilu
    _path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "extensions", "python", "message_loop_end", "_90_langfuse_iteration_end.py",
    )
    _path = os.path.normpath(_path)
    _spec = _ilu.spec_from_file_location("_test_iteration_end", _path)
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    return _mod


def _load_tool_start_module():
    """Load the tool_execute_before extension module for testing."""
    import importlib.util as _ilu
    _path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "extensions", "python", "tool_execute_before", "_90_langfuse_tool.py",
    )
    _path = os.path.normpath(_path)
    _spec = _ilu.spec_from_file_location("_test_tool_start", _path)
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    return _mod


def _load_tool_end_module():
    """Load the tool_execute_after extension module for testing."""
    import importlib.util as _ilu
    _path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "extensions", "python", "tool_execute_after", "_90_langfuse_tool_end.py",
    )
    _path = os.path.normpath(_path)
    _spec = _ilu.spec_from_file_location("_test_tool_end", _path)
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    return _mod


class TestIterationSpan:
    """Tests for v3 iteration AGENT observations (Task 3.1)."""

    def test_iteration_span_id_contextvar_set_and_get(self, lf):
        """set_iteration_span_id / get_iteration_span_id round-trip."""
        lf.set_iteration_span_id("iter-span-123")
        assert lf.get_iteration_span_id() == "iter-span-123"

    def test_iteration_span_id_default_empty(self, lf):
        """get_iteration_span_id returns empty string by default."""
        assert lf.get_iteration_span_id() == ""

    def test_clear_iteration_span_id(self, lf):
        """clear_iteration_span_id resets to empty."""
        lf.set_iteration_span_id("iter-span-456")
        lf.clear_iteration_span_id()
        assert lf.get_iteration_span_id() == ""

    def test_clear_trace_context_also_clears_iteration_span_id(self, lf):
        """clear_trace_context must clear iteration span_id along with other contextvars."""
        lf.set_trace_context("trace-1", "session-1")
        lf.set_iteration_span_id("iter-span-789")
        lf.clear_trace_context()
        assert lf.get_iteration_span_id() == ""
        assert lf._current_trace_id.get() == ""

    def test_iteration_span_id_context_isolation(self, lf):
        """Iteration span_id must isolate across copy_context boundaries."""
        import contextvars
        lf.set_iteration_span_id("parent-iter")
        ctx = contextvars.copy_context()

        def child():
            lf.set_iteration_span_id("child-iter")
            return lf.get_iteration_span_id()

        child_result = ctx.run(child)
        assert child_result == "child-iter"
        assert lf.get_iteration_span_id() == "parent-iter"

    def test_iteration_start_creates_agent_observation(self, lf):
        """message_loop_start extension creates AGENT observation nested under parent."""
        import asyncio
        lf._current_trace_id.set("trace-iter-1")
        mock_parent = MagicMock()
        mock_obs = MagicMock()
        mock_obs.id = "span-id-123"
        mock_parent.start_observation = MagicMock(return_value=mock_obs)
        lf.set_parent_observation(mock_parent)

        iter_mod = _load_iteration_start_module()
        loop_data = SimpleNamespace(
            iteration=0,
            params_persistent={"lf_sampled": True},
            params_temporary={},
        )
        with patch.object(iter_mod, "_lib", return_value=lf):
            ext_cls = iter_mod.LangfuseIterationStart
            ext_obj = ext_cls.__new__(ext_cls)
            ext_obj.agent = None
            asyncio.run(ext_obj.execute(loop_data=loop_data))

        mock_parent.start_observation.assert_called_once()
        _, kwargs = mock_parent.start_observation.call_args
        assert kwargs["as_type"] == "agent"
        assert "iteration-0" in kwargs["name"]
        assert loop_data.params_temporary["lf_iteration_obs"] is mock_obs

    def test_iteration_start_skips_when_not_sampled(self, lf):
        """Extension should skip when lf_sampled is False in params_persistent."""
        import asyncio
        mock_parent = MagicMock()
        lf.set_parent_observation(mock_parent)

        iter_mod = _load_iteration_start_module()
        loop_data = SimpleNamespace(
            iteration=0,
            params_persistent={"lf_sampled": False},
            params_temporary={},
        )
        with patch.object(iter_mod, "_lib", return_value=lf):
            ext_cls = iter_mod.LangfuseIterationStart
            ext_obj = ext_cls.__new__(ext_cls)
            ext_obj.agent = None
            asyncio.run(ext_obj.execute(loop_data=loop_data))

        mock_parent.start_observation.assert_not_called()

    def test_iteration_start_skips_when_no_parent(self, lf):
        """Extension should skip when no parent observation is set."""
        import asyncio
        lf._current_trace_id.set("trace-iter-2")
        lf.clear_parent_observation()

        iter_mod = _load_iteration_start_module()
        loop_data = SimpleNamespace(
            iteration=1,
            params_persistent={"lf_sampled": True},
            params_temporary={},
        )
        with patch.object(iter_mod, "_lib", return_value=lf):
            ext_cls = iter_mod.LangfuseIterationStart
            ext_obj = ext_cls.__new__(ext_cls)
            ext_obj.agent = None
            asyncio.run(ext_obj.execute(loop_data=loop_data))

        assert lf.get_iteration_span_id() == ""

    def test_iteration_end_ends_observation(self, lf):
        """message_loop_end extension ends the iteration observation."""
        import asyncio
        mock_obs = MagicMock()
        iter_mod = _load_iteration_end_module()
        loop_data = SimpleNamespace(
            iteration=0,
            params_persistent={"lf_sampled": True},
            params_temporary={"lf_iteration_obs": mock_obs},
        )
        lf.set_iteration_span_id("iter-span-end")
        with patch.object(iter_mod, "_lib", return_value=lf):
            ext_cls = iter_mod.LangfuseIterationEnd
            ext_obj = ext_cls.__new__(ext_cls)
            ext_obj.agent = None
            asyncio.run(ext_obj.execute(loop_data=loop_data))

        mock_obs.update.assert_called_once()
        mock_obs.end.assert_called_once()

    def test_iteration_end_no_obs_is_safe(self, lf):
        """message_loop_end must not raise when no iteration observation exists."""
        import asyncio
        iter_mod = _load_iteration_end_module()
        loop_data = SimpleNamespace(
            iteration=0,
            params_persistent={"lf_sampled": True},
            params_temporary={},
        )
        with patch.object(iter_mod, "_lib", return_value=lf):
            ext_cls = iter_mod.LangfuseIterationEnd
            ext_obj = ext_cls.__new__(ext_cls)
            ext_obj.agent = None
            asyncio.run(ext_obj.execute(loop_data=loop_data))  # must not raise


class TestToolSpan:
    """Tests for v3 TOOL observations (Task 3.2)."""

    def test_tool_start_creates_span_with_input(self, lf):
        """tool_execute_before creates SPAN observation with filtered tool args as input."""
        import asyncio
        lf._current_trace_id.set("trace-tool-1")
        mock_parent = MagicMock()
        mock_obs = MagicMock()
        mock_parent.start_observation = MagicMock(return_value=mock_obs)
        lf.set_parent_observation(mock_parent)

        tool_mod = _load_tool_start_module()
        mock_agent = MagicMock()
        mock_agent.loop_data = SimpleNamespace(params_temporary={})

        with patch.object(tool_mod, "_lib", return_value=lf):
            ext_cls = tool_mod.LangfuseToolStart
            ext_obj = ext_cls.__new__(ext_cls)
            ext_obj.agent = mock_agent
            asyncio.run(ext_obj.execute(
                tool_args={"path": "/some/path", "content": "hello"},
                tool_name="text_editor",
            ))

        mock_parent.start_observation.assert_called_once()
        _, kwargs = mock_parent.start_observation.call_args
        assert kwargs["as_type"] == "tool"
        assert "tool-text_editor" in kwargs["name"]
        assert "path" in str(kwargs["input"])
        assert "content" in str(kwargs["input"])

    def test_tool_start_nests_under_iteration_obs(self, lf):
        """Tool observation should nest under iteration AGENT when available."""
        import asyncio
        lf._current_trace_id.set("trace-tool-2")
        mock_iter_obs = MagicMock()
        mock_tool_obs = MagicMock()
        mock_iter_obs.start_observation = MagicMock(return_value=mock_tool_obs)
        lf.set_parent_observation(mock_iter_obs)

        tool_mod = _load_tool_start_module()
        mock_agent = MagicMock()
        mock_agent.loop_data = SimpleNamespace(
            params_temporary={"lf_iteration_obs": mock_iter_obs}
        )

        with patch.object(tool_mod, "_lib", return_value=lf):
            ext_cls = tool_mod.LangfuseToolStart
            ext_obj = ext_cls.__new__(ext_cls)
            ext_obj.agent = mock_agent
            asyncio.run(ext_obj.execute(
                tool_args={"query": "test"},
                tool_name="search_engine",
            ))

        mock_iter_obs.start_observation.assert_called_once()

    def test_tool_end_updates_output_and_ends(self, lf):
        """tool_execute_after updates output and ends the observation."""
        import asyncio
        mock_obs = MagicMock()
        tool_mod = _load_tool_end_module()
        mock_agent = MagicMock()
        mock_agent.loop_data = SimpleNamespace(
            params_temporary={"lf_tool_obs_list_code_execution_tool": [mock_obs]}
        )

        mock_response = SimpleNamespace(message="Execution completed")

        with patch.object(tool_mod, "_lib", return_value=lf):
            ext_cls = tool_mod.LangfuseToolEnd
            ext_obj = ext_cls.__new__(ext_cls)
            ext_obj.agent = mock_agent
            asyncio.run(ext_obj.execute(
                response=mock_response,
                tool_name="code_execution_tool",
            ))

        mock_obs.update.assert_called_once()
        _, kwargs = mock_obs.update.call_args
        assert kwargs["output"] == "Execution completed"
        mock_obs.end.assert_called_once()

    def test_tool_end_no_obs_is_safe(self, lf):
        """tool_execute_after must not raise when no tool observation exists."""
        import asyncio
        tool_mod = _load_tool_end_module()
        mock_agent = MagicMock()
        mock_agent.loop_data = SimpleNamespace(params_temporary={})

        with patch.object(tool_mod, "_lib", return_value=lf):
            ext_cls = tool_mod.LangfuseToolEnd
            ext_obj = ext_cls.__new__(ext_cls)
            ext_obj.agent = mock_agent
            asyncio.run(ext_obj.execute(
                response=SimpleNamespace(message=""),
                tool_name="nonexistent",
            ))  # must not raise

    def test_tool_start_truncates_large_args(self, lf):
        """Tool args exceeding MAX_TOOL_ARG_CHARS should be truncated."""
        import asyncio
        lf._current_trace_id.set("trace-tool-3")
        mock_parent = MagicMock()
        mock_obs = MagicMock()
        mock_parent.start_observation = MagicMock(return_value=mock_obs)
        lf.set_parent_observation(mock_parent)

        tool_mod = _load_tool_start_module()
        mock_agent = MagicMock()
        mock_agent.loop_data = SimpleNamespace(params_temporary={})

        large_code = "x" * 5000

        with patch.object(tool_mod, "_lib", return_value=lf):
            ext_cls = tool_mod.LangfuseToolStart
            ext_obj = ext_cls.__new__(ext_cls)
            ext_obj.agent = mock_agent
            asyncio.run(ext_obj.execute(
                tool_args={"code": large_code},
                tool_name="code_execution_tool",
            ))

        _, kwargs = mock_parent.start_observation.call_args
        input_val = kwargs["input"]
        code_val = input_val["code"] if isinstance(input_val, dict) else str(input_val)
        assert len(str(code_val)) < 5000  # truncated by _filter_sensitive_args


class TestGenerationNesting:
    """Tests for v3 GENERATION nesting via parent_span_id (Task 3.3)."""

    def _get_logger(self, lf):
        """Register callbacks to instantiate the LangfuseGenerationLogger."""
        import litellm
        litellm.success_callback.clear()
        litellm.failure_callback.clear()
        litellm._async_success_callback.clear()
        litellm._async_failure_callback.clear()
        lf._callbacks_registered = False
        lf._generation_logger = None
        lf._original_acompletion = None
        lf._original_completion = None
        lf._original_aresponses = None
        lf._original_responses = None
        lf._register_callbacks()
        return lf._generation_logger

    def test_generation_includes_parent_span_id_when_set(self, lf):
        """Callback logger adds parent_span_id to trace_context when iteration span_id is set."""
        mock_client = MagicMock()
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.set_trace_context("trace-gen-1", "session-1")
            lf.set_iteration_span_id("iter-span-gen-1")
            logger_obj = self._get_logger(lf)
            kwargs = {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]}
            response_obj = {"choices": [{"message": {"content": "ok"}}]}
            logger_obj._create_generation(kwargs, response_obj, None, None, error=False)
        mock_client.start_as_current_observation.assert_called_once()
        call_kwargs = mock_client.start_as_current_observation.call_args.kwargs
        assert call_kwargs["trace_context"]["parent_span_id"] == "iter-span-gen-1"
        assert call_kwargs["trace_context"]["trace_id"] == "trace-gen-1"

    def test_generation_falls_back_to_parent_obs_when_no_span_id(self, lf):
        """Without iteration span_id, callback logger nests under parent observation."""
        mock_client = MagicMock()
        mock_parent = MagicMock()
        lf.set_parent_observation(mock_parent)
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.set_trace_context("trace-gen-2", "session-2")
            lf.set_iteration_span_id("")
            logger_obj = self._get_logger(lf)
            kwargs = {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]}
            response_obj = {"choices": [{"message": {"content": "ok"}}]}
            logger_obj._create_generation(kwargs, response_obj, None, None, error=False)
        mock_parent.start_as_current_observation.assert_called_once()

    def test_generation_falls_back_to_trace_context_when_no_parent(self, lf):
        """Without iteration span_id or parent obs, use bare trace_context."""
        mock_client = MagicMock()
        lf.clear_parent_observation()
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.set_trace_context("trace-gen-3", "session-3")
            lf.set_iteration_span_id("")
            logger_obj = self._get_logger(lf)
            kwargs = {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]}
            response_obj = {"choices": [{"message": {"content": "ok"}}]}
            logger_obj._create_generation(kwargs, response_obj, None, None, error=False)
        mock_client.start_as_current_observation.assert_called_once()
        call_kwargs = mock_client.start_as_current_observation.call_args.kwargs
        assert "parent_span_id" not in call_kwargs.get("trace_context", {})
        assert call_kwargs["trace_context"]["trace_id"] == "trace-gen-3"

    def test_generation_parent_span_id_overrides_parent_obs(self, lf):
        """Iteration span_id takes precedence over parent_obs for nesting."""
        mock_client = MagicMock()
        mock_parent = MagicMock()
        lf.set_parent_observation(mock_parent)
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.set_trace_context("trace-gen-4", "session-4")
            lf.set_iteration_span_id("iter-span-gen-4")
            logger_obj = self._get_logger(lf)
            kwargs = {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]}
            response_obj = {"choices": [{"message": {"content": "ok"}}]}
            logger_obj._create_generation(kwargs, response_obj, None, None, error=False)
        # Should use client.start_as_current_observation (not parent_obs)
        mock_client.start_as_current_observation.assert_called_once()
        mock_parent.start_as_current_observation.assert_not_called()

    def test_streaming_wrapper_includes_parent_span_id(self, lf):
        """Streaming wrapper also adds parent_span_id when iteration span_id is set."""
        mock_client = MagicMock()
        mock_cm = MagicMock()
        mock_obs = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_obs)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mock_client.start_as_current_observation = MagicMock(return_value=mock_cm)
        lf.set_trace_context("trace-stream-1", "session-stream")
        lf.set_iteration_span_id("iter-span-stream")
        lf.clear_parent_observation()

        async def mock_aiter():
            yield {"choices": [{"delta": {"content": "hi"}}]}

        with patch.object(lf, "get_client", return_value=mock_client):
            wrapper = lf._StreamingGenerationWrapper(
                iterator=mock_aiter(),
                kwargs={"messages": [{"role": "user", "content": "hi"}], "model": "gpt-4"},
                trace_id="trace-stream-1",
                is_async=True,
            )

        mock_client.start_as_current_observation.assert_called_once()
        call_kwargs = mock_client.start_as_current_observation.call_args.kwargs
        assert call_kwargs["trace_context"]["parent_span_id"] == "iter-span-stream"
