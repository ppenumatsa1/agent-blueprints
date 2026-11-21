import importlib
import unittest

from app.application import load_application


class ModularityTests(unittest.TestCase):
    def test_original_extension_modules_are_the_layered_modules(self):
        modules = {
            "models": "domain.models",
            "errors": "domain.errors",
            "policy": "domain.policy",
            "service": "usecases.service",
            "host": "workflows.host",
            "workflow": "workflows.workflow",
            "store": "infrastructure.store",
            "identity": "infrastructure.identity",
            "delegation": "infrastructure.delegation",
        }
        for original, layered in modules.items():
            with self.subTest(module=original):
                self.assertIs(
                    importlib.import_module("app." + original),
                    importlib.import_module("app." + layered),
                )
        self.assertIsNotNone(load_application("examples.synthetic_application:build_application"))
