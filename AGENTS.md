# a0_langfuse Plugin DOX

## Purpose

Send LLM observability data to Langfuse with real token/cost data. Uses a **corrected tracing model** (v3): AGENT root observation, AGENT iterations with nested GENERATION (via `parent_span_id`) + TOOL children, EVENT narrative events via native `@extensible` on `Log.log()`, and SPAN utility observations. LiteLLM `_StreamingGenerationWrapper` captures GENERATION observations with token/cost data. Feature hooks perform scoring, prompt sync, and feedback.

**v3 corrected tracing model (2026-07-08):** Observation hierarchy matches Langfuse recommendations for agentic frameworks: AGENT root → AGENT iteration → GENERATION (nested via `parent_span_id`) + TOOL + EVENT children. Iteration span_id stored in `_current_iteration_span_id` contextvar for callback-safe nesting.

**v3 narrative tap (2026-07-07):** Single tap on `Log.log()` captures all 15 A0 event types as EVENT observations. Requires `@extensible` on `Log.log()` in `helpers/log.py` (A0 core). Filters noisy types (`progress`, `info`, `hint`, `response`) and empty entries.

## Knowledge

- **Owning KB:** none dedicated — catalog entry in `~/knowledge/agent_zero_plugins` (② Tool). Promote to a dedicated KB if this plugin grows substantial durable knowledge (Hub placement rule #7).
- **Access:** OpenKnowledge MCP only — `cwd: ~/knowledge/agent_zero_plugins`. Tools: `exec`, `search`, `write`, `edit`, `audit`, `lint`. Never `lsp` on KB markdown.
- **Fleet index:** `vanja-emichi/vbunjevac` → `registry/repos.md`.

## Ownership

- `plugin.yaml` — manifest; `default_config.yaml` — defaults; `.toggle-1` — enabled; `.gitignore` — protects `config.json`, `.env`, build artifacts; `config.json` (gitignored) — user configuration
- `extensions/python/lib/langfuse_client.py` — singleton client, config resolution, `LangfuseGenerationLogger` (CustomLogger), `_StreamingGenerationWrapper`, all scoring/tracking functions, contextvars (`_current_trace_id`, `_current_session_id`, `_current_parent_obs`, `_current_iteration_span_id`, `_current_loaded_skills`, `_utility_llm_result`), `_build_log_metadata()`, imports from `_helpers.py`
- `extensions/python/lib/_helpers.py` — pure functions: truncation limits, `_MODEL_PRICING`, `_SENSITIVE_KEY_PATTERNS`, format-agnostic helpers, `_sanitize_for_capture`, `_compute_cost_details`, `_format_generation_input`, `_filter_sensitive_args`
- `extensions/python/lib/_shared.py` — shared `lib()` dynamic import helper
- `extensions/python/agent_init/_90_langfuse_init.py` — initialize client on agent startup
- `extensions/python/_functions/helpers/log/Log/log/end/_90_langfuse_narrative.py` — **Narrative Tap**: captures Log.log() events as EVENT observations; filters ALL activity types (`progress`, `info`, `hint`, `response`, `agent`, `tool`, `code_exe`, `subagent`, `util`, `input`, `user`, `browser`, `mcp`) — only `error` and `warning` events pass through (all other types are covered by structured AGENT/TOOL/GENERATION/SPAN observations)
- `extensions/python/monologue_start/_20_langfuse_feedback.py` — implicit feedback scoring (`user-stopped: 0` / `user-followup: 1`)
- `extensions/python/monologue_start/_90_langfuse_trace.py` — root AGENT trace creation, subordinate linking via `trace_context` with `parent_span_id`; includes agent profile name in observation name and metadata (e.g., `agent-1-researcher-monologue`)
- `extensions/python/monologue_end/_90_langfuse_flush.py` — trace output, context manager cleanup, flush, clear context, skill tags + feature tags
- `extensions/python/monologue_end/_20_langfuse_judge.py` — LLM-as-a-Judge (sampled, disabled by default)
- `extensions/python/monologue_end/_30_langfuse_dataset.py` — auto-export successful traces as Langfuse dataset items (disabled by default)
- `extensions/python/message_loop_start/_90_langfuse_iteration.py` — AGENT iteration observation, stores span_id in contextvar, reads loaded skills from agent context for trace tagging
- `extensions/python/message_loop_end/_90_langfuse_iteration_end.py` — ends iteration AGENT, clears span_id
- `extensions/python/tool_execute_before/_90_langfuse_tool.py` — TOOL observation with filtered args
- `extensions/python/tool_execute_after/_90_langfuse_tool_end.py` — updates TOOL output, ends observation
- `extensions/python/util_model_call_before/_90_langfuse_util_start.py` — SPAN for background LLM calls
- `extensions/python/util_model_call_after/_90_langfuse_util_end.py` — updates SPAN output, ends
- `extensions/python/error_format/_90_langfuse_errors.py` — scores `framework-error: 0` (BOOLEAN)
- `extensions/python/_functions/agent/Agent/handle_exception/end/_90_langfuse_exceptions.py` — scores `raw-exception: 0` (BOOLEAN)
- `extensions/python/_functions/agent/Agent/handle_intervention/end/_90_langfuse_intervention.py` — scores `user-intervention: 0` (BOOLEAN) when InterventionException fires
- `extensions/python/hist_add_before/_90_langfuse_quality.py` — SYNC: pattern-matches 4 quality signals, scores BOOLEAN(0)
- `extensions/python/process_chain_end/_90_langfuse_chain.py` — tags trace with `chain-complete`
- `extensions/python/_functions/agent/Agent/hist_add_ai_response/end/_90_langfuse_feedback_target.py` — captures message→trace mapping for feedback attribution
- `extensions/python/system_prompt/_90_langfuse_prompt_sync.py` — uploads A0 prompt to Langfuse (disabled by default)
- `extensions/python/message_loop_prompts_before/_90_langfuse_prompt_override.py` — downloads Langfuse prompt override (disabled by default)
- `initialize.py` — pip install langfuse>=4.0.0,<5.0.0
- `hooks.py` — reset client on config save
- `api/langfuse_feedback.py` — POST endpoint for explicit user feedback (thumbs up/down)
- `extensions/webui/set_messages_after_loop/feedback-buttons.js` — feedback buttons UI
- `webui/config.html` — settings UI
- `tests/test_langfuse_plugin.py` — 174 unit tests across 33 test classes
- `tests/test_dataset_export.py` — 15 unit tests across 2 test classes (dataset export function + hook)
- `tests/conftest.py` — sys.path setup
- `skills/langfuse/` — Langfuse assistant skill (SKILL.md + 9 reference files)

**Disabled:** `extensions/python/_functions/helpers/log/LogItem.bak/` — LogItem.update() fires per streaming token, cannot be filtered to decision-only; agent thoughts are captured in GENERATION observation output/metadata instead

## Local Contracts

### Architecture: Option C — Manual GENERATION via SDK trace_context

The Langfuse SDK creates traces/observations via its own OTel pipeline. LLM GENERATION observations are created by `LangfuseGenerationLogger`, a LiteLLM CustomLogger that uses the SDK's `trace_context` parameter to link GENERATIONs to our existing trace. This avoids the separate-OTel-provider conflict that prevented trace merging with `langfuse_otel`.

### Data Flow

1. **monologue_start** creates root AGENT observation (`as_type="agent"`), sets trace context
2. **message_loop_start** creates AGENT iteration nested under root, stores span_id in contextvar
3. **LLM calls** → GENERATION created via `trace_context={"trace_id": ..., "parent_span_id": iteration_span_id}`
4. **tool_execute_before/after** → TOOL observations with filtered I/O
5. **util_model_call_before/after** → SPAN observations for background LLM calls
6. **Log.log() events** → EVENT observations via narrative tap
7. **message_loop_end** → ends iteration AGENT, clears span_id
8. **monologue_end** → sets trace output, ends root AGENT, flushes

### Key Design Decisions

- **`trace_context`** with `parent_span_id` — links GENERATION to iteration even after parent ended (confirmed by DeepWiki)
- **contextvars** — `_current_trace_id`, `_current_session_id`, `_current_parent_obs`, `_current_iteration_span_id` for per-context isolation
- **Narrative tap** — captures Log.log() events as EVENT type (per Langfuse docs); filters noisy types
- **TOOL type** — tool observations use `as_type="tool"` (per Langfuse docs)
- **No env var export** — secrets passed directly to `Langfuse()` constructor
- **Subordinate traces** — parallel subordinates nest within parent trace via `parent_span_id` (reads `_parallel_parent_context_id` from worker context); chain subordinates link via `Agent.DATA_NAME_SUPERIOR`

### Active Feature Set

- **LLM-as-a-Judge**: sampled quality scoring (disabled by default)
- **Dataset export**: auto-export successful traces as dataset items for experiments (disabled by default)
- **Prompt sync**: bidirectional prompt management (disabled by default)
- **Rate/retry tracking**: wraps rate limiters and transport for retry scores
- **Feedback API**: thumbs up/down with server-side message→trace mapping
- **Error scoring**: `framework-error: 0`, `raw-exception: 0` (BOOLEAN)
- **Quality signals**: `misformat`, `repeat`, `tool-not-found`, `critical-error` (BOOLEAN 0)
- **Chain tracking**: `chain-complete` tag
- **Utility model spans**: SPAN observations for background LLM calls
- **Multi-modality**: image extraction from multi-modal messages
- **Implicit feedback**: `user-stopped: 0` / `user-followup: 1`

## Work Guidance

- After code changes, clear `__pycache__` AND restart A0
- Use `start_observation()` for child observations, `start_as_current_observation(end_on_exit=False)` for root
- `contextvars.ContextVar` values are the source of truth for trace linking
- Feedback attribution uses server-side message→trace mapping, never client-provided trace IDs
- CRITICAL: `from helpers import litellm_transport` fails in plugin context — use `sys.modules.get('helpers.litellm_transport')`
- Responses API 404s for glm-5.2 → transport falls back to Chat Completions (wrapped by `_StreamingGenerationWrapper`)
- **Importlib bootstrap convention**: All extension hook files use the same `_shared.py` discovery pattern to load `_lib()`. This is required because A0 loads plugins via `importlib.util.spec_from_file_location` which does NOT set up A0's package paths. New hooks MUST copy this pattern verbatim from any existing hook file. Do NOT attempt to refactor into a shared import — the discovery works because each file walks up from its own `__file__` location.

## Verification

1. Unit tests: `cd /a0/usr/plugins/a0_langfuse && /opt/venv-a0/bin/python -m pytest tests/test_langfuse_plugin.py -v`
2. Compile: `/opt/venv-a0/bin/python -m py_compile extensions/python/lib/langfuse_client.py`
3. E2E: Send message → verify trace in Langfuse with AGENT root, nested GENERATION, TOOL observations

## DOX Framework

- DOX is a highly performant AGENTS.md hierarchy
- AGENTS.md files are binding work contracts for their subtrees
- Read nearest AGENTS.md + every parent before editing
- Update closest owning AGENTS.md after meaningful changes
- If docs conflict, the closer doc controls local work details

### Core Contract

- Work products, source materials, instructions, records, assets, and durable docs must stay understandable from the nearest applicable AGENTS.md plus every parent AGENTS.md above it

### Style

- Keep docs concise, current, and operational
- Document stable contracts, not diary entries
- Put broad rules in parent docs and concrete details in child docs

## Child DOX Index

| Child | Scope |
|-------|-------|
| `extensions/python/lib/` | Core client singleton (~1540 lines), LangfuseGenerationLogger, _StreamingGenerationWrapper, config, contextvars, cost calculation, all scoring/tracking functions |
| `extensions/python/_shared.py` | Shared `lib()` dynamic import helper |
| `extensions/python/` (hooks) | 15 lifecycle extension hooks: agent_init, monologue_start/2, monologue_end/3, message_loop_start/end, tool_execute_before/after, util_model_call_before/after, error_format, hist_add_before, process_chain_end, system_prompt, message_loop_prompts_before |
| `extensions/python/_functions/` | Custom function hooks: Log/log/end (narrative tap), handle_exception/end (raw-exception scoring), handle_intervention/end (intervention scoring), hist_add_ai_response/end (feedback target) |
| `api/` | REST API endpoint for user feedback |
| `webui/` + `extensions/webui/` | Settings UI + feedback buttons |
| `tests/` | 189 unit tests across 35 test classes + conftest |
| `skills/langfuse/` | Langfuse assistant skill — SKILL.md + 9 reference files |
