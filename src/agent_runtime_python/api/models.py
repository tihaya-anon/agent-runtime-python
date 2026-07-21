"""Request models for the internal Agent Run runtime API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class AgentRunInput(ApiModel):
    message: str

    @field_validator("message")
    @classmethod
    def require_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be empty")

        return value


class IncompleteAdHocRuns(ApiModel):
    comparable: Literal[False]
    promotable: Literal[False]


class DevelopmentAgentBehaviorPolicy(ApiModel):
    policy: Literal["development"]
    require_complete_dimensions: Literal[False] = Field(
        alias="requireCompleteDimensions"
    )
    reject_unresolved_dimensions: Literal[False] = Field(
        alias="rejectUnresolvedDimensions"
    )
    allow_incomplete_ad_hoc_runs: Literal[True] = Field(
        alias="allowIncompleteAdHocRuns"
    )
    incomplete_ad_hoc_runs: IncompleteAdHocRuns = Field(alias="incompleteAdHocRuns")


class StrictAgentBehaviorPolicy(ApiModel):
    policy: Literal["strict"]
    require_complete_dimensions: Literal[True] = Field(
        alias="requireCompleteDimensions"
    )
    reject_unresolved_dimensions: Literal[True] = Field(
        alias="rejectUnresolvedDimensions"
    )
    allow_incomplete_ad_hoc_runs: Literal[False] = Field(
        alias="allowIncompleteAdHocRuns"
    )


class SourceRevisionPolicy(ApiModel):
    require_clean_for_published_graph_versions: bool = Field(
        alias="requireCleanForPublishedGraphVersions"
    )


class RuntimePolicy(ApiModel):
    agent_behavior_version: (
        StrictAgentBehaviorPolicy | DevelopmentAgentBehaviorPolicy
    ) = Field(alias="agentBehaviorVersion")
    source_revision: SourceRevisionPolicy = Field(alias="sourceRevision")


class RuntimeProfile(ApiModel):
    schema_version: Literal[1] = Field(alias="schemaVersion")
    profile_id: str = Field(alias="profileId")
    runtime_policy: RuntimePolicy = Field(alias="runtimePolicy")


class StartRunCommand(ApiModel):
    version: Literal[1]
    command_type: Literal["run.start"] = Field(alias="type")
    agent_run_id: str = Field(alias="agentRunId")
    input: AgentRunInput
    runtime_profile: RuntimeProfile = Field(alias="runtimeProfile")
    behavior_version: dict[str, str] = Field(alias="behaviorVersion")

    @field_validator("agent_run_id")
    @classmethod
    def require_agent_run_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("agentRunId must not be empty")

        return value

    def to_worker_command(self) -> dict[str, Any]:
        return dict(self.model_dump(by_alias=True))
