# Langfuse Dataset Auto-Export

## Overview

When enabled, the Langfuse plugin automatically exports successful agent traces as **dataset items** — test cases you can reuse for experiments, evaluations, and regression testing in the Langfuse UI.

## How It Works

1. Agent completes a monologue normally (produces a `response` tool call)
2. The `_30_langfuse_dataset.py` hook fires during `monologue_end` (after the judge hook, before the flush hook)
3. It calls `client.create_dataset_item()` with:
   - `input` — the user's message (`{"role": "user", "content": "..."}`)
   - `expected_output` — the agent's final response text
   - `source_trace_id` — links back to the original trace in Langfuse UI
   - `metadata` — session ID for context
4. The dataset item appears in Langfuse under **Datasets → [dataset_name]**

## What Gets Exported

Only **successful** traces are exported:
- Trace must be sampled (`lf_sampled` is true)
- `last_response` must be a valid `response` tool call (errors and stops are skipped)
- Both user message and response text must be non-empty

## Configuration

In the plugin settings UI (or `default_config.yaml`):

```yaml
langfuse_dataset_export_enabled: true
langfuse_dataset_name: "a0-traces"
```

- **`langfuse_dataset_export_enabled`** — toggle on/off (default: `false`)
- **`langfuse_dataset_name`** — target dataset name (auto-created by Langfuse if it doesn't exist)

## Running Experiments

Once you have dataset items in Langfuse:

1. Go to **Datasets** in the Langfuse UI
2. Select the `a0-traces` dataset (or your custom name)
3. Click **Create Experiment**
4. Choose your model/prompt configuration
5. Langfuse replays each `input` through your configured pipeline
6. Compare outputs against `expected_output` using scores or manual review

## Source Trace Linking

Each dataset item includes `source_trace_id`, which creates a clickable link in the Langfuse UI back to the original trace. This lets you:
- Inspect the full agent interaction that generated the test case
- Verify the expected output came from a real conversation
- Debug experiment failures by comparing against the source trace

## Technical Details

- **Hook order**: `_30_langfuse_dataset.py` runs after `_20_langfuse_judge.py` (so quality scores are already on the trace) and before `_90_langfuse_flush.py` (so trace context is still active)
- **Never raises**: all errors are caught and logged at debug level — export failures never disrupt the agent
- **Truncation**: both input and expected_output are capped at 5000 characters
- **SDK method**: uses `client.create_dataset_item()` from the Langfuse Python SDK v4
