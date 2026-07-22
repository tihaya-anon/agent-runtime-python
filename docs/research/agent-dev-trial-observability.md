# Agent Development Trial Observability

Status: research note.

This note answers: if `agent-runtime-python` introduces deeper OpenTelemetry coverage for agent
development trials, what should be observable beyond the current study/trial/run spans?

## Current Repo Baseline

The runtime already owns Python-defined LangGraph graphs, worker-side event mapping, protocol
validation, direct runtime experiments, and runtime-internal telemetry for graph, node, model, tool,
and retrieval execution. It does not own browser-facing routes, product stream compatibility, or
whole-product path measurement through the TypeScript API gateway. [Source:
`docs/agents/runtime-boundary.md`](../agents/runtime-boundary.md)

Current telemetry spans are:

- `experiment.study`: one runtime study.
- `experiment.trial`: one trial command.
- `agent.run`: one accepted worker command.
- `agent.graph`: one registered graph execution.
- `agent.graph.node`: one LangGraph node execution.

These spans carry bounded, protocol-safe metadata such as Agent Run id, runtime profile id,
behavior-version dimensions, graph id, node name, experiment study/trial ids, target, parameters,
outcome, and worker error classification. Raw prompts, provider payloads, credentials, stack traces,
and tool arguments are intentionally excluded from boundary events and default span attributes.
[Source: `src/agent_runtime_python/observability/telemetry/`](../../src/agent_runtime_python/observability/telemetry/)
[Source: `docs/agents/runtime-usage.md`](../agents/runtime-usage.md)

The current Grafana dashboard uses Tempo trace drilldown and Tempo span metrics in Prometheus for
trial throughput, failed runs, p95 run latency, trial error ratio, outcome mix, runtime activity mix,
and recent trial drilldown. [Source:
`ops/observability/dashboards/generate_agent_runtime_experiments_dashboard.py`](../../ops/observability/dashboards/generate_agent_runtime_experiments_dashboard.py)

## Primary-Source Findings

