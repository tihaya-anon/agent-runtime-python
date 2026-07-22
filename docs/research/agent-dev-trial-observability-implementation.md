# Agent Development Trial Observability Implementation Appendix

Status: research appendix.

This appendix continues
[`agent-dev-trial-observability.md`](agent-dev-trial-observability.md) with concrete span shape,
dashboard, and implementation guidance.

## Logs and Events

Use spans for timed operations, metrics for aggregate behavior, and span events/logs for bounded
point-in-time facts that explain a run without creating new spans:

- route selected
- budget checked or exhausted
- retry scheduled
- checkpoint saved, loaded, or replayed
- stream first chunk observed
- model response refused, truncated, or paused
- evaluator completed

Do not use logs as a bypass for payload safety. The same redaction and opt-in content rules apply.

## Privacy and Payload Safety

Keep the current default: no raw prompts, provider payloads, credentials, stack traces, raw LangGraph
chunks, or tool arguments in default span attributes. Add a separate opt-in content capture switch if
developers need payload-level debugging locally. When enabled, prefer truncation, redaction, and
local-only exporters.

## Recommended Span Shape

```text
experiment.study
  experiment.trial
    agent.run
      agent.graph
        agent.graph.node
          gen_ai.inference.client
          gen_ai.execute_tool.internal
          gen_ai.retrieval.client
          gen_ai.embeddings.client
          agent.evaluation
```

Use the existing repo span names for the runtime-owned spine. Add OpenTelemetry GenAI or
OpenInference attributes on AI child spans. If both conventions are emitted, centralize the mapping
in `src/agent_runtime_python/observability/telemetry.py` so dashboards and tests do not duplicate
provider-specific field logic.

## Recommended Metrics and Dashboard Panels

Add these next to the existing dashboard panels:

- Token usage by study/model/token type.
- Cost by study/model/provider.
- Cache read ratio and cache creation ratio.
- Budget exhausted trials by reason.
- LLM operation p50/p95/p99.
- Streaming time to first chunk/token.
- Tool calls by tool and outcome.
- Retrieval latency and returned-document count.
- Retry count by reason.
- Eval score distribution by evaluator and parameter.
- Outcome by behavior-version dimension.
- Top failing graph nodes by `error.type`.

## Implementation Guidance for This Repo

1. Keep the current trace spine and bounded attribute policy.
2. Add a small telemetry API for model calls, tool calls, retrievals, evaluator calls, and budget
   snapshots instead of scattering raw `span.set_attribute` calls across graph code.
3. Prefer standard attribute names where there is a clear match:
   - OpenTelemetry GenAI for `gen_ai.*` spans and metrics.
   - OpenInference for `openinference.span.kind`, `llm.*`, `tool.*`, `retrieval.*`, and `graph.*`
     names already available through the existing `openinference-semantic-conventions` dependency.
4. Treat prompt cache read/write tokens as first-class telemetry. Compute "cache hit ratio" from
   provider-reported cached token counts; reserve true "KV cache hit" for future self-hosted
   inference where the runtime can observe server-side cache internals.
5. Add trial budget fields before adding many dashboard panels. Budget fields make failures and
   quality/cost tradeoffs interpretable.
6. Extend JSONL trial results with bounded numeric fields for usage, cache, cost, budget exhaustion,
   latency, and eval scores so offline experiments and OTEL traces agree.
7. Add targeted tests for any telemetry helper that maps provider usage into standard attributes.
