# Langfuse CLI Reference

Documentation: https://langfuse.com/docs/api-and-data-platform/features/cli

## Install

Run these commands via `code_execution_tool` with `runtime: terminal`:

```bash
# Run directly (recommended)
npx langfuse-cli api <resource> <action>
bunx langfuse-cli api <resource> <action>

# Or install globally
npm i -g langfuse-cli
langfuse api <resource> <action>
```

## Discovery

Run these via `code_execution_tool` with `runtime: terminal`:

```bash
# List all resources and auth info
langfuse api __schema

# List actions for a resource
langfuse api <resource> --help

# Show args/options for a specific action
langfuse api <resource> <action> --help

# Preview the curl command without executing
langfuse api <resource> <action> --curl
```

## Credentials

Set environment variables (via `code_execution_tool` with `runtime: terminal`):

```bash
export LANGFUSE_PUBLIC_KEY=pk-lf-...
export LANGFUSE_SECRET_KEY=sk-lf-...
export LANGFUSE_BASE_URL=https://cloud.langfuse.com  
```

## Tips

- Use `--json` for machine-readable JSON output
- Use `--curl` to preview the HTTP request without executing
- All list commands support filtering — check `<resource> <action> --help` for available options
- Prefer `observations` over `legacy-observations-v1s` — `observations` is the modern high-performance endpoint (cursor pagination, selective field groups); `legacy-observations-v1s` is the deprecated v1
- Prefer `metrics` over `legacy-metrics-v1s` for the same reason
- Prefer `scores` over `legacy-score-v1s` for list/get operations
- For broad trace queries, `traces list` can time out on Langfuse Cloud — use `observations list` (with `--trace-id` if you're traversing from a known trace) instead. See the [Observations API docs](https://langfuse.com/docs/api-and-data-platform/features/observations-api) for the v1 → v2 mapping.
- Pagination: legacy v1 endpoints use `--limit` and `--page`; modern endpoints (`observations`, `metrics`, `scores`) use cursor-based pagination — pass `--limit`, then thread `meta.cursor` from the response into the next request's `--cursor`

## Critical Gotchas

### observations list: ALWAYS pass `--fields`

The modern `observations list` endpoint uses **field group selection**. Without `--fields`, only 13 core fields are returned — **no `name`, no `model`, no `usage`, no `costDetails`**.

```bash
# WRONG — names and usage are missing (13 fields, no name/model/usage)
npx langfuse-cli api observations list --trace-id TRACE_ID

# CORRECT — request the field groups you need
npx langfuse-cli api observations list \
  --fields "core,basic,model,usage" \
  --filter '[{"type":"string","column":"traceId","operator":"=","value":"TRACE_ID"}]'
```

Available field groups:

| Group | Includes |
|---|---|
| `core` | id, traceId, startTime, endTime, type, parentObservationId, projectId (always included) |
| `basic` | **name**, level, environment, userId, sessionId |
| `model` | **model** (providedModelName), internalModelId, modelParameters |
| `usage` | **usageDetails**, **costDetails**, totalCost |
| `io` | input, output |
| `metadata` | metadata (truncated to 200 chars; use `--expand-metadata` for full values) |
| `time` | completionStartTime, createdAt, updatedAt |
| `metrics` | latency, timeToFirstToken |
| `trace_context` | tags, release, traceName |

Default: `core` + `basic` field groups are returned if `--fields` is not specified. However, the CLI v2 default returns only `core` fields (13 keys) in practice — always pass `--fields` explicitly.

### scores list: ALWAYS use `--filter`, never `--trace-id`

The v2 scores endpoint **ignores `traceId` as a query parameter** and returns all project scores. Use the JSON `--filter` format instead:

```bash
# WRONG — returns ALL scores across the project, not just this trace
npx langfuse-cli api scores list --trace-id TRACE_ID

# CORRECT — returns only scores for this trace
npx langfuse-cli api scores list \
  --filter '[{"type":"string","column":"traceId","operator":"=","value":"TRACE_ID"}]'
```

This applies to any v2 endpoint that supports `--filter`: prefer the structured JSON filter over simple query parameter flags.

### Ready-to-use: Full trace analysis query

```bash
# 1. Get trace observations with full data
npx langfuse-cli api observations list \
  --fields "core,basic,model,usage" \
  --filter '[{"type":"string","column":"traceId","operator":"=","value":"TRACE_ID"}]'

# 2. Get scores for this trace only
npx langfuse-cli api scores list \
  --filter '[{"type":"string","column":"traceId","operator":"=","value":"TRACE_ID"}]'

# 3. Get trace metadata (cost, latency, session)
npx langfuse-cli api traces list \
  --fields "core,scores,metrics" \
  --filter '[{"type":"string","column":"id","operator":"=","value":"TRACE_ID"}]'
```
