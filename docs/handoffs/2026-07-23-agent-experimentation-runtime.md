# Agent Experimentation Runtime Handoff

Date: 2026-07-23

## Purpose

This handoff captures the current design discussion for evolving
`agent-runtime-python` into a better runtime-level agent experimentation
environment. The next session should continue from these decisions rather than
re-open the production/product boundary.

## Current Repo State Observed

- Branch status at the time of discussion: `main...origin/main`.
- Existing runtime surfaces include the NDJSON worker, internal HTTP streaming
  API, experiment runner, JSONL trial results, OpenTelemetry spans, provider
  usage aggregation, Grafana dashboard generation, and observability smoke
  helpers.
- Open issues returned empty from `gh issue list --state open`.
- A research note was created during this session:
  `docs/research/agent-experimentation-challenges-2026-07.md`.

## Confirmed Boundary

`agent-runtime-python` should not own production monitoring or product shape.
Those belong in `../agent-workbench`.

This repo should own runtime-level experiment execution and validation. Its job
is to provide tested agent behavior candidates to the product repository.

## Confirmed Product Of This Repo

The unit of delivery to product should be a complete Behavior Version package,
not an isolated prompt, graph, model, or tool setting.

The important dimensions already align with current repo language:

- `graph`
- `state`
- `action`
- `prompt`
- `tool`
- `model`
- `trialParameter`
- `sourceRevision`

These are treated as deterministic identity for the agent behavior under test.

## Confirmed Evidence Model

Experiment output should have three layers:

1. Deterministic identity: the immutable Behavior Version package.
2. Experiment facts: trial inputs, parameters, environment identity, trajectory,
   usage, evaluator results, failure classification, repetition metadata, and
   source revision.
3. Candidate report: a deterministic aggregation over immutable experiment
   artifacts.

The candidate report must not use an LLM to evaluate or write the release
decision. LLMs may participate inside experiments as agents, critics, reward
models, or scorers, but their outputs must first be recorded as experiment
facts with provenance. The report generator is only a deterministic reducer.

## Confirmed Policy Model

Release candidate reports should be generated from versioned policy files, not
from hard-coded thresholds.

The policy engine belongs in code. Policy thresholds and required breakdowns
should be versioned artifacts so different agent types can use different
release bars.

Example rule dimensions discussed:

- pass rate
- infrastructure flake rate
- eval-data defect rate
- p95 latency
- mean cost
- required breakdowns by dataset, behavior version, failure classification, and
  tool

## Confirmed Artifact Model

Experiment outputs should use a versioned artifact schema. However, the schema
must not assume a filesystem directory layout as the stable interface.

Stable artifact identity should be logical:

- `artifactId`
- `artifactType`
- `artifactSchemaVersion`
- `contentDigest`
- `studyId`
- `behaviorVersionId`
- `datasetId`
- `createdAt`
- `storageUri`

The filesystem can be one storage backend, but future storage may include
compressed bundles, object storage, databases, Elasticsearch-like stores, or
other NoSQL systems.

PGL metadata must be able to connect traces, logs, metrics, and artifacts
through stable keys such as:

- `metadata.experiment.study_id`
- `metadata.experiment.artifact_id`
- `metadata.experiment.artifact_digest`
- `metadata.agent_behavior_version.*`
- `metadata.dataset.id`
- `metadata.dataset.version`

The report generator should query artifacts through an `ArtifactStore` or
`ArtifactRegistry` abstraction rather than reading fixed paths directly.

## Confirmed Immutability Rule

Registered experiment artifacts should be logically immutable and verified by
`contentDigest`.

Derived analysis, summaries, reports, compaction outputs, and storage
migrations should produce new artifacts or new storage locations for the same
digest, not mutate existing logical artifact content.

Suggested artifact lineage:

- `raw_experiment_artifact`: immutable source records.
- `summary_artifact`: derived from raw experiment artifacts.
- `candidate_report_artifact`: derived from raw artifacts, summaries, and a
  policy artifact.
- `compacted_storage_copy`: same logical artifact and digest, different
  storage URI.

## External Research Findings To Use

Do not duplicate the research note. Use:

- `docs/research/agent-experimentation-challenges-2026-07.md`
- `docs/research/agent-dev-trial-observability.md`
- `docs/research/agent-dev-trial-observability-implementation.md`

The main implications are:

- Agent correctness is trajectory correctness, not only answer correctness.
- Repetitions and dataset identity are required for meaningful comparisons.
- Evaluation data can be defective, ambiguous, or contaminated, so eval QA must
  be represented explicitly.
- OpenTelemetry GenAI and provider usage mapping should stay centralized and
  standards-first.
- Production platforms should remain optional consumers of portable OTLP/JSONL
  artifacts.

## Recommended Next Discussion

Continue the grill session from artifact and policy design. The next decisions
that materially affect implementation are:

1. What is the minimal first artifact schema for raw experiment records?
2. Should datasets/examples be first-class repo-managed artifacts, external
   references, or both?
3. What is the first deterministic release policy to implement?
4. What is the first built-in experimental environment beyond the smoke graph:
   tool-use, retrieval, checkpoint/replay, failure injection, or evaluator
   provenance?
5. Where should logical artifact registration live relative to OTEL emission:
   runner-only, telemetry layer, or a separate observability/artifacts module?

## Suggested Skills For Next Session

- `grill-me`: continue one-question-at-a-time decision pressure.
- `domain-modeling`: update `CONTEXT.md` once artifact/report/policy terms are
  finalized.
- `codebase-design`: design `ArtifactStore`, artifact schema, and report
  reducer boundaries.
- `tdd`: implement the first schema and deterministic report reducer
  test-first.
- `conventional-commits`: use when committing the eventual implementation.
