import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class VerificationWorkflowTests(unittest.TestCase):
    def test_existing_six_jobs_remain_and_browser_is_additive(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        original = (
            "contracts",
            "maf-infrastructure",
            "maf-core",
            "maf-frontend",
            "maf-compose",
            "maf-independent",
        )
        for job in original:
            self.assertEqual(workflow.count(f"  {job}:\n"), 1, job)
        self.assertEqual(workflow.count("  maf-browser:\n"), 1)
        self.assertIn("npm run e2e:local", workflow)
        self.assertIn("python scripts/instantiate_maf.py", workflow)
        self.assertIn("cd ../hosted-agent", workflow)
        self.assertIn("uv pip install --python", workflow)
        self.assertIn("python -m unittest discover -s tests -v", workflow)
        order_resolution_backend = workflow.split(
            "      - name: Run generated Order Resolution API, workflow, database, and UI tests\n",
            1,
        )[1].split("      - name:", 1)[0]
        self.assertIn(
            "uv run --locked python -m unittest discover -s tests -v",
            order_resolution_backend,
        )

    def test_generated_evidence_is_produced_from_the_exact_source_head(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        independent = workflow.split("  maf-independent:\n", 1)[1].split(
            "\n  maf-browser:\n", 1
        )[0]
        self.assertIn(
            "ref: ${{ github.event.pull_request.head.sha || github.sha }}",
            independent,
        )
        self.assertIn(
            'echo "SOURCE_REVISION=$(git rev-parse HEAD)" >> "$GITHUB_ENV"',
            independent,
        )

    def test_cloud_validation_is_manual_exact_revision_and_non_deploying(self):
        workflow = (ROOT / ".github" / "workflows" / "cloud-validation.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("pull_request:", workflow)
        self.assertNotIn("\n  push:", workflow)
        self.assertIn('test "$(git rev-parse HEAD)" = "$SOURCE_REVISION"', workflow)
        self.assertIn("verify_active_revision.py", workflow)
        self.assertIn("verify_app_insights_correlation.py", workflow)
        self.assertIn("capture_foundry_trajectory_evidence.py", workflow)
        self.assertIn("--foundry-evidence", workflow)
        self.assertIn("tests.hosted_failure_runner", workflow)
        self.assertIn("tests.test_order_resolution_real_provider", workflow)
        self.assertIn("npm run e2e:live", workflow)
        self.assertIn("python -m readiness.release", workflow)
        self.assertIn(
            "python -m pip install -r requirements-dev.txt",
            workflow,
        )
        self.assertIn(
            'assert report["dimensions"]["azure_runtime"]["status"] == "passed"',
            workflow,
        )
        self.assertEqual(workflow.count("id-token: write"), 2)
        self.assertIn("E2E_OWNER_SESSION_STORAGE_JSON", workflow)
        self.assertIn("E2E_REVIEWER_SESSION_STORAGE_JSON", workflow)
        self.assertIn("E2E_EXPECTED_TENANT_ID", workflow)
        self.assertIn("MAF_REAL_RESULT_FACTORY", workflow)
        self.assertIn("MAF_REAL_AUTH_FILE", workflow)
        self.assertLess(
            workflow.index("npm ci --no-audit --no-fund"),
            workflow.index("E2E_OWNER_STORAGE_STATE_JSON"),
        )
        self.assertLess(
            workflow.index(
                'uv sync --locked --project "$RUNNER_TEMP/order-resolution/backend"'
            ),
            workflow.index("MAF_REAL_PROVIDER_AUTH_JSON"),
        )
        for forbidden in (
            "azd up",
            "azd deploy",
            "terraform apply",
            "az deployment",
            "az containerapp update",
            "az containerapp revision activate",
            "az postgres flexible-server firewall-rule create",
            "az postgres flexible-server firewall-rule update",
            "az postgres flexible-server firewall-rule delete",
            "az postgres flexible-server start",
            "az postgres flexible-server stop",
        ):
            self.assertNotIn(forbidden, workflow)

    def test_cloud_failure_injection_is_opt_in_and_bound_to_nonproduction(self):
        workflow = (ROOT / ".github" / "workflows" / "cloud-validation.yml").read_text(
            encoding="utf-8"
        )
        failure_input = workflow.split("      run_failure_injection:\n", 1)[1].split(
            "      failure_target_id:\n", 1
        )[0]
        self.assertIn("default: false", failure_input)
        job = workflow.split("  failure-injection:\n", 1)[1].split(
            "\n  telemetry-correlation:\n", 1
        )[0]
        self.assertIn("needs: exact-active-revision", job)
        self.assertIn("environment: azure-foundry-failure-injection-nonproduction", job)
        self.assertIn("ubuntu-24.04", job)
        self.assertIn("Azure/setup-azd@", job)
        self.assertIn("version: 1.39.1", job)
        self.assertIn("azure/login@", job)
        self.assertIn("FAILURE_TARGET_KIND", job)
        self.assertIn('test "$FAILURE_TARGET_KIND" = "synthetic-nonproduction"', job)
        self.assertIn("workstream-d-active-revision", job)
        self.assertIn("MAF_HOSTED_FAILURE_AUTH_FILE", job)
        self.assertIn("MAF_HOSTED_FAILURE_TARGET_ID", job)
        self.assertIn("gh run view", workflow)
        self.assertIn("--json headSha,conclusion,workflowName", workflow)
        self.assertIn("MAF_HOSTED_DEPLOYMENT_WORKFLOW_PATH", workflow)
        self.assertIn(
            'test "$(jq -r .path <<<"$run_json")" = "$DEPLOYMENT_WORKFLOW_PATH"',
            workflow,
        )
        self.assertIn("workstream-d-active-revision", job)
        self.assertLess(
            job.index("uv sync --locked"),
            job.index("azure/login@"),
        )
        self.assertLess(
            job.index("Require synthetic nonproduction target"),
            job.index("azure/login@"),
        )
        self.assertLess(
            job.index("Restore hosted adapter authentication material"),
            job.index("Run bounded hosted failure injection"),
        )
        self.assertIn('ACTIONS_ID_TOKEN_REQUEST_TOKEN: ""', job)

    def test_postgres_readiness_waits_for_tcp_and_fails_after_timeout(self):
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("Bash is required to exercise the GitHub Actions step.")

        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        for marker, container in (
            ("      - name: Start isolated PostgreSQL\n", "maf-core-test"),
            ("      - name: Start isolated test PostgreSQL\n", "maf-instance-test"),
        ):
            step = workflow.split(marker, 1)[1].split("      - name:", 1)[0]
            script = textwrap.dedent(
                "for attempt in {1..60}; do\n"
                + step.split("          for attempt in {1..60}; do\n", 1)[1].split(
                    "      - name:", 1
                )[0]
            )
            stub = (
                "count=0\n"
                "docker() {\n"
                f'  [[ "$*" == "exec {container} pg_isready -q -h 127.0.0.1 -U blueprint_test -d blueprint_test" ]] || exit 99\n'
                '  count=$((count + 1)); echo "$count" > "$COUNT_FILE"\n'
                '  [[ "$count" -ge "$READY_AT" ]]\n'
                "}\n"
                "sleep() { :; }\n"
            )
            with tempfile.TemporaryDirectory() as temporary:
                count_file = Path(temporary) / "attempts"
                for ready_at, status, attempts in ((3, 0, "3"), (61, 1, "60")):
                    with self.subTest(container=container, ready_at=ready_at):
                        environment = os.environ.copy()
                        environment.update(
                            COUNT_FILE=count_file.as_posix(), READY_AT=str(ready_at)
                        )
                        result = subprocess.run(
                            [bash, "-e", "-c", stub + script],
                            env=environment,
                            capture_output=True,
                            text=True,
                            check=False,
                        )
                        self.assertEqual(
                            result.returncode, status, result.stdout + result.stderr
                        )
                        self.assertEqual(count_file.read_text().strip(), attempts)
                        if status:
                            self.assertIn(
                                "PostgreSQL TCP did not become ready", result.stderr
                            )

        compose = (ROOT / "blueprints" / "maf" / "workflow" / "compose.yaml").read_text(
            encoding="utf-8"
        )
        postgres = compose.split("  postgres:\n", 1)[1].split("\n  api:\n", 1)[0]
        self.assertIn(
            'test: ["CMD-SHELL", "pg_isready -q -h 127.0.0.1 -U blueprint -d blueprint"]',
            postgres,
        )
        self.assertIn("timeout: 3s", postgres)
        self.assertIn("retries: 20", postgres)

    def test_generated_verifier_step_propagates_failures_and_rejects_skips(self):
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("Bash is required to exercise the GitHub Actions step.")

        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        marker = "      - name: Run generated contracts and golden acceptance without skips\n"
        step = workflow.split(marker, 1)[1].split("      - name:", 1)[0]
        self.assertTrue(step.startswith("        run: |\n"))
        script = textwrap.dedent(step.split("\n", 1)[1])
        stub = (
            'python() { printf "%s\\n" "$TEST_OUTPUT"; return "$TEST_STATUS"; }\n'
            "uv() {\n"
            '  [[ "$1" == run && "$2" == --locked && "$3" == --project && '
            '"$4" == "$GENERATED_DIR/backend" && "$5" == python ]] || return 99\n'
            "  shift 5\n"
            '  python "$@"\n'
            "}\n"
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
                    self.assertEqual(
                        result.returncode, expected, result.stdout + result.stderr
                    )


if __name__ == "__main__":
    unittest.main()
