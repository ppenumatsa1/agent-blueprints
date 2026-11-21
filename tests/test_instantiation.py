import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "instantiate_maf.py"


class InstantiationTests(unittest.TestCase):
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
            self.assertTrue((target / "backend" / "requirements-dev.txt").is_file())
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
