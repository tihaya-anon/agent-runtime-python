# Experiment Artifact Storage Architecture, July 2026

Status: research note.

This note answers: for an agent experimentation runtime that needs immutable experiment evidence,
content digests, OpenTelemetry trace/log linkage, and later flexible storage/querying, should the
PGL stack logs/Loki be the experiment record database, or should logs be an index/event stream while
canonical evidence lives in external experiment stores reached through `EvidenceRef` pointers?

Source policy: primary sources only. Sources are official OpenTelemetry, Grafana Loki/Grafana,
Prometheus, MLflow, LangSmith/LangGraph, W&B, OpenLineage, AWS S3, and RFC documentation.

## Repo Context

The current runtime already writes JSONL trial results and emits OpenTelemetry spans for
`experiment.study`, `experiment.trial`, `agent.run`, `agent.graph`, and `agent.graph.node`. Trial
results include trial id, Agent Run id, selected parameters, terminal event, outcome, response
summary, runtime profile and behavior version data, and provider usage when present. [Source: repo
runtime usage](../agents/runtime-usage.md) [Source: repo results
module](../../src/agent_runtime_python/experiments/results.py) [Source: repo telemetry
spans](../../src/agent_runtime_python/observability/telemetry/spans.py)

The current design discussion considered logical artifact identity fields such as `artifactId`,
`artifactType`, `artifactSchemaVersion`, `contentDigest`, `studyId`, `behaviorVersionId`,
`datasetId`, `createdAt`, and `storageUri`, then refined that direction into a narrower
`EvidenceRef`/`EvidenceSink` contract. The runtime should carry evidence pointers and policy, not
own a full experiment artifact database. [Source: repo
handoff](../handoffs/2026-07-23-agent-experimentation-runtime.md) [Source: repo ADR
0005](../adr/0005-use-evidence-sink-adapters-for-experiment-evidence.md)

## Recommendation

Do not make Loki/PGL logs the canonical experiment record database.

Use this split instead:

```text
Canonical evidence:
  External experiment stores or opt-in local EvidenceSink adapters
  - MLflow/Phoenix/LangSmith/Langfuse/W&B/local files/object storage
  - digest when the adapter can provide or compute one
  - URI points to the concrete evidence location

Discovery and observability:
  OpenTelemetry traces/logs/metrics
  - emit evidence pointer metadata
  - carry EvidenceRef URI/digest/role plus studyId, trialId, exampleId, repetitionIndex
  - link logs and traces through traceId/spanId
  - feed Grafana dashboards and drilldowns

Analysis/querying:
  External experiment trackers or derived summaries
  - generated from evidence pointers and recorded trial facts
  - can later move to SQLite/Postgres/DuckDB/object-store manifests/search systems
```

The v1 runtime shape should be an evidence pointer seam, not a general query database:
`EvidenceSink.record(...) -> EvidenceRef`. Flexible querying should remain the responsibility of
external experiment trackers or later derived indexes after the evidence roles and report reducers
are stable.

## Why Logs Should Not Be Canonical

OpenTelemetry logs are a telemetry signal designed to represent logs and events from first-party,
third-party, and system sources; the data model includes timestamps, body, attributes, severity, and
optional trace context fields such as `TraceId` and `SpanId`. That makes logs good for correlated
events, not a purpose-built immutable object database. [Source: OpenTelemetry Logs Data
Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)

