# Agent Experimentation Prior Art, July 2026

Status: research note.

Question: has this repo's need already been solved elsewhere? Scope: LangGraph/LangSmith tracing and
evaluation; LLM/agent observability and evaluation platforms; pre-LLM ML experiment tracking,
ablation, sweeps, artifacts, and comparison systems.

Source policy: primary sources only. Sources are official docs, specifications, first-party API
references, source repos, and project-author docs when official docs are the canonical reference.

## Short Answer

The need is partially solved, but not in the exact shape this repo needs.

Modern agent platforms already solve large pieces:

- LangSmith and LangGraph provide integrated tracing, trace inspection, graph/node-oriented Studio
  workflows, datasets, offline/online evals, experiment comparison, and OpenTelemetry ingestion/export
  paths.
- Phoenix/OpenInference, Langfuse, MLflow GenAI, and W&B Weave all converge on the same model:
  instrument application runs as traces, evaluate against datasets/examples, store per-example
  scores, and compare experiment runs.
- Pre-LLM ML tools already solved the older part of this problem: runs/trials, params, metrics,
  artifacts, sweep/search spaces, checkpoints, storage backends, and reproducibility metadata.

But those systems are either hosted product surfaces, broad experiment trackers, or framework-specific
observability layers. This repo still has a useful reason to build a small runtime-owned core:

```text
runtime trace ownership:
  emit OTEL traces/spans/events from the runtime itself

evidence linkage:
  EvidenceRef pointers from runtime facts to external evidence stores

portable evidence sinks:
  local files, MLflow, Phoenix, LangSmith, Langfuse, W&B, or object storage adapters

deterministic report reducers:
  compare behavior versions from recorded facts and versioned policy

optional integrations:
  export to LangSmith/Phoenix/Grafana/MLflow/W&B rather than require them
```

## LangGraph And LangSmith

