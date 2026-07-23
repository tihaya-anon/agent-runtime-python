# Agent Experimentation Challenges, July 2026

Status: research note.

This note answers: what hard problems in building, evaluating, and operating AI agents matter for
`agent-runtime-python` if the repo wants to become a better experimental environment, not a
production agent framework?

Source policy: primary sources only. The sources used here are official product docs/specs from
OpenTelemetry, MLflow, LangSmith/LangGraph, OpenAI, Anthropic, Google, and Microsoft, plus primary
benchmark and evaluation publications.

## Repo Context

This repo is a Python Agent Run runtime, experiment runner, and observability toolkit for
LangGraph-backed development trials. Its main runtime surfaces are the NDJSON worker protocol,
experiment planning/results, direct/internal/gateway targets, and OpenTelemetry-based telemetry.
[Source: repo `docs/codebase.md`](../codebase.md)

The repo's domain language already centers on Development Trials, Trial Budgets, Provider Usage,
Model Usage Breakdowns, Experiment Metadata, and Usage Snapshots. [Source: repo `CONTEXT.md`](../../CONTEXT.md)

Existing research notes recommend preserving a runtime-owned span spine while adding standard
GenAI model/tool/retrieval/evaluator child spans, provider usage, cache usage, budget state, latency,
and eval scores to traces and JSONL results. [Source:
`agent-dev-trial-observability.md`](agent-dev-trial-observability.md) [Source:
`agent-dev-trial-observability-implementation.md`](agent-dev-trial-observability-implementation.md)

## Current Hard Problems

### 1. Agent correctness is trajectory correctness, not just answer correctness.

