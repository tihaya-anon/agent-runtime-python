import unittest
from collections.abc import Sequence

from agent_runtime_python.experiment import (
    ExperimentConfig,
    JsonScalar,
    OptunaStudyPlanner,
    ParameterDistribution,
    TrialPlanner,
    build_trial_plan,
)
from agent_runtime_python.runtime.protocol import COMMAND_VALIDATOR

from tests.experiment_helpers import COMPLETE_BEHAVIOR_VERSION


class ExperimentPlanningTest(unittest.TestCase):
    def test_build_trial_plan_generates_protocol_compliant_parameter_sweep(
        self,
    ) -> None:
        config = ExperimentConfig(
            message="Explain closures.",
            parameter_matrix={"style": ["concise", "detailed"], "temperature": [0, 1]},
        )

        trials = build_trial_plan(config)

        self.assertEqual(len(trials), 4)
        self.assertEqual(
            [trial.parameters for trial in trials],
            [
                {"style": "concise", "temperature": 0},
                {"style": "concise", "temperature": 1},
                {"style": "detailed", "temperature": 0},
                {"style": "detailed", "temperature": 1},
            ],
        )
        for trial in trials:
            COMMAND_VALIDATOR.validate(trial.command)
            self.assertEqual(trial.command["type"], "run.start")
            self.assertEqual(
                trial.command["runtimeProfile"]["profileId"], "runtime-development"
            )
            self.assertIn("trialParameter", trial.command["behaviorVersion"])
            self.assertIn("Trial parameters:", trial.command["input"]["message"])
            self.assertEqual(
                trial.command["experimentMetadata"],
                {
                    "studyId": config.study_id,
                    "trialId": trial.trial_id,
                    "target": config.target,
                },
            )

    def test_published_trial_requires_complete_behavior_identity(self) -> None:
        config = ExperimentConfig(
            message="Explain closures.",
            parameter_matrix={"style": ["concise"]},
            runtime_profile="published",
            behavior_version={"graph": "graph:python-smoke"},
        )

        with self.assertRaisesRegex(ValueError, "complete behavior identity"):
            build_trial_plan(config)

    def test_comparable_trial_requires_complete_behavior_identity(self) -> None:
        config = ExperimentConfig(
            message="Explain closures.",
            parameter_matrix={"style": ["concise"]},
            comparable=True,
            behavior_version={"graph": "graph:python-smoke"},
        )

        with self.assertRaisesRegex(ValueError, "complete behavior identity"):
            build_trial_plan(config)

    def test_published_trial_accepts_complete_behavior_identity(self) -> None:
        config = ExperimentConfig(
            message="Explain closures.",
            parameter_matrix={"style": ["concise"]},
            runtime_profile="published",
            behavior_version=COMPLETE_BEHAVIOR_VERSION,
        )

        trials = build_trial_plan(config)

        self.assertEqual(len(trials), 1)
        self.assertEqual(
            trials[0].command["runtimeProfile"]["profileId"], "runtime-published"
        )
        COMMAND_VALIDATOR.validate(trials[0].command)

    def test_build_trial_plan_accepts_custom_planner_extension_point(self) -> None:
        class FixedPlanner:
            def parameter_sets(
                self, config: ExperimentConfig
            ) -> Sequence[dict[str, JsonScalar]]:
                _ = config
                return [{"candidate": "optuna-style"}]

        planner: TrialPlanner = FixedPlanner()

        trials = build_trial_plan(
            ExperimentConfig(
                message="Explain closures.",
                parameter_matrix={"ignored": ["matrix"]},
            ),
            planner=planner,
        )

        self.assertEqual(len(trials), 1)
        self.assertEqual(trials[0].parameters, {"candidate": "optuna-style"})

    def test_optuna_study_planner_uses_optuna_trial_suggestions(self) -> None:
        class FakeTrial:
            def suggest_categorical(
                self,
                name: str,
                choices: Sequence[JsonScalar],
            ) -> JsonScalar:
                self.categorical = (name, choices)
                return "detailed"

            def suggest_int(
                self,
                name: str,
                low: int,
                high: int,
                step: int = 1,
                log: bool = False,
            ) -> int:
                self.integer = (name, low, high, step, log)
                return 2

            def suggest_float(
                self,
                name: str,
                low: float,
                high: float,
                step: float | None = None,
                log: bool = False,
            ) -> float:
                self.floating = (name, low, high, step, log)
                return 0.2

        class FakeStudy:
            def __init__(self) -> None:
                self.trials: list[FakeTrial] = []

            def ask(self) -> FakeTrial:
                trial = FakeTrial()
                self.trials.append(trial)
                return trial

        study = FakeStudy()
        planner = OptunaStudyPlanner(
            [
                ParameterDistribution(
                    name="style",
                    kind="categorical",
                    choices=["concise", "detailed"],
                ),
                ParameterDistribution(name="k", kind="int", low=1, high=3),
                ParameterDistribution(
                    name="temperature", kind="float", low=0.0, high=1.0
                ),
            ],
            trial_count=2,
            study=study,
        )

        trials = build_trial_plan(
            ExperimentConfig(message="Explain closures.", parameter_matrix={}),
            planner=planner,
        )

        self.assertEqual(len(trials), 2)
        self.assertEqual(
            trials[0].parameters,
            {"style": "detailed", "k": 2, "temperature": 0.2},
        )
        self.assertEqual(len(study.trials), 2)

    def test_optuna_study_planner_can_generate_local_candidates_without_optuna(
        self,
    ) -> None:
        planner = OptunaStudyPlanner(
            [
                ParameterDistribution(
                    name="style",
                    kind="categorical",
                    choices=["concise", "detailed"],
                ),
                ParameterDistribution(name="k", kind="int", low=1, high=3),
                ParameterDistribution(
                    name="temperature", kind="float", low=0.0, high=1.0
                ),
            ],
            trial_count=3,
        )

        trials = build_trial_plan(
            ExperimentConfig(message="Explain closures.", parameter_matrix={}),
            planner=planner,
        )

        self.assertEqual(
            [trial.parameters for trial in trials],
            [
                {"style": "concise", "k": 1, "temperature": 0.0},
                {"style": "detailed", "k": 2, "temperature": 0.5},
                {"style": "concise", "k": 3, "temperature": 1.0},
            ],
        )


if __name__ == "__main__":
    unittest.main()
