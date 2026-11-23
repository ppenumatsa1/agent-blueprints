import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

import scripts.instantiate_maf as instantiator


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "instantiate_maf.py"


class InstantiationTests(unittest.TestCase):
    def generate_order_resolution(self, parent: Path) -> tuple[Path, Path, Path, Path]:
        contract = parent / "acceptance-contract.json"
        contract.write_text(
            '{"id":"order-resolution-spec","version":"0.1.0"}\n',
            encoding="utf-8",
        )
        cases = parent / "golden-cases.json"
        cases.write_text(
            '{"scenario_set":"order-resolution-spec/0.1.0","cases":[{"id":"TEST-001"}]}\n',
            encoding="utf-8",
        )
        contract_test = parent / "test_order_resolution_contract.py"
        contract_test.write_text(
            (
                "import unittest\n\n"
                "class OrderResolutionContractTests(unittest.TestCase):\n"
                "    def test_isolated_fixture(self):\n"
                "        self.assertTrue(True)\n"
            ),
            encoding="utf-8",
        )
        target = parent / "order-resolution"
        subprocess.run(
            [
                sys.executable,
                str(GENERATOR),
                str(target),
                "--profile",
                "order-resolution",
                "--order-resolution-contract",
                str(contract),
                "--order-resolution-cases",
                str(cases),
                "--order-resolution-test",
                str(contract_test),
            ],
            check=True,
            capture_output=True,
        )
        return target, contract, cases, contract_test

    def test_external_effect_guidance_does_not_treat_outbox_as_deduplication(self):
        workflow = ROOT / "blueprints" / "maf" / "workflow"
        passages = (
            (
                workflow / "README.md",
                "The local host uses",
                "The Foundry Responses adapter",
            ),
            (
                workflow / "docs" / "architecture.md",
                "4. A database action",
                "The [testing guide]",
            ),
            (
                workflow / "docs" / "design" / "architecture.md",
                "The per-case PostgreSQL",
                "For an interrupted start",
            ),
            (workflow / "docs" / "design" / "specs.md", "| SPEC-05 |", "| SPEC-06 |"),
            (
                workflow / "docs" / "design" / "specs.md",
                "| Consequential external effects |",
                "```mermaid",
            ),
            (
                workflow / "docs" / "design" / "issues-changes-fixes.md",
                "- **Priority/extension decisions:**",
                "- **Next verification:**",
            ),
            (
                ROOT / "docs" / "implementation-plan.md",
                "| P0: consequential external side effects |",
                "| P1-07",
            ),
            (
                ROOT / "docs" / "master-checklist.md",
                "| Consequential external side-effect authorization",
                "| Authenticated FastAPI",
            ),
        )
        for document, start, end in passages:
            with self.subTest(document=document.relative_to(ROOT), passage=start):
                text = (
                    document.read_text(encoding="utf-8")
                    .split(start, 1)[1]
                    .split(end, 1)[0]
                )
                text = " ".join(text.lower().split())
                for phrase in (
                    "service-specific authorization",
                    "downstream idempotency",
                    "authoritative reconciliation",
                    "fail closed",
                    "manual resolution",
                    "outbox only persists intent",
                    "deduplicat",
                    "lost acknowledgment",
                ):
                    self.assertIn(phrase, text)

    def test_hosted_identity_guidance_rejects_unverified_oid_binding(self):
        documents = (
            ROOT / "docs" / "agent-blueprints-architecture.md",
            ROOT / "docs" / "implementation-plan.md",
            ROOT / "docs" / "master-checklist.md",
            ROOT
            / "blueprints"
            / "maf"
            / "workflow"
            / "docs"
            / "design"
            / "architecture.md",
        )
        oid_claim = re.compile(
            r"(?:x-ms-user-identity.{0,80}(?:trusted user OID|user OID)|"
            r"(?:identity|OID) header is (?:a |the )?(?:user OID|identity|not a credential))",
            re.IGNORECASE | re.DOTALL,
        )
        for document in documents:
            with self.subTest(document=document.relative_to(ROOT)):
                text = document.read_text(encoding="utf-8")
                self.assertNotRegex(text, oid_claim)

        journal = (
            ROOT
            / "blueprints"
            / "maf"
            / "workflow"
            / "docs"
            / "design"
            / "issues-changes-fixes.md"
        ).read_text(encoding="utf-8")
        historical_claim = "trusted user OID. **Superseded/unverified:**"
        self.assertIn(historical_claim, journal)
        clarification = journal.split(historical_claim, 1)[1].split("Current azd", 1)[0]
        for required in ("opaque", "x-agent-user-id", "not be persisted", "unverified"):
            with self.subTest(clarification=required):
                self.assertIn(required, clarification)

    def test_copied_project_owns_runtime_verifier_and_exact_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "application"
            subprocess.run(
                [sys.executable, str(GENERATOR), str(target)],
                check=True,
                capture_output=True,
            )
            source_contract = (
                ROOT / "scenarios" / "order-adjustment" / "verification-contract.json"
            )
            copied_contract = (
                target
                / "verification"
                / "scenarios"
                / "order-adjustment"
                / "verification-contract.json"
            )
            self.assertEqual(source_contract.read_bytes(), copied_contract.read_bytes())
            for source in (ROOT / "contracts").rglob("*"):
                if source.is_file():
                    copied = (
                        target
                        / "verification"
                        / "contracts"
                        / source.relative_to(ROOT / "contracts")
                    )
                    with self.subTest(contract=source.name):
                        self.assertEqual(source.read_bytes(), copied.read_bytes())
            self.assertTrue((target / "compose.yaml").is_file())
            self.assertTrue(
                (target / "backend" / "tests" / "order_adjustment_adapter.py").is_file()
            )
            self.assertFalse(
                (target / "backend" / "app" / "extensions" / "agents.py").exists()
            )
            for relative in (
                "backend/app/extensions/model.py",
                "backend/app/extensions/prompts.py",
                "backend/app/extensions/tools.py",
                "backend/app/extensions/evaluation.py",
                "backend/examples/prompts/synthetic-review.v1.md",
                "backend/examples/evaluation_fixture.py",
                "backend/tests/test_extensions.py",
                "backend/tests/test_evaluation.py",
                "backend/tests/hosted_failure_runner.py",
                "backend/tests/test_hosted_failure_runner.py",
                "frontend/playwright.config.ts",
                "frontend/e2e/local.spec.ts",
                "frontend/e2e/live.spec.ts",
            ):
                self.assertEqual(
                    (ROOT / "blueprints" / "maf" / "workflow" / relative).read_bytes(),
                    (target / relative).read_bytes(),
                )
            self.assertTrue((target / "backend" / "Dockerfile").is_file())
            generated_dockerfile = (target / "backend" / "Dockerfile").read_bytes()
            self.assertEqual(
                (ROOT / "blueprints" / "maf" / "workflow" / "backend" / "Dockerfile").read_bytes(),
                generated_dockerfile,
            )
            self.assertIn(
                b"SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt",
                generated_dockerfile,
            )
            for relative in (
                Path("agent-framework-core.sha256"),
                Path("scripts") / "verify_framework_supply_chain.py",
            ):
                source_backend_file = (
                    ROOT / "blueprints" / "maf" / "workflow" / "backend" / relative
                )
                self.assertEqual(
                    source_backend_file.read_bytes(),
                    (target / "backend" / relative).read_bytes(),
                )
            source_docs = ROOT / "blueprints" / "maf" / "workflow" / "docs"
            for source in source_docs.rglob("*.md"):
                copied = target / "docs" / source.relative_to(source_docs)
                with self.subTest(document=source.relative_to(source_docs)):
                    self.assertEqual(source.read_bytes(), copied.read_bytes())
            for markdown in (
                target / "README.md",
                *sorted((target / "docs").rglob("*.md")),
                *sorted((target / "infra").rglob("*.md")),
            ):
                links = re.findall(
                    r"\[[^\]]+\]\(([^)]+)\)", markdown.read_text(encoding="utf-8")
                )
                for destination in links:
                    link = urlsplit(destination)
                    if link.scheme or destination.startswith("//"):
                        continue
                    linked_path = unquote(link.path)
                    resolved = (
                        (markdown.parent / linked_path).resolve()
                        if linked_path
                        else markdown.resolve()
                    )
                    with self.subTest(
                        document=markdown.relative_to(target), link=destination
                    ):
                        self.assertTrue(
                            resolved.is_file(),
                            f"Broken generated-project link: {destination}",
                        )
            for path in (
                "backend/pyproject.toml",
                "backend/uv.lock",
                "backend/.python-version",
                ".vscode/launch.json",
                ".vscode/tasks.json",
            ):
                self.assertTrue((target / path).is_file(), path)
            self.assertEqual(
                (
                    ROOT / "blueprints" / "maf" / "workflow" / "backend" / "uv.lock"
                ).read_bytes(),
                (target / "backend" / "uv.lock").read_bytes(),
            )
            self.assertFalse((target / "backend" / ".venv").exists())
            self.assertFalse((target / "backend" / ".uv-cache").exists())
            self.assertFalse((target / "backend" / ".ruff_cache").exists())
            for name in (
                "baseline.sql",
                "env.py",
                "versions/0001_baseline.py",
                "manifests/0001.json",
            ):
                source = (
                    ROOT
                    / "blueprints"
                    / "maf"
                    / "workflow"
                    / "backend"
                    / "migrations"
                    / name
                )
                self.assertEqual(
                    source.read_bytes(),
                    (target / "backend" / "migrations" / name).read_bytes(),
                )
            for name in (
                "prd",
                "techstack",
                "specs",
                "architecture",
                "projectstructure",
                "userflow",
                "deployment-flow",
                "issues-changes-fixes",
            ):
                self.assertTrue((target / "docs" / "design" / f"{name}.md").is_file())
            self.assertFalse((target / "docs" / "engineering-journal.md").exists())

            self.assertTrue((target / "azure.yaml").is_file())
            self.assertTrue((target / "infra" / "main.bicep").is_file())
            self.assertTrue((target / "infra" / "validate.py").is_file())
            self.assertTrue((target / "infra" / "modules" / "foundry.bicep").is_file())
            self.assertTrue(
                (target / "infra" / "tests" / "test_validation.py").is_file()
            )
            self.assertTrue(
                (target / "infra" / "environments" / "dev.example.bicepparam").is_file()
            )
            self.assertTrue(
                (
                    target / "infra" / "environments" / "prod.example.bicepparam"
                ).is_file()
            )
            self.assertFalse((target / "frontend" / "node_modules").exists())
            self.assertFalse((target / "frontend" / "dist").exists())
            self.assertTrue(
                (target / "verification" / "readiness" / "release.py").is_file()
            )
            self.assertTrue(
                (
                    target / "verification" / "tests" / "test_release_evidence.py"
                ).is_file()
            )
            self.assertIn(
                "verification/scenarios/order-adjustment/verification-contract.json -text",
                (target / ".gitattributes").read_text(encoding="utf-8"),
            )
            self.assertFalse((target / ".env").exists())
            environment = os.environ.copy()
            environment.pop("PYTHONPATH", None)
            for cwd, module in (
                (target / "backend", "app"),
                (target / "verification", "readiness"),
            ):
                result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        f"import {module}; print({module}.__file__)",
                    ],
                    cwd=cwd,
                    env=environment,
                    text=True,
                    capture_output=True,
                    check=True,
                )
                self.assertTrue(
                    Path(result.stdout.strip())
                    .resolve()
                    .is_relative_to(target.resolve())
                )

    def test_refuses_existing_or_repository_destinations(self):
        with tempfile.TemporaryDirectory() as temporary:
            existing = Path(temporary) / "existing"
            existing.mkdir()
            marker = existing / "keep.txt"
            marker.write_text("unchanged", encoding="utf-8")
            for target in (existing, ROOT / "should-not-be-created"):
                with self.subTest(target=target):
                    result = subprocess.run(
                        [sys.executable, str(GENERATOR), str(target)],
                        text=True,
                        capture_output=True,
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("Instantiation failed:", result.stderr)
            self.assertEqual(marker.read_text(encoding="utf-8"), "unchanged")
            self.assertFalse((ROOT / "should-not-be-created").exists())

    def test_order_resolution_profile_is_explicit_and_independent(self):
        with tempfile.TemporaryDirectory() as temporary:
            target, contract, cases, contract_test = self.generate_order_resolution(
                Path(temporary)
            )
            self.assertEqual(
                contract.read_bytes(),
                (
                    target
                    / "verification"
                    / "scenarios"
                    / "order-resolution"
                    / "acceptance-contract.json"
                ).read_bytes(),
            )
            self.assertEqual(
                cases.read_bytes(),
                (
                    target
                    / "verification"
                    / "scenarios"
                    / "order-resolution"
                    / "golden-cases.json"
                ).read_bytes(),
            )
            self.assertEqual(
                contract_test.read_bytes(),
                (
                    target
                    / "verification"
                    / "tests"
                    / "test_order_resolution_contract.py"
                ).read_bytes(),
            )
            for relative in (
                "backend/app/order_resolution/action.py",
                "backend/app/order_resolution/application.py",
                "backend/app/order_resolution/host.py",
                "backend/app/order_resolution/persistence.py",
                "backend/app/order_resolution/rules.py",
                "backend/app/order_resolution/service.py",
                "backend/app/order_resolution/workflow.py",
                "backend/order_resolution_hosted/__init__.py",
                "backend/order_resolution_hosted/bridge.py",
                "backend/order_resolution_hosted/client.py",
                "backend/tests/test_order_resolution.py",
                "backend/tests/test_order_resolution_api.py",
                "hosted-agent/main.py",
                "hosted-agent/requirements.txt",
                "hosted-agent/src/order_resolution_hosted/bridge.py",
                "hosted-agent/src/order_resolution_hosted/business.py",
                "hosted-agent/src/order_resolution_hosted/host.py",
                "hosted-agent/src/order_resolution_hosted/client.py",
                "hosted-agent/src/order_resolution_hosted/model.py",
                "hosted-agent/tests/test_application.py",
                "hosted-agent/tests/test_bridge.py",
                "hosted-agent/tests/test_business.py",
                "hosted-agent/tests/test_protocol.py",
                "scripts/foundry/publish_order_resolution_hosted.py",
                "backend/tests/test_order_resolution_real_provider.py",
                "frontend/src/order-resolution.tsx",
                "frontend/src/test/order-resolution.test.tsx",
                "docs/order-resolution.md",
            ):
                self.assertTrue((target / relative).is_file(), relative)
            for name in ("bridge.py", "client.py"):
                self.assertEqual(
                    (
                        ROOT
                        / "profiles"
                        / "order-resolution"
                        / "hosted-agent"
                        / "src"
                        / "order_resolution_hosted"
                        / name
                    ).read_bytes(),
                    (
                        target / "backend" / "order_resolution_hosted" / name
                    ).read_bytes(),
                )
            backend_init = (
                target / "backend" / "order_resolution_hosted" / "__init__.py"
            ).read_text(encoding="utf-8")
            self.assertNotIn("from .", backend_init)
            hosted_init = (
                target
                / "hosted-agent"
                / "src"
                / "order_resolution_hosted"
                / "__init__.py"
            ).read_text(encoding="utf-8")
            self.assertNotIn("from .", hosted_init)
            dockerfile = (target / "backend" / "Dockerfile").read_text(encoding="utf-8")
            self.assertIn(
                "COPY --chown=blueprint:blueprint order_resolution_hosted/ "
                "order_resolution_hosted/",
                dockerfile,
            )
            self.assertIn(
                "verification/scenarios/order-resolution/verification-contract.json -text",
                (target / ".gitattributes").read_text(encoding="utf-8"),
            )
            self.assertNotIn(
                "order_resolution",
                (target / "backend" / "app" / "workflows" / "workflow.py").read_text(
                    encoding="utf-8"
                ),
            )
            self.assertFalse(any(path.is_symlink() for path in target.rglob("*")))
            repository_path = str(ROOT.resolve())
            for path in target.rglob("*"):
                if path.is_file():
                    with self.subTest(path=path.relative_to(target)):
                        self.assertNotIn(
                            repository_path,
                            path.read_text(encoding="utf-8", errors="ignore"),
                        )
            compose = (target / "compose.yaml").read_text(encoding="utf-8")
            self.assertIn(
                "BLUEPRINT_APPLICATION: ${BLUEPRINT_APPLICATION:-app.order_resolution.application:build_application}",
                compose,
            )
            generated_main = (
                target / "backend" / "app" / "main.py"
            ).read_text(encoding="utf-8")
            self.assertIn(
                "from .order_resolution.application import build_application",
                generated_main,
            )
            self.assertIn(
                "app = create_app(settings, build_application())",
                generated_main,
            )
            self.assertNotIn("BLUEPRINT_APPLICATION", generated_main)
            self.assertNotIn(str(ROOT), compose)

            environment = os.environ.copy()
            environment.pop("PYTHONPATH", None)
            backend = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "from app.order_resolution.rules import OrderResolutionRules; "
                        "print(OrderResolutionRules.__module__)"
                    ),
                ],
                cwd=target / "backend",
                env=environment,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertEqual(backend.stdout.strip(), "app.order_resolution.rules")
            bridge = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import importlib.util; "
                        "spec = importlib.util.find_spec('order_resolution_hosted.bridge'); "
                        "assert spec is not None and spec.origin is not None; "
                        "print(spec.origin)"
                    ),
                ],
                cwd=target / "backend",
                env=environment,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertTrue(
                Path(bridge.stdout.strip())
                .resolve()
                .is_relative_to(
                    (target / "backend" / "order_resolution_hosted").resolve()
                )
            )

    def test_order_resolution_profile_requires_explicit_cases_until_canonical_fixture_exists(
        self,
    ):
        scenario_root = ROOT / "scenarios" / "order-resolution"
        if (scenario_root / "acceptance-contract.json").is_file() and (
            scenario_root / "golden-cases.json"
        ).is_file():
            with tempfile.TemporaryDirectory() as temporary:
                target = Path(temporary) / "order-resolution"
                subprocess.run(
                    [
                        sys.executable,
                        str(GENERATOR),
                        str(target),
                        "--profile",
                        "order-resolution",
                    ],
                    check=True,
                    capture_output=True,
                )
                self.assertEqual(
                    (scenario_root / "acceptance-contract.json").read_bytes(),
                    (
                        target
                        / "verification"
                        / "scenarios"
                        / "order-resolution"
                        / "acceptance-contract.json"
                    ).read_bytes(),
                )
                self.assertEqual(
                    (scenario_root / "golden-cases.json").read_bytes(),
                    (
                        target
                        / "verification"
                        / "scenarios"
                        / "order-resolution"
                        / "golden-cases.json"
                    ).read_bytes(),
                )
            return
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "order-resolution"
            result = subprocess.run(
                [
                    sys.executable,
                    str(GENERATOR),
                    str(target),
                    "--profile",
                    "order-resolution",
                ],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--order-resolution-contract", result.stderr)
            self.assertFalse(target.exists())

    def test_order_resolution_profile_merges_reserved_backend_and_verification_paths(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            profile = root / "profile"
            reserved_backend = profile / "backend" / "app" / "order_resolution"
            reserved_backend.mkdir(parents=True)
            (reserved_backend / "durability.py").write_text(
                'SOURCE = "temporary-agent-c"\n', encoding="utf-8"
            )
            (reserved_backend / "effects.py").write_text(
                'SOURCE = "temporary-agent-c"\n', encoding="utf-8"
            )
            migrations = profile / "backend" / "migrations"
            migrations.mkdir(parents=True)
            (migrations / "0001_order_resolution_durability.sql").write_text(
                "-- temporary Agent C migration\n", encoding="utf-8"
            )
            reserved_tests = profile / "backend" / "tests"
            reserved_tests.mkdir(parents=True)
            (reserved_tests / "test_order_resolution_durability.py").write_text(
                'SOURCE = "temporary-agent-c"\n', encoding="utf-8"
            )
            (reserved_backend / "evaluation.py").write_text(
                'SOURCE = "temporary-agent-d"\n', encoding="utf-8"
            )
            evaluations = profile / "backend" / "evaluations"
            evaluations.mkdir(parents=True)
            (evaluations / "order-resolution-0.1.0.json").write_text(
                '{"source":"temporary-agent-d"}\n', encoding="utf-8"
            )
            (reserved_tests / "test_order_resolution_evaluation.py").write_text(
                'SOURCE = "temporary-agent-d"\n', encoding="utf-8"
            )
            (reserved_tests / "order_resolution_evidence_runner.py").write_text(
                'SOURCE = "temporary-agent-d"\n', encoding="utf-8"
            )
            reserved_verification = (
                profile / "verification" / "scenarios" / "order-resolution"
            )
            reserved_verification.mkdir(parents=True)
            (reserved_verification / "verification-contract.json").write_text(
                '{"source":"temporary-agent-d"}\n', encoding="utf-8"
            )
            (reserved_verification / "example-trust.json").write_text(
                '{"source":"temporary-agent-d-trust"}\n', encoding="utf-8"
            )
            contract = root / "acceptance-contract.json"
            contract.write_text('{"version":"0.1.0"}\n', encoding="utf-8")
            cases = root / "golden-cases.json"
            cases.write_text('{"cases":[]}\n', encoding="utf-8")
            contract_test = root / "test_order_resolution_contract.py"
            contract_test.write_text("import unittest\n", encoding="utf-8")
            target = root / "generated"

            with patch.object(instantiator, "ORDER_RESOLUTION_PROFILE", profile):
                instantiator.instantiate(
                    target,
                    profile="order-resolution",
                    order_resolution_contract=contract,
                    order_resolution_cases=cases,
                    order_resolution_test=contract_test,
                )

            self.assertEqual(
                (
                    target / "backend" / "app" / "order_resolution" / "durability.py"
                ).read_text(encoding="utf-8"),
                'SOURCE = "temporary-agent-c"\n',
            )
            self.assertEqual(
                (
                    target
                    / "verification"
                    / "scenarios"
                    / "order-resolution"
                    / "verification-contract.json"
                ).read_text(encoding="utf-8"),
                '{"source":"temporary-agent-d"}\n',
            )
            for relative in (
                "backend/app/order_resolution/effects.py",
                "backend/migrations/0001_order_resolution_durability.sql",
                "backend/tests/test_order_resolution_durability.py",
                "backend/app/order_resolution/evaluation.py",
                "backend/evaluations/order-resolution-0.1.0.json",
                "backend/tests/test_order_resolution_evaluation.py",
                "backend/tests/order_resolution_evidence_runner.py",
                "verification/scenarios/order-resolution/example-trust.json",
            ):
                self.assertTrue((target / relative).is_file(), relative)


if __name__ == "__main__":
    unittest.main()
