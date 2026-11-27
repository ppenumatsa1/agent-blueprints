"""Real Docker checks. Run explicitly; a missing engine is a failure, not a skip."""

import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "offline_launcher", SCRIPTS / "run_synthetic_manual_test.py"
)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class OfflineIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = runner.build_image(
            os.environ.get("OFFLINE_TEST_PACKAGE_INDEX", "https://pypi.org/simple")
        )

    def test_native_approval_and_rejection_with_runtime_denial_probes(self):
        with patch.dict(
            os.environ,
            {
                "AZURE_CLIENT_SECRET": "synthetic-host-canary",
                "DATABASE_URL": "synthetic-host-canary",
                "BLUEPRINT_APPLICATION": "must.not.import:factory",
            },
        ):
            for decision in ("approved", "rejected"):
                with self.subTest(decision=decision):
                    result = runner.run_test(self.image, decision)
                    self.assertEqual(result["decision"], decision)
                    self.assertEqual(result["isolation_probes"], "passed")
                    self.assertFalse(result["durable"])

    def test_real_capability_changes_are_denied_before_start(self):
        real_docker = runner.docker
        mutations = (
            ("network", lambda args: args.__setitem__(args.index("--network") + 1, "bridge")),
            ("writable", lambda args: args.remove("--read-only")),
            ("root", lambda args: args.__setitem__(args.index("--user") + 1, "0")),
            ("mount", lambda args: args.__setitem__(slice(1, 1), ["--tmpfs", "/tmp"])),
            (
                "credential",
                lambda args: args.__setitem__(
                    slice(1, 1), ["--env", "AZURE_CLIENT_SECRET=synthetic-container-canary"]
                ),
            ),
            ("entrypoint", lambda args: args.__setitem__(slice(1, 1), ["--entrypoint", "/bin/sh"])),
        )
        for name, mutate in mutations:
            calls = []

            def changed_docker(*arguments, **kwargs):
                arguments = list(arguments)
                calls.append(arguments[0])
                if arguments[0] == "create":
                    mutate(arguments)
                return real_docker(*arguments, **kwargs)

            with self.subTest(name=name), patch.object(runner, "docker", changed_docker):
                with self.assertRaises(RuntimeError):
                    runner.run_test(self.image, "approved")
                self.assertNotIn("start", calls)
                self.assertEqual(calls[-1], "rm")

    def test_cli_surface_has_no_code_image_payload_or_endpoint_override(self):
        import subprocess
        import sys

        for option in ("--code", "--image", "--payload", "--docker-host"):
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "run_synthetic_manual_test.py"),
                    option,
                    "synthetic",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
