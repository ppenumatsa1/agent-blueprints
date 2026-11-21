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