OpenTelemetry semantic conventions provide common names for spans, metrics, logs, and events, and
reserve attributes/events such as `error.type`, `exception.type`, `exception.message`,
`exception.stacktrace`, and `exception` for error reporting. [Source:
OpenTelemetry semantic conventions](https://opentelemetry.io/docs/specs/otel/semantic-conventions/)
[Source: OpenTelemetry general semantic conventions](https://opentelemetry.io/docs/specs/semconv/general/)

OpenTelemetry GenAI conventions define AI-specific spans for inference, retrieval, agent invocation,
workflow invocation, tool execution, embeddings, and provider-specific OpenAI/Anthropic calls. They
include attributes for model request/response names, generation parameters, streaming, finish
reasons, token counts, cache-read input tokens, cache-creation input tokens, reasoning output tokens,
conversation id, agent identity, workflow name, retrieval data source id, top-k, and tool name/type.
Sensitive prompt, output, retrieval document, tool argument, and tool result attributes are marked
opt-in. [Source: OpenTelemetry GenAI spans model](https://raw.githubusercontent.com/open-telemetry/semantic-conventions/main/model/gen-ai/spans.yaml)
[Source: OpenTelemetry GenAI attributes model](https://raw.githubusercontent.com/open-telemetry/semantic-conventions/main/model/gen-ai/registry.yaml)

OpenTelemetry GenAI metrics define histograms for `gen_ai.client.token.usage`,
`gen_ai.client.operation.duration`, streaming time to first chunk, and streaming time per output
chunk. The token metric should use provider-reported usage when available, and should not report
usage if it cannot efficiently obtain token counts. [Source: OpenTelemetry GenAI metrics
model](https://raw.githubusercontent.com/open-telemetry/semantic-conventions/main/model/gen-ai/metrics.yaml)

OpenInference is an OpenTelemetry-based semantic convention for AI observability. It standardizes
span kinds such as `LLM`, `AGENT`, `CHAIN`, `TOOL`, `RETRIEVER`, `RERANKER`, `EMBEDDING`,
`GUARDRAIL`, `EVALUATOR`, and `PROMPT`, and includes token, cache, and cost attributes such as
`llm.token_count.prompt`, `llm.token_count.prompt_details.cache_read`,
`llm.token_count.prompt_details.cache_write`, `llm.token_count.completion_details.reasoning`, and
`llm.cost.total`. [Source: OpenInference specification](https://arize-ai.github.io/openinference/spec/)
[Source: OpenInference semantic conventions](https://arize-ai.github.io/openinference/spec/semantic_conventions.html)

OpenAI Responses usage includes `input_tokens`, `input_tokens_details.cached_tokens`,
`output_tokens`, `output_tokens_details.reasoning_tokens`, and `total_tokens`. The Responses API also
has `prompt_cache_key`, `prompt_cache_retention`, `max_tool_calls`, reasoning effort, truncation, and
stream completion events. [Source: OpenAI Responses API reference](https://developers.openai.com/api/reference/resources/responses/methods/create)

OpenAI organization usage reports expose aggregate input tokens, cached input tokens, output tokens,
model request counts, project id, user id, API key id, model, batch, and service tier. [Source:
OpenAI Usage API reference](https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage)

Anthropic reports `input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`, and
`output_tokens`; its pricing docs distinguish base input, cache write, cache hit/read, and output
pricing. The same docs show server tool usage fields such as web search and web fetch request
counts. [Source: Anthropic pricing and usage docs](https://platform.claude.com/docs/en/about-claude/pricing)

Anthropic `stop_reason` distinguishes successful generation stops such as `end_turn`,
`max_tokens`, `tool_use`, `pause_turn`, and `refusal` from API errors. [Source: Anthropic stop reason
handling](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons)

LangSmith evaluation docs treat datasets, examples, reference outputs, metadata, experiment outputs,
evaluator scores, execution traces, repetitions, latency, total tokens, and cost as core experiment
analysis dimensions. Repetitions exist because LLM outputs are nondeterministic and agents can have
high variability. [Source: LangSmith evaluation concepts](https://docs.langchain.com/langsmith/evaluation-concepts)
[Source: LangSmith experiment configuration](https://docs.langchain.com/langsmith/experiment-configuration)
[Source: LangSmith analyze an experiment](https://docs.langchain.com/langsmith/analyze-an-experiment)

LangSmith tracing docs require custom LLM traces to provide run type, provider/model metadata, token
usage, cost metadata, and time-to-first-token when custom wrappers are used. [Source: LangSmith log
LLM calls](https://docs.langchain.com/langsmith/log-llm-trace)

LangGraph persistence saves graph state as checkpoints at execution steps and supports
human-in-the-loop inspection, memory, time travel debugging, and fault tolerance. LangGraph streaming
supports `updates`, `values`, `messages`, `custom`, `checkpoints`, `tasks`, and `debug` projections,
which map naturally to node state updates, token streams, checkpoints, task starts/finishes, and
debug telemetry. [Source: LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
[Source: LangGraph streaming](https://langchain-ai.github.io/langgraph/agents/streaming/)

## What Agent Developers Usually Care About

### 1. Trial Identity and Reproducibility

Keep these as low-cardinality span attributes on `experiment.trial` and inherited child spans:

- `metadata.experiment.study_id`
- `metadata.experiment.trial_id`
- `metadata.experiment.trial_index`
- `metadata.experiment.trial_count`
- `metadata.experiment.target`
- `metadata.experiment.parameter.<name>`
- `metadata.runtime_profile.id`
- `metadata.agent_behavior_version.*`
- `metadata.source_revision`
- future dataset/example/repetition fields: `metadata.experiment.dataset_id`,
  `metadata.experiment.example_id`, `metadata.experiment.repetition_index`

Why: without stable trial, behavior, source, dataset, and repetition identity, latency, token, cache,
and quality numbers cannot be compared safely.

### 2. Outcome, Error, and Stop Reason

Keep the existing `metadata.experiment.outcome`, `metadata.agent_run.outcome`, and
`metadata.agent_run.error_classification`. Add standard `error.type` on failed model/tool/retrieval
spans, and add provider stop/finish fields when a model response succeeds but is incomplete,
truncated, refused, or waiting for tool use.

Recommended low-cardinality values:

- trial outcome: `succeeded`, `failed`, `cancelled`
- terminal event: `run.completed`, `run.failed`, `run.cancelled`
- run error classification: `validation`, `internal`, `provider`, `timeout`, `rate_limit`,
  `budget_exceeded`, `tool_error`, `parse_error`, `eval_failed`
- provider finish/stop reason: provider-native value plus normalized category such as `stop`,
  `length`, `tool_call`, `refusal`, `pause`, `error`

### 3. Budget, Tokens, Cache, and Cost

This is the most important missing layer for trial observability.

Track configured budget and consumed budget at trial scope:

- `metadata.experiment.trial_budget.max_input_tokens`
- `metadata.experiment.trial_budget.max_output_tokens`
- `metadata.experiment.trial_budget.max_total_tokens`
- `metadata.experiment.trial_budget.max_cost_usd`
- `metadata.experiment.trial_budget.max_tool_calls`
- `metadata.experiment.trial_budget.max_retries`
- `metadata.experiment.trial_budget.max_iterations`
- `metadata.experiment.trial_budget.max_checkpoints`
- `metadata.experiment.trial_budget.remaining_total_tokens`
- `metadata.experiment.trial_budget.remaining_cost_usd`
- `metadata.experiment.trial_budget.exhausted`: boolean
- `metadata.experiment.trial_budget.exhausted_reason`: low-cardinality string

Track provider usage at LLM call scope using standards first:

- OpenTelemetry GenAI: `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`,
  `gen_ai.usage.reasoning.output_tokens`, `gen_ai.usage.cache_read.input_tokens`,
  `gen_ai.usage.cache_creation.input_tokens`
- OpenInference equivalent: `llm.token_count.prompt`, `llm.token_count.completion`,
  `llm.token_count.total`, `llm.token_count.prompt_details.cache_read`,
  `llm.token_count.prompt_details.cache_write`,
  `llm.token_count.completion_details.reasoning`
- metrics: `gen_ai.client.token.usage` histogram labelled by token type, provider, model,
  operation, study, target, and possibly runtime profile

Do not call provider prompt-cache telemetry a raw "KV cache hit rate" unless the runtime owns the
inference server and can observe model-server KV cache internals. For hosted APIs, collect:

- cache read tokens
- cache creation/write tokens
- cache read ratio: `cache_read_input_tokens / input_tokens`
- cache write ratio: `cache_creation_input_tokens / input_tokens`
- effective cached-token savings/cost, if pricing is known

### 4. Latency and Streaming Responsiveness

Keep span-metrics p95 for the existing span spine, then add LLM/tool/retrieval child latency:

- trial duration
- agent run duration
- graph duration
- graph node duration
- model operation duration
- time to first token/chunk for streaming responses
- time per output chunk
- tool duration
- retrieval duration
- retry delay/backoff duration
- queue/wait duration if a target introduces async execution

### 5. Agent Control Flow and Graph Shape

For agent development, the trace must explain the path taken:

- graph id and graph node name
- node attempt number
- agent loop iteration number
- selected route/edge decision as a bounded label
- number of child LLM calls
- number of tool calls
- number of retrieval calls
- final node and terminal event
- checkpoint/thread ids when persistence is enabled

Use spans for operations and events for point-in-time decisions such as "route selected",
"budget checked", "retry scheduled", or "checkpoint saved".

### 6. Tools and External Effects

Add child spans for every tool execution:

- span name: `gen_ai.execute_tool` or existing local equivalent
- tool name: required
- tool type: `function`, `extension`, `datastore`, or repo-local low-cardinality type
- tool call id if available
- outcome and `error.type`
- duration
- optional/redacted arguments and result only when explicitly enabled
- counts by tool name, outcome, and error type

For safety, raw tool arguments/results should remain opt-in and redacted by default, matching the
repo's current boundary rule.

### 7. Retrieval, Memory, and Checkpoints

Add retrieval spans when a graph fetches context:

- data source id
- top-k requested
- documents returned
- filtered count
- score summary such as min/max/mean, not full content by default
- optional document ids/scores when safe
- embedding model and token usage for embedding calls

For LangGraph persistence, record thread/checkpoint identifiers and counts, but not full state by
default:

- thread id
- checkpoint id
- checkpoint namespace
- step/super-step number
- checkpoint saved/restored/replayed event
- checkpoint size bucket if available
- pending write recovery count if available

### 8. Evaluation Quality

Agent development is not only operational health. Each trial needs quality signals:

- dataset id/name/version
- example id
- repetition index/count
- evaluator name/version
- evaluator span kind
- numeric score
- pass/fail label
- rubric version or criteria id
- human feedback score/comment presence
- comparison baseline id when doing A/B trials

Do not put long evaluator rationales on default span attributes. Store only bounded labels and scores
by default; attach explanations through opt-in logs/artifacts if needed.

### 9. Reliability, Retry, and Cancellation

Track the mechanics that often explain bad trials:

- retries attempted
- max retries
- retry reason
- backoff duration
- timeout budget
- cancellation requested/observed
- rate limit errors
- HTTP/provider status class
- provider error code normalized into `error.type`
- partial output flag
- parse/schema validation outcome

The concrete span shape, dashboard panel list, logs/events guidance, privacy guidance, and
implementation steps now live in
[`agent-dev-trial-observability-implementation.md`](agent-dev-trial-observability-implementation.md).
