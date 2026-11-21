from collections.abc import Callable, Sequence

import msal

from app.config import Settings
from app.domain.errors import DelegationError
from app.infrastructure.identity import AuthenticatedRequest


class OnBehalfOf:
    """Optional server-side delegation during an authenticated request."""

    def __init__(
        self, settings: Settings, client_factory: Callable = msal.ConfidentialClientApplication
    ):
        self.settings = settings
        self._client_factory = client_factory
        self._client = None

    def exchange(self, identity: AuthenticatedRequest, scopes: Sequence[str]) -> str:
        if not self.settings.obo_enabled:
            raise DelegationError("Delegated access is disabled.")
        if not isinstance(identity, AuthenticatedRequest) or not identity.access_token:
            raise DelegationError("A validated user request is required.")
        requested = tuple(scopes)
        if not requested or any(
            scope not in self.settings.obo_allowed_scopes for scope in requested
        ):
            raise DelegationError("The requested downstream scopes are not allowed.")
        try:
            if self._client is None:
                self._client = self._client_factory(
                    client_id=self.settings.api_client_id,
                    client_credential=self.settings.obo_client_secret,
                    authority=f"https://login.microsoftonline.com/{self.settings.tenant_id}",
                    enable_pii_log=False,
                )
            result = self._client.acquire_token_on_behalf_of(
                user_assertion=identity.access_token, scopes=list(requested)
            )
        except Exception as exc:
            raise DelegationError("Delegated access failed.") from exc
        token = result.get("access_token") if isinstance(result, dict) else None
        if not isinstance(token, str) or not token:
            raise DelegationError("Delegated access failed.")
        return token