OpenTelemetry traces model work as spans with attributes, timestamped events, status, and links to
other spans; span links may point to spans in the same or different trace. That is a good fit for
connecting Monte Carlo repetitions, dataset/example runs, and artifact-created events without
packing all experiment facts into one trace or one log line. [Source: OpenTelemetry Tracing
API](https://opentelemetry.io/docs/specs/otel/trace/api/)

Grafana Loki is explicitly optimized around indexing labels and storing log entries in compressed
chunks. Its index is a table of contents for label sets; the chunk is the container for log entries.
[Source: Loki architecture](https://grafana.com/docs/loki/latest/get-started/architecture/)

Loki's storage docs state that Loki indexes only log metadata labels, while log data itself is
compressed and stored in chunks. This is cost-effective for log aggregation, but it is the wrong
primary contract for exact artifact retrieval, digest verification, and schema migration. [Source:
Loki storage](https://grafana.com/docs/loki/latest/configure/storage/)

Loki label guidance warns that high-cardinality labels create many streams, a huge index, tiny
chunks, and poor performance. Artifact IDs, trial IDs, trace IDs, example IDs, and content digests
are naturally high-cardinality, so they should not be primary Loki stream labels. [Source: Loki
labels](https://grafana.com/docs/loki/latest/get-started/labels/)

Loki structured metadata is metadata attached to log lines without being indexed as labels, and
Grafana documents it as a place for high-cardinality metadata that should be available at query
time. That is the right place for artifact IDs and digests if they need to be visible in Loki.
[Source: Loki structured metadata](https://grafana.com/docs/loki/latest/get-started/labels/structured-metadata/)

Grafana's trace-to-logs documentation gives the same warning for trace IDs and span IDs: use
low-cardinality labels for source dimensions and store high-cardinality values as structured
metadata or query pipeline fields. This supports using logs for drilldown, but not as the canonical
artifact index. [Source: Grafana trace-to-logs correlation](https://grafana.com/docs/grafana/latest/datasources/tempo/configure-tempo-data-source/configure-trace-to-logs/)

Loki retention is operationally allowed to remove old log chunks and index entries, and Loki also
supports targeted deletion. Canonical experiment records need explicit retention/immutability
semantics controlled by the experiment system, not by the logging stack's operational retention
policy. [Source: Loki log retention](https://grafana.com/docs/loki/latest/operations/storage/retention/)
[Source: Loki log entry deletion](https://grafana.com/docs/loki/latest/operations/storage/logs-deletion/)

Prometheus is even less suitable as a record store: its data model is time series samples identified
by metric name and labels, and label changes create new time series. Prometheus should hold aggregate
trial metrics, not per-trial JSON records. [Source: Prometheus data
model](https://prometheus.io/docs/concepts/data_model/)

## What Logs Are Good For

Logs should record artifact lifecycle events and human/operator context:

```json
{
  "event.name": "experiment.artifact.created",
  "artifact.id": "art_...",
  "artifact.type": "raw_experiment_trial",
  "artifact.schema_version": "1",
  "artifact.digest": "sha256:...",
  "artifact.storage_uri": "file://...",
  "experiment.study_id": "study_...",
  "experiment.trial_id": "trial_...",
  "dataset.id": "dataset_...",
  "dataset.example_id": "example_...",
  "experiment.repetition_index": 3,
  "trace_id": "...",
  "span_id": "..."
}
```

Use Loki labels only for bounded source dimensions such as `service_name`, environment, target, or
artifact type. Put `artifact.id`, digest, trace ID, trial ID, and example ID in structured metadata
or JSON body fields and expose Grafana data links from logs/traces to the EvidenceRef URI. Grafana
supports derived fields that extract values from logs and link to trace backends or other URLs, and
Tempo data source settings support trace-to-logs navigation through shared trace/log identifiers.
[Source: Grafana Loki data source derived fields](https://grafana.com/docs/grafana/latest/datasources/loki/configure-loki-data-source/)
[Source: Grafana Tempo data source correlations](https://grafana.com/docs/grafana/latest/datasources/tempo/configure-tempo-data-source/)

## Prior Art From Experiment Systems

MLflow separates metadata storage from artifact storage. Its backend store records entities such as
run IDs, trace IDs, tags, parameters, metrics, and start/end times, while large artifacts such as
models, images, and data files live in an artifact store. [Source: MLflow backend
store](https://mlflow.org/docs/latest/self-hosting/architecture/backend-store/) [Source: MLflow
artifact store](https://mlflow.org/docs/latest/self-hosting/architecture/artifact-store/)

MLflow Tracking concepts also split run metadata from run artifacts: a run records metadata such as
metrics, parameters, start/end times, and output files. Experiments group runs for a task. [Source:
MLflow Tracking](https://mlflow.org/docs/latest/ml/tracking/)

LangSmith evaluations treat an experiment as results for an application version on a dataset, and
each experiment captures outputs, evaluator scores, and execution traces for every dataset example.
That supports this repo's intended split between per-trial facts, traces, and deterministic reports.
[Source: LangSmith evaluation concepts](https://docs.langchain.com/langsmith/evaluation-concepts)

LangSmith datasets are versioned whenever examples change. That argues for recording dataset ID and
dataset version in each trial artifact rather than depending only on a mutable dataset name. [Source:
LangSmith dataset management](https://docs.langchain.com/langsmith/manage-datasets)

LangGraph checkpoint persistence exposes a storage-style API with `put`, `put_writes`, `get_tuple`,
and `list`, and replay from a checkpoint skips prior saved nodes and re-executes later nodes. That is
separate from observability and reinforces the idea that replayable facts/checkpoints belong in a
runtime store, while traces explain execution. [Source: LangGraph
persistence](https://docs.langchain.com/oss/python/langgraph/persistence)

W&B Artifacts are versioned inputs/outputs of runs; W&B computes an artifact digest over contents
and treats logging the same digest as a no-op. W&B can also track checksums and version information
for external object-store references. This is close to the desired model for experiment artifacts:
stable logical identity plus digest-backed content. [Source: W&B artifact
overview](https://docs.wandb.ai/models/artifacts) [Source: W&B Artifact API](https://docs.wandb.ai/models/ref/python/experiments/artifact)

DVC's data versioning model uses file hashes and a cache to identify stored data objects. That is
the same broad pattern needed here: content identity should be digest-backed while physical location
is a backend concern. [Source: DVC internal files and
cache](https://dvc.org/doc/user-guide/project-structure/internal-files)

OpenLineage uses run events to represent job lifecycle transitions, and datasets as named inputs and
outputs with extensible facets. Its custom facet schema URLs are expected to be immutable pointers,
for example a tag or git SHA, not a branch name. That supports using event streams for lineage and
provenance while keeping versioned schemas and datasets explicit. [Source: OpenLineage
spec](https://github.com/OpenLineage/OpenLineage/blob/main/spec/OpenLineage.md)

## Artifact Format And Digest

Use JSON as the stored artifact format. For `contentDigest`, use a deterministic canonical JSON byte
representation rather than pretty JSON or YAML. RFC 8785 defines JSON Canonicalization Scheme for
hashable JSON, using the I-JSON subset, deterministic property sorting, and no emitted whitespace.
[Source: RFC 8785](https://datatracker.ietf.org/doc/html/rfc8785)

The runtime does not need to expose RFC 8785 as a public dependency decision in the first patch, but
the contract should be compatible with it:

```text
contentDigest = "sha256:" + sha256(canonical_json_bytes)
```

Human readability should come from Grafana dashboards, trace/log drilldown, CLI pretty-printers, and
candidate reports, not from making the canonical record YAML.

## Evidence Sink Options

For v1, use one of these concrete adapters behind the same `EvidenceSink` interface:

- Noop sink for default runtime behavior.
- Local file sink as an opt-in development fallback.
- External tracker sinks later, such as MLflow, Phoenix, LangSmith, Langfuse, W&B, or object storage.

The logical contract should not depend on any directory or vendor shape:

```text
EvidenceRef.role
EvidenceRef.uri
EvidenceRef.digest
EvidenceRef.mediaType
EvidenceRef.schemaVersion
```

If stronger physical immutability is needed later, S3 Object Lock can prevent object versions from
being deleted or overwritten for a retention period or indefinitely using WORM semantics. [Source:
Amazon S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)

## Recommended V1 Contract For This Repo

Define evidence references as pointers, not database rows:

```text
role = trial_summary | prompt_bundle | tool_payload | provider_response | ...
uri = backend-specific evidence location
digest = optional, but required when the adapter can compute it
mediaType = content type
schemaVersion = evidence payload schema
```

Minimum identity fields:

```text
studyId
trialId
trialGroupId
repetitionIndex
datasetId
datasetVersion
exampleId
behaviorVersionId
sourceRevision
runnerVersion
traceId
spanIds
```

Minimum fact fields:

```text
input/ref digests or payload refs
final output/ref digest or payload ref
compact semantic trajectory
provider usage
latency
evaluator results
failure classification
warnings/data quality flags
```

Keep OTEL spans/logs as correlation surfaces. Attach bounded EvidenceRef pointer fields to the
active `experiment.trial` span or structured log event, and keep raw prompts, tool payloads, and
provider responses out of telemetry.

## Later Querying Path

When pointer lookup is no longer enough, add query capability in an external tracker or derived
index, not by changing the runtime evidence pointer contract:

1. Start with a generated manifest or SQLite index over artifact metadata.
2. Add deterministic summary artifacts for study-level aggregates.
3. Add DuckDB/Parquet or Postgres if local analysis or multi-user querying becomes important.
4. Keep Loki/Prometheus/Grafana for observability: timelines, drilldown, dashboards, and links.

This keeps storage replaceable: local files today, MLflow/Phoenix/LangSmith tomorrow, database
indexing later, without changing the runtime EvidenceRef schema or deterministic report reducer
contract.

PGL should answer "what happened, when, and where do I click next?" EvidenceRef should answer
"where is the external evidence, what role does it play, and can its digest be checked?"

## Decision

For `agent-runtime-python`, implement `EvidenceSink`/`EvidenceRef` as the runtime-owned seam and
treat PGL logs as evidence pointer observability, not as the experiment database. Do not rely on
Loki retention, cardinality, parsing, or LogQL behavior for correctness-critical experiment records;
use mature experiment platforms or explicit sink adapters for canonical evidence storage.
