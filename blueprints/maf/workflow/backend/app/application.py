import importlib
from collections.abc import Callable
from dataclasses import dataclass

from app.workflows.host import WorkflowFactory
from app.domain.models import AccessPolicy, BusinessRules, StateRepository, TransactionalAction
from app.workflows.workflow import create_workflow


def _no_initialization(store: StateRepository) -> None:
    pass


@dataclass(frozen=True)
class ApplicationComponents:
    rules: BusinessRules
    policy: AccessPolicy
    action: TransactionalAction
    initialize: Callable[[StateRepository], None] = _no_initialization
    workflow_factory: WorkflowFactory = create_workflow


def load_application(specification: str) -> ApplicationComponents:
    module_name, separator, factory_name = specification.partition(":")
    if not module_name or not separator or not factory_name:
        raise ValueError("BLUEPRINT_APPLICATION must name an application factory as module:function.")
    factory = getattr(importlib.import_module(module_name), factory_name)
    components = factory()
    if not isinstance(components, ApplicationComponents):
        raise TypeError("The application factory must return ApplicationComponents.")
    return components
