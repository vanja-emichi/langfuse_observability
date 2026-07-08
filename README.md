# Langfuse Observability for Agent Zero

Send LLM traces, tool spans, and agent interactions to [Langfuse](https://langfuse.com) with **real token and cost data**.

## Features

- **Real token tracking** — captures actual provider-reported prompt/completion tokens via LiteLLM `CustomLogger`
- **Cost tracking** — per-call cost from LiteLLM's `completion_cost()`
- **Tool spans** — every tool execution traced with args and results
- **Iteration spans** — each agent loop iteration tracked as a child span
- **Session grouping** — traces grouped by chat context
- **Cross-chat isolation** — `contextvars.ContextVar` prevents trace ID leakage between concurrent chats
- **Sampling support** — configurable sample rate for high-volume deployments

## Architecture: Option C — Manual GENERATION via SDK trace_context

The plugin uses a single-layer architecture where the Langfuse v4 SDK owns the entire trace lifecycle:

1. **A0 Extensions** create the trace structure (root → iterations → tools) via the SDK's `start_as_current_observation()` and `start_observation()` APIs
2. **`LangfuseGenerationLogger`** (a LiteLLM `CustomLogger`) fires on LLM success/failure events and creates GENERATION observations via `client.start_as_current_observation(trace_context={"trace_id": trace_id}, as_type="generation")`
3. **W3C trace_context** links the GENERATION to the SDK-created trace — the official approach per Langfuse documentation

This means token counts come directly from the provider response (e.g., OpenAI `usage` object), not from tiktoken estimation.

### What was removed (and why)

The following components were part of earlier architecture iterations and have been removed:

| Removed | Reason |
|---------|--------|
| `litellm.success_callback = ["langfuse"]` | LangFuseLogger incompatible with v4 SDK |
| `langfuse_otel` callback | Separate OTel provider conflict — orphaned traces |
| Transport patch (`_patch_acompletion`) | Injected metadata into LLM kwargs — unnecessary with trace_context |
| Contextvars bridge (`LangfuseTraceBridge`) | Replaced by `LangfuseGenerationLogger` |
| `before_main_llm_call` extension | No-op after architecture pivot |
| `response_stream_end` extension | No-op after architecture pivot |
| `os.environ` key export | Security risk — keys now passed directly to constructor |
| Multi-agent nesting | Feature dropped — each chat gets its own trace |

## What Gets Traced

| Entity | What | Source |
|--------|------|--------|
| **Trace** | One per agent monologue | A0 extension (`monologue_start`) |
| **GENERATION** | One per LLM call (tokens, cost, model, I/O) | `LangfuseGenerationLogger` (LiteLLM callback) |
| **SPAN** | One per tool execution (args, result) | A0 extension (`tool_execute_before`/`after`) |
| **SPAN** | One per loop iteration | A0 extension (`message_loop_start`/`end`) |

```
Trace: agent-0-monologue
├── SPAN: iteration-0
│   ├── GENERATION: glm-5.2 (in=3963, out=132)
│   └── SPAN: code_execution_tool
├── SPAN: iteration-1
│   ├── GENERATION: glm-5.2 (in=2050, out=89)
│   └── SPAN: text_editor
└── SPAN: iteration-2
    └── GENERATION: glm-5.2 (in=812, out=45)
```

## Installation

1. Install the plugin into your Agent Zero plugins directory:

```bash
git clone <repo-url> /path/to/agent-zero/usr/plugins/a0_langfuse
```

2. In Agent Zero settings, go to Plugins and click **Initialize** to install the `langfuse` Python package.

3. Configure your Langfuse credentials (see below).

## Configuration

Configure via the Agent Zero settings UI (Plugins > Langfuse section).

| Setting | Config Key | Default |
|---------|-----------|--------|
| Enable | `langfuse_enabled` | `false` |
| Public Key | `langfuse_public_key` | - |
| Secret Key | `langfuse_secret_key` | - |
| Host | `langfuse_host` | `https://cloud.langfuse.com` |
| Environment | `langfuse_environment` | Auto-detected (`production` if `--dockerized=true`, else `development`) |
| Sample Rate | `langfuse_sample_rate` | `1.0` |

**Auto-enable**: If `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` environment variables are set, tracing activates automatically even if the toggle is off. Auto-enable only fires for env-var sourced keys, not config keys — explicit `langfuse_enabled: false` is respected.

**Secrets handling**: Keys are passed directly to the `Langfuse()` constructor via parameters — they are never exported to `os.environ`.

## Requirements

- Agent Zero framework
- `langfuse>=4.0.0,<5.0.0` Python package (auto-installed)
- Langfuse account (cloud or self-hosted)

## Troubleshooting

**No traces appearing**: Check that keys are correct and plugin is enabled. Look for log messages from `langfuse_client`. Verify the `langfuse_environment` field matches your Langfuse project's environment.

**GENERATION not linked to trace**: Ensure the plugin was loaded before the first LLM call. The `LangfuseGenerationLogger` must be registered in both sync and async LiteLLM callback paths during `agent_init`.

**Token counts showing 0**: This should not happen with this plugin. If it does, verify your provider returns usage data in responses. Token data comes from `response_obj.usage` (provider-reported), not from tiktoken estimation.

**Changes not taking effect**: Restart Agent Zero after code changes to extension files — the `_lib()` `sys.modules` cache doesn't auto-clear.

**Performance impact**: The plugin adds minimal overhead. Langfuse SDK batches and flushes asynchronously.
