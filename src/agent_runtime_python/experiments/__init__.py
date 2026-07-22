"""Public experiment module surface backed by deeper implementation modules."""

from agent_runtime_python.experiments.cli import main
from agent_runtime_python.experiments.planning import (
    OptunaStudyPlanner,
    ParameterSweepPlanner,
    build_trial_plan,
)
from agent_runtime_python.experiments.results import (
    JsonlResultRecorder,
    record_trial_result,
)
from agent_runtime_python.experiments.runner import run_experiment
from agent_runtime_python.experiments.targets import (
    DirectWorkerTarget,
    InternalHttpStreamingTarget,
    TsGatewayTarget,
    create_target,
)
from agent_runtime_python.experiments.types import (
    ExperimentConfig,
    ExperimentTarget,
    JsonScalar,
    OptunaStudyProtocol,
    OptunaTrialProtocol,
    ParameterDistribution,
    ParameterDistributionKind,
    ParameterMatrix,
    RuntimeProfileKind,
    TargetKind,
    TargetRun,
    TrialOutcome,
    TrialPlan,
    TrialPlanner,
    TrialResult,
    UsageSnapshot,
)

__all__ = [
    "DirectWorkerTarget",
    "ExperimentConfig",
    "ExperimentTarget",
    "InternalHttpStreamingTarget",
    "JsonScalar",
    "JsonlResultRecorder",
    "OptunaStudyPlanner",
    "OptunaStudyProtocol",
    "OptunaTrialProtocol",
    "ParameterDistribution",
    "ParameterDistributionKind",
    "ParameterMatrix",
    "ParameterSweepPlanner",
    "RuntimeProfileKind",
    "TargetKind",
    "TargetRun",
    "TrialOutcome",
    "TrialPlan",
    "TrialPlanner",
    "TrialResult",
    "TsGatewayTarget",
    "UsageSnapshot",
    "build_trial_plan",
    "create_target",
    "main",
    "record_trial_result",
    "run_experiment",
]
