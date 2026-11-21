import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "instantiate_maf.py"


class InstantiationTests(unittest.TestCase):
    def test_external_effect_guidance_does_not_treat_outbox_as_deduplication(self):
        workflow = ROOT / "blueprints" / "maf" / "workflow"
        passages = (
            (workflow / "README.md", "The local host uses", "The Foundry Responses adapter"),
            (workflow / "docs" / "architecture.md", "4. A database action", "The [testing guide]"),
            (workflow / "docs" / "design" / "architecture.md", "The per-case PostgreSQL", "For an interrupted start"),
            (workflow / "docs" / "design" / "specs.md", "| SPEC-05 |", "| SPEC-06 |"),
            (workflow / "docs" / "design" / "specs.md", "| Consequential external effects |", "```mermaid"),
            (workflow / "docs" / "design" / "issues-changes-fixes.md", "- **Priority/extension decisions:**", "- **Next verification:**"),
            (ROOT / "docs" / "implementation-plan.md", "| P0: consequential external side effects |", "| P1-07"),
            (ROOT / "docs" / "master-checklist.md", "| Consequential external side-effect authorization", "| Authenticated FastAPI"),
        )
        for document, start, end in passages:
            with self.subTest(document=document.relative_to(ROOT), passage=start):
                text = document.read_text(encoding="utf-8").split(start, 1)[1].split(end, 1)[0]
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
            ROOT / "blueprints" / "maf" / "workflow" / "docs" / "design" / "architecture.md",
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
            ROOT / "blueprints" / "maf" / "workflow" / "docs" / "design" / "issues-changes-fixes.md"
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
            subprocess.run([sys.executable, str(GENERATOR), str(target)], check=True, capture_output=True)
            source_contract = ROOT / "scenarios" / "order-adjustment" / "verification-contract.json"
            copied_contract = target / "verification" / "scenarios" / "order-adjustment" / "verification-contract.json"
            self.assertEqual(source_contract.read_bytes(), copied_contract.read_bytes())
            for source in (ROOT / "contracts").rglob("*"):
                if source.is_file():
                    copied = target / "verification" / "contracts" / source.relative_to(ROOT / "contracts")
                    with self.subTest(contract=source.name):
                        self.assertEqual(source.read_bytes(), copied.read_bytes())
            self.assertTrue((target / "compose.yaml").is_file())
            self.assertTrue((target / "backend" / "tests" / "order_adjustment_adapter.py").is_file())
            self.assertTrue((target / "backend" / "Dockerfile").is_file())
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
                links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", markdown.read_text(encoding="utf-8"))
                for destination in links:
                    link = urlsplit(destination)
                    if link.scheme or destination.startswith("//"):
                        continue
                    linked_path = unquote(link.path)
                    resolved = (markdown.parent / linked_path).resolve() if linked_path else markdown.resolve()
                    with self.subTest(document=markdown.relative_to(target), link=destination):
                        self.assertTrue(resolved.is_file(), f"Broken generated-project link: {destination}")
            for path in ("backend/pyproject.toml", "backend/uv.lock", "backend/.python-version",
                         ".vscode/launch.json", ".vscode/tasks.json"):
                self.assertTrue((target / path).is_file(), path)
            self.assertEqual(
                (ROOT / "blueprints" / "maf" / "workflow" / "backend" / "uv.lock").read_bytes(),
                (target / "backend" / "uv.lock").read_bytes(),
            )
            self.assertFalse((target / "backend" / ".venv").exists())
            self.assertFalse((target / "backend" / ".uv-cache").exists())
            self.assertFalse((target / "backend" / ".ruff_cache").exists())
            for name in ("baseline.sql", "env.py", "versions/0001_baseline.py", "manifests/0001.json"):
                source = ROOT / "blueprints" / "maf" / "workflow" / "backend" / "migrations" / name
                self.assertEqual(source.read_bytes(), (target / "backend" / "migrations" / name).read_bytes())
            for name in ("prd", "techstack", "specs", "architecture", "projectstructure", "userflow",
                         "deployment-flow", "issues-changes-fixes"):
                self.assertTrue((target / "docs" / "design" / f"{name}.md").is_file())
            self.assertFalse((target / "docs" / "engineering-journal.md").exists())

            self.assertTrue((target / "azure.yaml").is_file())
            self.assertTrue((target / "infra" / "main.bicep").is_file())
            self.assertTrue((target / "infra" / "validate.py").is_file())
            self.assertTrue((target / "infra" / "modules" / "foundry.bicep").is_file())
            self.assertTrue((target / "infra" / "tests" / "test_validation.py").is_file())
            self.assertTrue((target / "infra" / "environments" / "dev.example.bicepparam").is_file())
            self.assertTrue((target / "infra" / "environments" / "prod.example.bicepparam").is_file())
            self.assertFalse((target / "frontend" / "node_modules").exists())
            self.assertFalse((target / "frontend" / "dist").exists())
            self.assertFalse((target / ".env").exists())
            environment = os.environ.copy()
            environment.pop("PYTHONPATH", None)
            for cwd, module in ((target / "backend", "app"), (target / "verification", "readiness")):
                result = subprocess.run(
                    [sys.executable, "-c", f"import {module}; print({module}.__file__)"],
                    cwd=cwd,
                    env=environment,
                    text=True,
                    capture_output=True,
                    check=True,
                )
                self.assertTrue(Path(result.stdout.strip()).resolve().is_relative_to(target.resolve()))

    def test_refuses_existing_or_repository_destinations(self):
        with tempfile.TemporaryDirectory() as temporary:
            existing = Path(temporary) / "existing"
            existing.mkdir()
            marker = existing / "keep.txt"
            marker.write_text("unchanged", encoding="utf-8")
            for target in (existing, ROOT / "should-not-be-created"):
                with self.subTest(target=target):
                    result = subprocess.run(
                        [sys.executable, str(GENERATOR), str(target)], text=True, capture_output=True
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("Instantiation failed:", result.stderr)
            self.assertEqual(marker.read_text(encoding="utf-8"), "unchanged")
            self.assertFalse((ROOT / "should-not-be-created").exists())


if __name__ == "__main__":
    unittest.main()
