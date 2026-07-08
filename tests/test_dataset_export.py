"""Tests for dataset export functionality (export_dataset_item + hook)."""

import asyncio
import importlib.util
import json
import os
from unittest.mock import MagicMock, patch

import pytest

PLUGIN_BASE = os.path.join(
    os.path.dirname(__file__), "..", "extensions", "python", "lib"
)


def _load_client_module():
    path = os.path.join(PLUGIN_BASE, "langfuse_client.py")
    spec = importlib.util.spec_from_file_location("test_dataset_client", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_dataset_hook_module():
    """Load the _30_langfuse_dataset extension module for testing."""
    hook_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "extensions", "python", "monologue_end", "_30_langfuse_dataset.py",
    )
    hook_path = os.path.normpath(hook_path)
    spec = importlib.util.spec_from_file_location("_test_dataset_hook", hook_path)
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
    return mod


class TestExportDatasetItem:
    """export_dataset_item creates dataset items via the SDK."""

    def test_export_calls_create_dataset_item(self, lf):
        """export_dataset_item calls client.create_dataset_item with correct args."""
        mock_client = MagicMock()
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.export_dataset_item(
                dataset_name="a0-traces",
                input_data={"role": "user", "content": "hello"},
                expected_output="hi there",
                trace_id="trace-ds-1",
                metadata={"session": "sess-1"},
            )
        mock_client.create_dataset_item.assert_called_once()
        _, kwargs = mock_client.create_dataset_item.call_args
        assert kwargs["dataset_name"] == "a0-traces"
        assert kwargs["input"] == {"role": "user", "content": "hello"}
        assert kwargs["expected_output"] == "hi there"
        assert kwargs["source_trace_id"] == "trace-ds-1"
        assert kwargs["metadata"] == {"session": "sess-1"}

    def test_export_no_client(self, lf):
        """export_dataset_item does nothing when no client available."""
        with patch.object(lf, "get_client", return_value=None):
            lf.export_dataset_item("ds", {"role": "user", "content": "x"}, "y", "t1")
        # No exception raised

    def test_export_empty_dataset_name(self, lf):
        """export_dataset_item skips when dataset_name is empty."""
        mock_client = MagicMock()
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.export_dataset_item("", {"role": "user", "content": "x"}, "y", "t1")
        mock_client.create_dataset_item.assert_not_called()

    def test_export_empty_trace_id(self, lf):
        """export_dataset_item skips when trace_id is empty."""
        mock_client = MagicMock()
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.export_dataset_item("ds", {"role": "user", "content": "x"}, "y", "")
        mock_client.create_dataset_item.assert_not_called()

    def test_export_no_metadata_defaults_to_empty(self, lf):
        """export_dataset_item uses empty dict when metadata is None."""
        mock_client = MagicMock()
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.export_dataset_item(
                dataset_name="ds",
                input_data={"role": "user", "content": "x"},
                expected_output="y",
                trace_id="t1",
            )
        _, kwargs = mock_client.create_dataset_item.call_args
        assert kwargs["metadata"] == {}

    def test_export_swallows_exceptions(self, lf):
        """export_dataset_item never raises even if SDK throws."""
        mock_client = MagicMock()
        mock_client.create_dataset_item.side_effect = RuntimeError("API down")
        with patch.object(lf, "get_client", return_value=mock_client):
            lf.export_dataset_item("ds", {"role": "user", "content": "x"}, "y", "t1")
        # No exception raised