LangSmith describes agent evaluation at three levels: final response, single step, and trajectory;
trajectory evaluation checks whether the agent took the expected path of tool calls or decisions.
[Source: LangSmith application-specific evaluation approaches](https://docs.langchain.com/langsmith/evaluation-approaches)

Google's Gen AI agent evaluation docs make the same split between final response evaluation and
trajectory evaluation, and define trajectory metrics such as exact match, in-order match, any-order
match, precision, recall, and single-tool-use checks. [Source: Google Cloud Evaluate Gen AI
agents](https://cloud.google.com/vertex-ai/generative-ai/docs/models/evaluation-agents)

Microsoft Foundry's agent evaluators distinguish system evaluation from process evaluation, and its
process evaluators cover tool selection, tool input accuracy, tool output utilization, and tool call
success. [Source: Microsoft Foundry agent evaluators](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/agent-evaluators)

The `tau-bench` paper argues that real-world tool agents must converse with users, call tools, and
follow domain policy; its evaluation compares final database state against an annotated goal state
and uses a `pass^k` metric to measure reliability across repeated trials. [Source: `tau-bench`
paper](https://arxiv.org/abs/2406.12045)

Implication: this repo should treat each trial result as a record of both outcome and path: graph
nodes, route decisions, tool names, tool inputs at a safe normalized level, tool outputs at a safe
normalized level, and final response/evaluator scores.

### 2. Stochasticity makes one-run results weak evidence.

LangSmith documents repetitions because LLM outputs are non-deterministic and agents can have high
variability; repeated runs let experiment tables show average feedback score and standard deviation.
[Source: LangSmith repetitions](https://docs.langchain.com/langsmith/repetition)

Microsoft Agent Framework supports `num_repetitions` for agent evaluation so each query can run
multiple independent times to detect non-deterministic behavior. [Source: Microsoft Agent Framework
evaluation](https://learn.microsoft.com/en-us/agent-framework/agents/evaluation)

`tau-bench` reports that even state-of-the-art function-calling agents such as GPT-4o were
inconsistent in 2024, with less than 50% task success and retail `pass^8` below 25% in its reported
experiments. [Source: `tau-bench` paper](https://arxiv.org/abs/2406.12045)

The METR time-horizon paper models success as a function of human task time and reports that
frontier model time horizons had been doubling about every seven months, while noting limits to
external validity. [Source: METR time-horizon paper](https://arxiv.org/abs/2503.14499)

Implication: the experiment runner should make repetitions first-class metadata and report
confidence-oriented summaries, not only one row per parameter setting.

### 3. Hard benchmarks are often not fair benchmarks.

OpenAI's 2024 SWE-bench Verified work found that the original SWE-bench could underestimate model
capability because some tasks were hard or impossible to solve; SWE-bench Verified was created as a
500-sample human-validated subset. [Source: OpenAI SWE-bench Verified](https://openai.com/index/introducing-swe-bench-verified/)

OpenAI's February 23, 2026 analysis says SWE-bench Verified no longer measured frontier coding
capabilities well because of residual flawed tests and benchmark exposure during training; in a
138-problem audit, at least 59.4% of audited problems had material test or problem-description
issues. [Source: OpenAI SWE-bench Verified follow-up](https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/)

OpenAI's July 8, 2026 SWE-Bench Pro audit estimated that about 30% of public-split tasks were
broken, with issues including overly strict tests, underspecified prompts, low-coverage tests, and
misleading prompts. [Source: OpenAI SWE-Bench Pro audit](https://openai.com/index/separating-signal-from-noise-coding-evaluations/)

OSWorld was introduced as an execution-based benchmark for open-ended computer tasks in real OS
environments, and its paper reported that humans completed over 72.36% of tasks while the best model
completed 12.24% in the original evaluation. [Source: OSWorld paper](https://arxiv.org/abs/2404.07972)

Implication: this repo should include evaluation-set QA affordances: task provenance, reference
quality notes, hidden-test assumptions, evaluator version, failure taxonomy, and a way to mark a
trial failure as an eval-data defect instead of a model/runtime defect.

### 4. Observability needs standard traces plus payload discipline.

OpenTelemetry's GenAI semantic conventions define development-stage attributes for provider,
request/response model, finish reasons, streaming, token usage, cache-read tokens, cache-creation
tokens, reasoning-output tokens, conversation ID, agent identity, tool identity, retrieval metadata,
evaluation scores, prompts, and workflow names. [Source: OpenTelemetry GenAI registry](https://raw.githubusercontent.com/open-telemetry/semantic-conventions/main/model/gen-ai/registry.yaml)

OpenTelemetry GenAI spans define client inference spans, embeddings spans, retrieval spans, remote
and internal agent invocation spans, internal tool execution spans, and workflow invocation spans;
prompt, input-message, output-message, retrieval-query, tool-argument, and tool-result attributes
are opt-in or marked sensitive. [Source: OpenTelemetry GenAI spans](https://raw.githubusercontent.com/open-telemetry/semantic-conventions/main/model/gen-ai/spans.yaml)

OpenTelemetry GenAI metrics define histograms for token usage, operation duration, time to first
chunk, and time per output chunk. [Source: OpenTelemetry GenAI metrics](https://raw.githubusercontent.com/open-telemetry/semantic-conventions/main/model/gen-ai/metrics.yaml)

MLflow Tracing is OpenTelemetry-compatible, supports GenAI semantic conventions, traces LLM and
agent intermediate steps, and exposes latency and token usage at each step. [Source: MLflow
Tracing](https://mlflow.org/docs/latest/genai/tracing)

Google ADK tracing implements OpenTelemetry GenAI semantic conventions, emits OTLP, and organizes an
agent run as a root span with child spans for LLM operations and tool executions. [Source: Google
ADK traces](https://adk.dev/observability/traces/)

OpenAI Agents SDK tracing records model calls, tool calls, handoffs, guardrails, and custom spans,
and the OpenAI docs recommend using traces before formalizing agent workflow evaluations. [Source:
OpenAI Agents observability](https://developers.openai.com/api/docs/guides/agents/integrations-observability)

Implication: this repo should stay standards-first for span/metric names, but keep raw prompts,
messages, tool arguments, retrieval text, outputs, and provider payloads out of default telemetry.

### 5. State, pause, resume, replay, and human review are runtime concerns.

LangGraph persistence uses checkpointers for thread-scoped state, conversation continuity,
human-in-the-loop workflows, time travel, and fault tolerance; replay from a prior checkpoint skips
already-saved nodes and re-executes later nodes. [Source: LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)

LangGraph interrupts pause graph execution, save state through persistence, and resume through a
`Command`; because execution restarts the node from the beginning, code before an interrupt can run
again. [Source: LangGraph interrupts](https://langchain-ai.github.io/langgraph/concepts/breakpoints/)

OpenAI Agents SDK guardrails validate input, output, or tool behavior automatically, while human
review pauses a run for approval before sensitive actions and resumes the same run from saved state.
[Source: OpenAI guardrails and human review](https://developers.openai.com/api/docs/guides/agents/guardrails-approvals)

Anthropic's Messages API includes `stop_reason` on every successful response; `pause_turn` can occur
when a server-tool sampling loop reaches its iteration limit, and applications should continue the
conversation by sending the assistant response back. [Source: Anthropic stop reasons](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons)

Implication: even for experimentation, the runtime needs explicit event fields for pause, resume,
checkpoint, replay, retry, approval requested, approval accepted/rejected, and node re-entry.

### 6. Tool surfaces are moving targets, and tool cost is part of behavior.

OpenAI's tools guide covers hosted tools, function calling, programmatic tool calling, tool search,
remote MCP servers, and Agents SDK tool wiring; it says the model usually chooses whether to use a
configured tool unless `tool_choice` controls the behavior. [Source: OpenAI tools guide](https://developers.openai.com/api/docs/guides/tools)

Anthropic's tool-use docs distinguish client tools, which return `tool_use` blocks for application
execution, from server tools such as web search, web fetch, code execution, tool search, and MCP
connector tools that run on Anthropic infrastructure. [Source: Anthropic tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)

OpenTelemetry GenAI tool spans require `gen_ai.operation.name` and `gen_ai.tool.name`, recommend tool
call id, description, and type, and make tool arguments and results opt-in because they can contain
sensitive information. [Source: OpenTelemetry GenAI spans](https://raw.githubusercontent.com/open-telemetry/semantic-conventions/main/model/gen-ai/spans.yaml)

Anthropic documents that tool use request cost includes normal input and output tokens, tool
definition/tool-use/tool-result tokens, and additional usage-based charges for some server tools.
[Source: Anthropic tool-use pricing](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)

Implication: experiments should track not only "did it call a tool" but also tool schema version,
tool-choice mode, approval mode, server/client execution location, tool result status, tool latency,
and tool-specific usage/cost.

### 7. Context and cache behavior directly affect repeatability, latency, and cost.

Anthropic prompt caching can cache prompt prefixes with automatic caching or explicit breakpoints,
uses 5-minute or 1-hour TTLs, and is recommended for large context, repeated tasks, long
conversations, and agentic tool use. [Source: Anthropic prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)

Anthropic documents that total input tokens under prompt caching are
`cache_read_input_tokens + cache_creation_input_tokens + input_tokens`, and that `input_tokens` alone
does not represent all input tokens sent when caching is effective. [Source: Anthropic prompt
caching token breakdown](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)

LangSmith cost tracking separates input, output, and other costs, includes subtypes such as cache
reads and reasoning tokens, and can aggregate cost/token data in trace trees, project stats, and
dashboards. [Source: LangSmith cost tracking](https://docs.langchain.com/langsmith/cost-tracking)

Implication: the repo's Provider Usage and Usage Snapshot model should preserve provider-native
usage fields and derived normalized fields, especially cache read/write, reasoning tokens, tool
usage, service tier, and estimated cost.

### 8. LLM-as-judge is useful, but scorer provenance matters.

MLflow GenAI evaluation uses `mlflow.genai.evaluate()` with scorer objects, supports built-in LLM
judges, guidelines judges, custom judges, and code-based scorers, and treats classic MLflow model
evaluation metrics as non-interoperable with GenAI scorers. [Source: MLflow model evaluation](https://mlflow.org/docs/latest/ml/evaluation) [Source: MLflow scorers](https://mlflow.org/docs/latest/genai/eval-monitor/scorers/index.html)

MLflow trace evaluation lets scorers inspect complete traces, including spans, attributes, and
outputs, so they can score tool trajectories, sub-agent routing, and retrieved-document behavior
rather than only final text. [Source: MLflow evaluating traces](https://mlflow.org/docs/latest/genai/eval-monitor/running-evaluation/traces/)

LangSmith's evaluation workflow supports human review, code rules, LLM-as-judge, pairwise
comparison, datasets, experiments, repetitions, concurrency, caching, and production-to-dataset
feedback loops. [Source: LangSmith evaluation](https://docs.langchain.com/langsmith/evaluation)

Microsoft Foundry portal evaluations include task completion, coherence, groundedness, response
completeness, fluency, relevance, and safety evaluators, with recommended evaluator sets differing
by full-conversation and individual-turn scopes. [Source: Microsoft Foundry portal evaluations](https://learn.microsoft.com/azure/foundry/how-to/evaluate-generative-ai-app)

Implication: experiment results should record evaluator id, evaluator type, judge model, rubric or
code scorer version, threshold, score value, score label, explanation, and the trace/span scope that
was evaluated.

### 9. Production-operating patterns are useful, but the repo should import only the experimental core.

Microsoft Foundry trace evaluation can evaluate external agents as long as they emit
OpenTelemetry GenAI spans to Application Insights, and it supports evaluation by trace IDs or by
agent filter. [Source: Microsoft Foundry cloud evaluation](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/cloud-evaluation)

MLflow automatic evaluation can run LLM judges on traces and multi-turn conversations as they are
logged, while offline evaluation uses curated datasets or historical traces. [Source: MLflow
automatic evaluation](https://mlflow.org/docs/latest/genai/eval-monitor/automatic-evaluations/)

LangSmith online evaluation can run evaluators automatically on production runs or threads, while
offline evaluation runs on curated datasets during development. [Source: LangSmith evaluation](https://docs.langchain.com/langsmith/evaluation)

Implication: this repo should not become an always-on production monitoring platform, but it should
produce trace and JSONL artifacts that can be replayed, sampled, scored, and exported to such
platforms.

## Recommendations For This Repo

1. Make repetition and dataset identity mandatory for serious comparisons: add fields for
   `dataset_id`, `dataset_version`, `example_id`, `repetition_index`, `seed` when available,
   `source_revision`, and `evalset_quality_status`.

2. Add path-level result fields: record graph route decisions, node attempts, tool call order, tool
   call outcomes, approval/pause/resume/checkpoint/replay events, and normalized trajectory
   summaries beside final trial outcomes.

3. Standardize GenAI telemetry mapping in one module: map provider responses to OpenTelemetry GenAI
   usage, cache, reasoning, model, service-tier, finish/stop, tool, retrieval, workflow, and
   evaluator attributes without scattering provider-specific logic through graphs.

4. Split telemetry content modes: default mode should emit bounded identifiers, counts, statuses,
   and hashes; local debug mode may include truncated/redacted prompts, tool arguments, tool results,
   retrieval text, and evaluator explanations.

5. Add evaluator provenance to JSONL: each score should include evaluator name, scorer type,
   judge/provider/model, rubric or code version, threshold, score value/label, explanation, and
   evaluated trace/span scope.

6. Add evaluation-data QA: allow trial results to classify failures as `agent_behavior`,
   `runtime_error`, `provider_error`, `tool_error`, `eval_data_defect`, `ambiguous_task`, or
   `infrastructure_flake`.

7. Keep production integrations optional: emit portable OTLP/JSONL artifacts and avoid hard
   dependencies on LangSmith, MLflow, Foundry, or Vertex so the repo remains an experimental runtime.

