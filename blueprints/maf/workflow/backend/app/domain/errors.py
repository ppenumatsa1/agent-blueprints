class BlueprintError(Exception):
    """A safe, expected application error."""


class AccessDenied(BlueprintError):
    pass


class NotFound(BlueprintError):
    pass


class Conflict(BlueprintError):
    pass


class CheckpointError(BlueprintError):
    pass


class ActionError(BlueprintError):
    pass


class AuthenticationFailed(BlueprintError):
    pass


class AuthenticationUnavailable(BlueprintError):
    pass


class DelegationError(BlueprintError):
    pass


class HostedWorkflowError(BlueprintError):
    pass


class InvalidInput(BlueprintError):
    pass


class HistoryScanLimitExceeded(BlueprintError):
    pass