class TestDatasetExportHook:
    """The _30_langfuse_dataset monologue_end hook logic."""

    def _make_loop_data(self, **kwargs):
        """Create a minimal mock for LoopData."""
        ld = MagicMock()
        ld.params_persistent = kwargs.get(
            "params_persistent",
            {"lf_sampled": True, "lf_trace_id": "trace-hook-1", "lf_session_id": "sess-1"},
        )
        ld.last_response = kwargs.get("last_response")
        ld.user_message = kwargs.get("user_message")
        return ld

    def test_hook_skips_when_not_sampled(self, lf):
        """Hook does nothing when lf_sampled is False."""
        dataset_mod = _load_dataset_hook_module()
        ld = self._make_loop_data(params_persistent={"lf_sampled": False})
        ext = dataset_mod.LangfuseDatasetExport(agent=None)

        mock_lf = MagicMock()
        with patch.object(dataset_mod, "_lib", return_value=mock_lf):
            asyncio.run(ext.execute(loop_data=ld))
        mock_lf.export_dataset_item.assert_not_called()

    def test_hook_skips_when_disabled(self, lf):
        """Hook does nothing when dataset export is disabled in config."""
        dataset_mod = _load_dataset_hook_module()
        ld = self._make_loop_data(
            last_response=json.dumps({"tool_name": "response", "tool_args": {"text": "answer"}}),
            user_message=MagicMock(content="hello"),
        )
        ext = dataset_mod.LangfuseDatasetExport(agent=None)

        mock_lf = MagicMock()
        mock_lf.get_langfuse_config.return_value = {"langfuse_dataset_export_enabled": False}
        with patch.object(dataset_mod, "_lib", return_value=mock_lf):
            asyncio.run(ext.execute(loop_data=ld))
        mock_lf.export_dataset_item.assert_not_called()

    def test_hook_skips_non_response_output(self, lf):
        """Hook skips when last_response is not a 'response' tool call."""
        dataset_mod = _load_dataset_hook_module()
        ld = self._make_loop_data(
            last_response=json.dumps({"tool_name": "code_execution_tool", "tool_args": {}}),
            user_message=MagicMock(content="hello"),
        )
        ext = dataset_mod.LangfuseDatasetExport(agent=None)

        mock_lf = MagicMock()
        mock_lf.get_langfuse_config.return_value = {"langfuse_dataset_export_enabled": True}
        with patch.object(dataset_mod, "_lib", return_value=mock_lf):
            asyncio.run(ext.execute(loop_data=ld))
        mock_lf.export_dataset_item.assert_not_called()

    def test_hook_skips_empty_response(self, lf):
        """Hook skips when last_response is empty/None."""
        dataset_mod = _load_dataset_hook_module()
        ld = self._make_loop_data(last_response=None, user_message=MagicMock(content="hello"))
        ext = dataset_mod.LangfuseDatasetExport(agent=None)

        mock_lf = MagicMock()
        mock_lf.get_langfuse_config.return_value = {"langfuse_dataset_export_enabled": True}
        with patch.object(dataset_mod, "_lib", return_value=mock_lf):
            asyncio.run(ext.execute(loop_data=ld))
        mock_lf.export_dataset_item.assert_not_called()

    def test_hook_exports_on_normal_completion(self, lf):
        """Hook calls export_dataset_item on a normal response completion."""
        dataset_mod = _load_dataset_hook_module()
        ld = self._make_loop_data(
            last_response=json.dumps({
                "tool_name": "response",
                "tool_args": {"text": "This is the answer."},
            }),
            user_message=MagicMock(content="What is Python?"),
        )
        ext = dataset_mod.LangfuseDatasetExport(agent=None)

        mock_lf = MagicMock()
        mock_lf.get_langfuse_config.return_value = {
            "langfuse_dataset_export_enabled": True,
            "langfuse_dataset_name": "my-dataset",
        }
        with patch.object(dataset_mod, "_lib", return_value=mock_lf):
            asyncio.run(ext.execute(loop_data=ld))

        mock_lf.export_dataset_item.assert_called_once()
        _, kwargs = mock_lf.export_dataset_item.call_args
        assert kwargs["dataset_name"] == "my-dataset"
        assert kwargs["input_data"] == {"role": "user", "content": "What is Python?"}
        assert kwargs["expected_output"] == "This is the answer."
        assert kwargs["trace_id"] == "trace-hook-1"
        assert kwargs["metadata"] == {"session": "sess-1"}

    def test_hook_skips_empty_user_message(self, lf):
        """Hook skips when user_message is empty."""
        dataset_mod = _load_dataset_hook_module()
        ld = self._make_loop_data(
            last_response=json.dumps({
                "tool_name": "response",
                "tool_args": {"text": "answer"},
            }),
            user_message=MagicMock(content=""),
        )
        ext = dataset_mod.LangfuseDatasetExport(agent=None)

        mock_lf = MagicMock()
        mock_lf.get_langfuse_config.return_value = {"langfuse_dataset_export_enabled": True}
        with patch.object(dataset_mod, "_lib", return_value=mock_lf):
            asyncio.run(ext.execute(loop_data=ld))
        mock_lf.export_dataset_item.assert_not_called()

    def test_hook_never_raises(self, lf):
        """Hook never raises even if internal errors occur."""
        dataset_mod = _load_dataset_hook_module()
        ld = self._make_loop_data()
        ext = dataset_mod.LangfuseDatasetExport(agent=None)

        mock_lf = MagicMock()
        mock_lf.get_langfuse_config.side_effect = RuntimeError("crash")
        with patch.object(dataset_mod, "_lib", return_value=mock_lf):
            # Should not raise
            asyncio.run(ext.execute(loop_data=ld))

    def test_hook_uses_default_dataset_name(self, lf):
        """Hook uses 'a0-traces' as default when config key is missing."""
        dataset_mod = _load_dataset_hook_module()
        ld = self._make_loop_data(
            last_response=json.dumps({
                "tool_name": "response",
                "tool_args": {"text": "answer"},
            }),
            user_message=MagicMock(content="hello"),
        )
        ext = dataset_mod.LangfuseDatasetExport(agent=None)

        mock_lf = MagicMock()
        mock_lf.get_langfuse_config.return_value = {
            "langfuse_dataset_export_enabled": True,
        }
        with patch.object(dataset_mod, "_lib", return_value=mock_lf):
            asyncio.run(ext.execute(loop_data=ld))

        _, kwargs = mock_lf.export_dataset_item.call_args
        assert kwargs["dataset_name"] == "a0-traces"

    def test_hook_skips_no_trace_id(self, lf):
        """Hook skips when lf_trace_id is missing."""
        dataset_mod = _load_dataset_hook_module()
        ld = self._make_loop_data(
            params_persistent={"lf_sampled": True, "lf_trace_id": "", "lf_session_id": ""},
            last_response=json.dumps({
                "tool_name": "response",
                "tool_args": {"text": "answer"},
            }),
            user_message=MagicMock(content="hello"),
        )
        ext = dataset_mod.LangfuseDatasetExport(agent=None)

        mock_lf = MagicMock()
        mock_lf.get_langfuse_config.return_value = {"langfuse_dataset_export_enabled": True}
        with patch.object(dataset_mod, "_lib", return_value=mock_lf):
            asyncio.run(ext.execute(loop_data=ld))
        mock_lf.export_dataset_item.assert_not_called()
