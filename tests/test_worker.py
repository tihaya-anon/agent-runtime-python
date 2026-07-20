import unittest

from agent_runtime_python import __version__
from agent_runtime_python.worker import main


class WorkerTest(unittest.TestCase):
    def test_package_exposes_version(self) -> None:
        # Given
        version = __version__

        # When
        has_version = bool(version)

        # Then
        self.assertTrue(has_version)

    def test_placeholder_worker_exits_successfully(self) -> None:
        # Given
        expected_exit_code = 0

        # When
        exit_code = main()

        # Then
        self.assertEqual(exit_code, expected_exit_code)


if __name__ == "__main__":
    unittest.main()