LangSmith observability concepts define traces as collections of runs for a single operation, and
runs as span-like units of work such as LLM calls, prompt formatting, retrieval, or arbitrary
application work. It supports tags and metadata for filtering, and says integrations can
automatically trace supported frameworks including LangChain and LangGraph. It also states LangSmith
SaaS trace retention semantics and that datasets persist beyond trace retention. [Source:
LangSmith observability concepts](https://docs.langchain.com/langsmith/observability-concepts)

LangSmith's LangChain tracing docs say no extra code is needed to trace LangChain after enabling the
environment variables, and that LangChain objects invoked inside LangSmith `traceable` functions
become child runs. This is close to what this repo wants from "runtime-owned traces": parent/child
execution structure, explicit metadata, and framework interop. [Source: LangSmith trace LangChain
apps](https://docs.langchain.com/langsmith/trace-with-langchain)

LangSmith also supports OpenTelemetry tracing. Its OTEL guide says LangChain/LangGraph applications
can enable `LANGSMITH_OTEL_ENABLED`, that traces may be sent to alternate OTLP destinations, and that
LangSmith maps OpenTelemetry, GenAI, TraceLoop, and OpenInference attributes/events into LangSmith
runs. This is strong evidence that this repo should stay OTEL-compatible and avoid inventing a
private trace schema. [Source: LangSmith trace with OpenTelemetry](https://docs.langchain.com/langsmith/trace-with-opentelemetry)

LangSmith evaluation concepts match the repo's target workflow: offline evaluations run on datasets
with reference outputs for benchmarking/regression/backtesting, while online evaluations run on
production traces. Evaluator inputs include the dataset example and the run with intermediate steps;
evaluators return named feedback scores or values. The docs explicitly mention agent trajectory and
tool selection as evaluation targets. [Source: LangSmith evaluation
concepts](https://docs.langchain.com/langsmith/evaluation-concepts)

LangSmith Studio connects traces, datasets, prompts, and graph nodes. It can run experiments over a
dataset, debug traces, import traced runs into Studio, and add parts of thread history to a dataset.
For deployed LangGraph agents, usage billing separately counts deployment runs and LangGraph node
executions, which confirms that node-level graph execution is a first-class product concern. [Source:
LangSmith Studio observability](https://docs.langchain.com/langsmith/observability-studio) [Source:
LangSmith usage](https://docs.langchain.com/langsmith/view-usage)

LangGraph streaming exposes low-level graph execution modes such as `updates`, `values`, `messages`,
`custom`, `checkpoints`, `tasks`, and `debug`; the newer event streaming layer projects the same
underlying event flow into typed streams for messages, values, subgraphs, interrupts, output, and
custom extensions. This is important for complex graphs: LangGraph can produce semantic execution
events, but Tempo-style trace visualization is still a trace/span tree, not a complete graph topology
renderer by itself. [Source: LangGraph streaming](https://docs.langchain.com/oss/python/langgraph/streaming)
[Source: LangGraph event streaming](https://docs.langchain.com/oss/python/langgraph/event-streaming)

LangGraph persistence and time travel are separate from observability. Time travel works through
checkpoints; replay resumes from a prior checkpoint, skips nodes before it, and re-executes later
nodes. This supports a key architectural distinction for this repo: traces explain what happened;
checkpoints/artifacts preserve replayable or comparable facts. [Source: LangGraph time
travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel)

## Agent Observability And Evaluation Platforms

Phoenix describes itself as an AI observability and evaluation platform built on OpenTelemetry and
OpenInference. Its stated capabilities include traces for model calls, retrieval, tool use, and
custom logic; evaluations on traces and spans; prompt versions; datasets; and experiments that
compare changes on the same inputs. [Source: Phoenix overview](https://arize.com/docs/phoenix)

Phoenix experiments are especially close to this repo's current design. The SDK model is: define or
upload a dataset, define a task that runs on each example, configure evaluators, and run an
experiment. The client API supports `dataset_id`, `dataset_version_id`, dataset splits,
`repetitions`, task runs, evaluation runs, and later evaluator attachment. This is direct prior art
for first-class `datasetId`, `datasetVersionId`, `exampleId`, and `repetitionIndex`. [Source:
Phoenix experiments how-to](https://arizeai-433a7140.mintlify.app/docs/phoenix/datasets-and-experiments/how-to-experiments)
[Source: Phoenix experiments API](https://arize-phoenix.readthedocs.io/projects/client/api/experiments.html)

OpenInference is a vendor-neutral semantic convention layer over OpenTelemetry for AI/ML traces. It
requires `openinference.span.kind` and defines span kinds such as `LLM`, `CHAIN`, `AGENT`,
`RETRIEVER`, `TOOL`, `EVALUATOR`, and `PROMPT`, plus standardized input/output, message, document,
token, cost, and metadata attributes. Phoenix and OpenInference instrumentation can export to any
OTEL-compatible collector. [Source: OpenInference semantic
conventions](https://arize-ai.github.io/openinference/spec/semantic_conventions.html) [Source:
OpenInference repo](https://github.com/Arize-ai/openinference)

Langfuse has nearly the same conceptual model. Its experiment data model includes `Dataset`,
`DatasetItem`, `DatasetRun`, and `DatasetRunItem`. A dataset item has input, expected output,
metadata, and optional source trace/observation links. A dataset run item links a dataset item to a
trace ID. Scores attach evaluation results to traces, observations, sessions, or dataset runs. [Source:
Langfuse experiment data model](https://langfuse.com/docs/evaluation/experiments/data-model)
[Source: Langfuse scores](https://langfuse.com/docs/evaluation/scores/overview)

Langfuse datasets support versioning, including running experiments on a dataset at a specific
version timestamp for reproducibility. Prompt experiments can compare prompt versions or models over
a dataset and optionally apply LLM-as-judge or code evaluators. [Source: Langfuse
datasets](https://langfuse.com/docs/evaluation/experiments/datasets) [Source: Langfuse experiments
via UI](https://langfuse.com/docs/evaluation/experiments/experiments-via-ui)

MLflow GenAI has converged toward traces plus evaluation datasets. MLflow tracing is described as
OpenTelemetry-compatible and captures inputs, outputs, metadata, intermediate steps, latency, and
token usage. `mlflow.genai.evaluate` can evaluate existing traces or input/output/expectation data,
and agent scorers include plan quality and tool calling. MLflow evaluation datasets require a SQL
backend and are meant for golden sets, regression tests, app-version comparison, and production
trace-derived examples. [Source: MLflow GenAI tracing](https://mlflow.org/docs/latest/genai/tracing)
[Source: MLflow GenAI API](https://mlflow.org/docs/latest/api_reference/python_api/mlflow.genai.html)
[Source: MLflow evaluation datasets](https://mlflow.org/docs/latest/genai/datasets/)

W&B Weave defines Ops, Calls, and Traces. An Op is a versioned tracked function; a Call is an
execution of an Op that captures input arguments, output, timing/latency, parent-child relationships,
and errors. Weave evaluations define a dataset, one or more scorers, and a model/function to
evaluate; each evaluation captures traces of predictions and scores. [Source: Weave tracing](https://docs.wandb.ai/weave/guides/tracking/tracing)
[Source: Weave evaluations](https://docs.wandb.ai/weave/guides/core-types/evaluations)

Weave also supports no-code and code-driven comparison workflows: evaluation playgrounds compare
multiple models/prompts on the same dataset, and evaluation logging supports comparing multiple
evaluations by metric and per-example outputs. [Source: Weave evaluation
playground](https://docs.wandb.ai/weave/guides/tools/evaluation_playground) [Source: Weave
evaluation logger](https://docs.wandb.ai/weave/guides/evaluation/evaluation_logger)

## Pre-LLM ML Experiment Tracking Prior Art

MLflow Tracking is the canonical older pattern: an experiment groups runs; each run records metadata
such as params, metrics, start/end times, and artifacts such as output files. MLflow's architecture
separates a backend store for run metadata from artifact storage for large files. [Source: MLflow
Tracking](https://mlflow.org/docs/latest/ml/tracking/) [Source: MLflow CLI/artifact and server
options](https://mlflow.org/docs/latest/api_reference/cli.html)

W&B uses a run as a single unit of computation with a unique run ID, config, metrics, artifacts, and
project membership. W&B Sweeps automate hyperparameter search with Bayesian, grid, and random
strategies. W&B Artifacts version datasets, models, and other inputs/outputs of runs; artifacts can
represent model evaluation outputs such as tables. [Source: W&B runs](https://docs.wandb.ai/models/runs)
[Source: W&B sweeps](https://docs.wandb.ai/models/sweeps) [Source: W&B artifacts](https://docs.wandb.ai/models/artifacts)

Optuna's `Study` corresponds to an optimization task and is a set of trials. A `Trial` suggests
params, reports values, can carry user attributes, and can be exported through study trial history.
Optuna also has an experimental artifact module with a filesystem artifact store and `upload_artifact`
for per-trial output files. [Source: Optuna Study](https://optuna.readthedocs.io/en/stable/reference/generated/optuna.study.Study.html)
[Source: Optuna user attributes](https://optuna.readthedocs.io/en/stable/tutorial/20_recipes/003_attributes.html)
[Source: Optuna artifacts](https://optuna.readthedocs.io/en/v3.6.2/reference/artifacts.html)

Ray Tune's key concepts are search space, trainable objective, search algorithm, scheduler, Tuner,
trials, and result grid. It persists experiment-level state, trial checkpoints, and trial results;
trial results are saved in CSV, JSON, or TensorBoard formats. Storage can be local filesystem,
network filesystem, or object storage, with cloud/NFS needed for robust distributed runs. [Source:
Ray Tune key concepts](https://docs.ray.io/en/latest/tune/key-concepts.html) [Source: Ray Tune
storage](https://docs.ray.io/en/latest/tune/tutorials/tune-storage.html) [Source: Ray Tune trial
checkpoints](https://docs.ray.io/en/master/tune/tutorials/tune-trial-checkpoints.html)

Sacred's `Experiment` and `Run` model is older but still highly relevant. A Sacred run collects start
and stop times, configuration, result/errors, host and package info, local source files, opened
resources, and added artifacts. Observers receive start, heartbeat, artifact/resource, completed,
interrupted, and failed events; built-in observers include MongoDB, local file storage, and TinyDB.
This is a strong precedent for separating runtime events from stored experiment facts. [Source:
Sacred experiment overview](https://sacred.readthedocs.io/en/latest/experiment.html) [Source: Sacred
observers](https://sacred.readthedocs.io/en/latest/observers.html) [Source: Sacred API](https://sacred.readthedocs.io/en/latest/apidoc.html)

ClearML centers experiment management on a `Task`, a single execution session that captures source
code, Git info, uncommitted patches, Python environment, configuration, hyperparameters, console
output, scalars, plots, debug samples, models, and artifacts. Tasks can be cloned and executed by
agents with modified parameters. [Source: ClearML tasks](https://clear.ml/docs/latest/docs/fundamentals/task/)

DVC gives the content-addressed storage lesson. DVC data versioning uses metadata pointers in Git
while actual data lives in a cache, with files identified by content hash. DVC experiments use
Git-based refs to track lightweight experiment variants and compare params/metrics without
requiring a central database. [Source: DVC data versioning](https://dvc.org/doc/start/data-management/data-versioning)
[Source: DVC experiment refs](https://dvc.org/blog/experiment-refs/)

Aim's `Run` object tracks and stores ML training metadata such as metrics and hyperparameters in a
local `.aim` repository by default. Runs have hashes, can be grouped under experiments, can capture
terminal logs and system metrics, and can log system params such as installed packages and Git info.
[Source: Aim manage runs](https://aimstack.readthedocs.io/en/latest/using/manage_runs.html) [Source:
Aim configure runs](https://aimstack.readthedocs.io/en/latest/using/configure_runs.html)

Neptune defines a run as the basic unit of a model-training experiment, containing configs, metrics,
predictions, and scores. It distinguishes experiments as lineages of runs with the same name, where
forking can retain metric history. Note: Neptune's current docs also announce service shutdown on
March 5, 2026 after acquisition, so it is useful as prior art, not as an integration target. [Source:
Neptune runs](https://docs.neptune.ai/runs) [Source: Neptune docs home](https://docs.neptune.ai/)

Kubeflow Katib models hyperparameter tuning through Kubernetes CRDs. An Experiment defines objective
metrics, search algorithm, parallel and max trial counts, failed-trial limits, parameter search
space, and a trial template. The controller lifecycle creates Suggestions and Trials, injects metric
collectors, persists metrics to the Katib DB backend, and updates optimal-trial status. [Source:
Katib configure experiment](https://www.kubeflow.org/docs/components/katib/user-guides/hp-tuning/configure-experiment/)
[Source: Katib lifecycle](https://www.kubeflow.org/docs/components/katib/reference/experiment-cr/)

## What This Means For This Repo

### Do not make Grafana/Tempo/Loki the experiment database

The prior-art pattern is consistent: observability captures execution and supports drilldown, while
experiment systems still keep first-class runs/trials/artifacts/datasets/evaluations. LangSmith,
Phoenix, Langfuse, MLflow GenAI, and Weave all link traces to evaluation records rather than treating
generic trace storage as the only source of truth.

For this repo, PGL should stay an observability surface:

```text
Tempo:
  trace/span tree, latency, errors, parent/child execution structure

Loki:
  logs and artifact lifecycle events

Grafana:
  dashboards and drilldowns

EvidenceSink adapters:
  canonical evidence lives in external stores or opt-in local files
```

### Keep OTEL as the runtime trace spine

LangSmith OTEL, OpenInference, Phoenix, and MLflow GenAI all point in the same direction:
standardized spans/attributes are the interoperability layer. This repo should continue runtime-owned
OTEL spans for `experiment.study`, `experiment.trial`, `agent.run`, `agent.graph`,
`agent.graph.node`, and provider calls, then extend only bounded fields:

```text
dataset.id
dataset.version
dataset.example_id
experiment.repetition_index
experiment.artifact_id
experiment.artifact_digest
experiment.trial_group_id
agent_behavior_version.*
```

Use OpenTelemetry GenAI attributes where stable and map to OpenInference-compatible names where it
helps downstream tools.

### Treat one trial repetition as the atomic experiment record

Phoenix's `repetitions`, Langfuse's dataset run items, Optuna's trials, Ray Tune's trial results,
and W&B/MLflow runs all reinforce the same modeling rule: comparison requires an atomic execution
unit. For this repo, the unit should be:

```text
one behavior version
one dataset example
one trial parameter set
one repetition
= one immutable raw trial artifact
```

Monte Carlo runs should be multiple artifacts linked by `trialGroupId`/trace links/shared
study/example/behavior metadata, not one large mutable aggregate.

### Separate datasets/examples from traces

LangSmith, Phoenix, Langfuse, and MLflow all distinguish datasets/examples from traces/runs. This
repo should do the same. A trace may be promoted into a dataset example, but the dataset/example
identity used for a regression run must be explicit and versioned.

Minimum future fields:

```text
datasetId
datasetVersionId or datasetDigest
exampleId
exampleVersionId or exampleDigest
split
```

### Build a tiny local core first; integrate later

Because Phoenix/Langfuse/LangSmith/MLflow/W&B already exist, this repo should not compete with them
as a UI product. The valuable local core is much smaller:

```text
EvidenceSink:
  record(evidence) -> EvidenceRef pointer

Trace linkage:
  emit evidence pointer metadata with trace/span ids and URI/digest

Report reducer:
  deterministic aggregation over recorded facts, EvidenceRefs, and policy evidence

Export adapters:
  optional later: LangSmith/Phoenix/Langfuse/MLflow/W&B
```

### Do not overbuild search/indexing in v1

MLflow, W&B, Aim, ClearML, Neptune, Phoenix, and Langfuse all provide rich search/query UIs, but
that is product surface area. The repo's v1 can stay local and narrow if it records enough metadata
inside the artifact and logs artifact lifecycle events. Add derived indexes later once report needs
are proven.

Recommended v1 backend:

```text
local filesystem
canonical JSON artifacts
content digest over canonical bytes
id lookup only
OTEL/log event for artifact creation
```

### Do not rely on LLM judges for release decisions

LangSmith, Phoenix, Langfuse, MLflow GenAI, and Weave all support LLM-as-judge. That is useful as an
evaluator inside experiments, but release decisions should still be deterministic reducers over
recorded facts and versioned policy. LLM judge outputs should be treated as evaluator facts with
model/prompt/provider provenance.

## Build Vs Integrate

Recommended position:

1. Build the local runtime-owned core.
2. Keep the trace schema OTEL/OpenInference-compatible.
3. Export or mirror later to LangSmith/Phoenix/Langfuse/MLflow/W&B if a user wants those UIs.
4. Do not make any hosted platform mandatory for the runtime.

This preserves the repo's identity as a portable experimentation runtime while leaving a clear path
to adopt stronger product surfaces later.

## Open Questions For Design

- Should this repo adopt OpenInference attribute names directly for agent/tool/retriever/evaluator
  spans, or continue its current `metadata.*` names and add an export mapping?
- Should dataset/example artifacts be first-class in v1, or should v1 only record external dataset
  references and digests?
- Should the first concrete `EvidenceSink` adapter be local files, MLflow, Phoenix, or LangSmith?
- Should Phoenix or LangSmith be the first optional integration target, given they already model
  repetitions, datasets, traces, and experiments?
