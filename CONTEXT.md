# Agent Runtime

This context describes the language of agent development experiments run through the Python agent runtime.

## Language

**Development Trial**:
A single experimental attempt to run an agent behavior under a controlled target, parameter set, runtime profile, and source revision.
_Avoid_: Test run, experiment run

**Trial Budget**:
The optional configured resource limits for a Development Trial, such as token, cost, tool-call, retry, iteration, or checkpoint ceilings. A Development Trial without a Trial Budget is unbudgeted.
_Avoid_: Quota, limit

**Provider Usage**:
The provider-reported consumption for a model call, including input tokens, output tokens, cached input tokens, reasoning tokens, and related billable usage.
_Avoid_: Model stats, usage stats

**Model Usage Breakdown**:
Provider Usage grouped by provider, model, and runtime execution context so one Development Trial can compare usage across different graph nodes or model choices.
_Avoid_: Per-model stats, usage split

**Experiment Metadata**:
Optional metadata carried on a worker command that identifies the Development Trial without becoming part of the user input or runtime profile.
_Avoid_: Run metadata, trial extras

**Usage Snapshot**:
A cumulative point-in-time report of Provider Usage for an Agent Run or Development Trial. In v1, the runtime emits one final Usage Snapshot before the terminal worker event.
_Avoid_: Usage event, token event
