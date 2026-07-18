from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from apps.backend.app.infrastructure.environment import DotEnvError, load_dotenv_file


class EnvironmentFileTests(unittest.TestCase):
    def test_loads_values_without_overriding_process_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / ".env"
            path.write_text(
                "MIMO_API_KEY=local-secret\n"
                'MIMO_MODEL="mimo-v2.5"\n'
                "VIDEO_EMOTION_ENABLED=true # local opt-in\n",
                encoding="utf-8",
            )
            environment = {"MIMO_API_KEY": "process-secret"}

            self.assertTrue(load_dotenv_file(path, environment=environment))

            self.assertEqual(environment["MIMO_API_KEY"], "process-secret")
            self.assertEqual(environment["MIMO_MODEL"], "mimo-v2.5")
            self.assertEqual(environment["VIDEO_EMOTION_ENABLED"], "true")

    def test_rejects_shell_syntax_instead_of_evaluating_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / ".env"
            path.write_text("MIMO-API-KEY=$(unsafe)\n", encoding="utf-8")

            with self.assertRaises(DotEnvError):
                load_dotenv_file(path, environment={})

    def test_optional_missing_file_is_a_noop(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / ".env"
            self.assertFalse(load_dotenv_file(path, environment={}, required=False))


if __name__ == "__main__":
    unittest.main()
