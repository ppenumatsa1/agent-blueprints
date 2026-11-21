import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class VerificationWorkflowTests(unittest.TestCase):
    def test_generated_verifier_step_propagates_failures_and_rejects_skips(self):
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("Bash is required to exercise the GitHub Actions step.")

        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        marker = "      - name: Run generated contracts and golden acceptance without skips\n"
        step = workflow.split(marker, 1)[1].split("      - name:", 1)[0]
        self.assertTrue(step.startswith("        run: |\n"))
        script = textwrap.dedent(step.split("\n", 1)[1])
        stub = (
            'python() { printf "%s\\n" "$TEST_OUTPUT"; return "$TEST_STATUS"; }\n'
            'uv() {\n'
            '  [[ "$1" == run && "$2" == --locked && "$3" == --project && '
            '"$4" == "$GENERATED_DIR/backend" && "$5" == python ]] || return 99\n'
            '  shift 5\n'
            '  python "$@"\n'
            '}\n'
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "app" / "verification").mkdir(parents=True)
            environment = os.environ.copy()
            environment.update(
                GENERATED_DIR=(root / "app").as_posix(),
                RUNNER_TEMP=root.as_posix(),
            )
            for output, status, expected in (
                ("FAILED (failures=1)", 37, 37),
                ("OK (skipped=1)", 0, 1),
                ("OK (expected failures=1)", 0, 1),
                ("OK", 0, 0),
            ):
                with self.subTest(output=output):
                    environment.update(TEST_OUTPUT=output, TEST_STATUS=str(status))
                    result = subprocess.run(
                        [bash, "-e", "-c", stub + script],
                        env=environment,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode, expected, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
