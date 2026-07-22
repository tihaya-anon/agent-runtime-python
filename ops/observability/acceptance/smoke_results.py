"""Trial-result parsing and printable dashboard values."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from smoke_commands import ObservabilitySmokeError


@dataclass(frozen=True)
class TrialIdentity:
    study_id: str
    trial_id: str
    agent_run_id: str


def read_trial_identities(path: Path, study_id: str) -> list[TrialIdentity]:
    identities = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        trial_id = record.get("trialId")
        agent_run_id = record.get("agentRunId")
        if not isinstance(trial_id, str) or not isinstance(agent_run_id, str):
            raise ObservabilitySmokeError(f"Invalid trial result record: {line}")
        identities.append(
            TrialIdentity(
                study_id=study_id,
                trial_id=trial_id,
                agent_run_id=agent_run_id,
            )
        )

    return identities


def print_dashboard_values(
    success_identities: list[TrialIdentity],
    failure_identity: TrialIdentity,
) -> None:
    first = success_identities[0]
    print("\nDashboard variable values:")
    print(f"study_id={first.study_id}")
    print(f"trial_id={first.trial_id}")
    print(f"agent_run_id={first.agent_run_id}")
    print(f"failed_agent_run_id={failure_identity.agent_run_id}")
    print(f"failed_study_id={failure_identity.study_id}")
    print("\nAll generated trials:")
    for identity in success_identities:
        print(f"- trial_id={identity.trial_id} agent_run_id={identity.agent_run_id}")
    print(
        "- "
        f"trial_id={failure_identity.trial_id} "
        f"agent_run_id={failure_identity.agent_run_id} "
        "outcome=failed"
    )
