"""Compatibility alias for the original blueprint module."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("app.infrastructure.identity")
