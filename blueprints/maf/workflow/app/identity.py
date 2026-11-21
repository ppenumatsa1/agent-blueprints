from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

import jwt

from .config import Settings
from .errors import AuthenticationFailed, AuthenticationUnavailable
from .models import Principal


@dataclass(frozen=True)
class AuthenticatedRequest:
    principal: Principal
    access_token: str = field(repr=False, compare=False)


class IdentityProvider(Protocol):
    def authenticate(self, access_token: str) -> AuthenticatedRequest: ...


class EntraIdentity:
    """Validate delegated, single-tenant Entra v2 access tokens for this API."""

    def __init__(self, settings: Settings, jwks_client=None):
        self.settings = settings
        self.issuer = f"https://login.microsoftonline.com/{settings.tenant_id}/v2.0"
        self.jwks = jwks_client or jwt.PyJWKClient(
            f"https://login.microsoftonline.com/{settings.tenant_id}/discovery/v2.0/keys",
            cache_jwk_set=True,
            lifespan=300,
            timeout=5,
        )

    def authenticate(self, access_token: str) -> AuthenticatedRequest:
        if not isinstance(access_token, str) or not access_token or len(access_token) > 16_384:
            raise AuthenticationFailed("A valid bearer access token is required.")
        try:
            header = jwt.get_unverified_header(access_token)
            kid = header.get("kid")
            if header.get("alg") != "RS256" or not isinstance(kid, str) or not 1 <= len(kid) <= 128:
                raise AuthenticationFailed("A valid bearer access token is required.")
            key = self.jwks.get_signing_key_from_jwt(access_token)
            claims = jwt.decode(
                access_token,
                key.key,
                algorithms=["RS256"],
                audience=self.settings.api_client_id,
                issuer=self.issuer,
                options={"require": ["iss", "aud", "exp", "nbf", "iat", "tid", "oid", "sub", "scp", "ver"]},
            )
            tenant = str(UUID(claims["tid"]))
            subject = str(UUID(claims["oid"]))
            scopes = claims["scp"]
            roles = claims.get("roles", [])
            if (
                tenant != self.settings.tenant_id
                or claims["aud"] != self.settings.api_client_id
                or claims["ver"] != "2.0"
                or not isinstance(claims["sub"], str)
                or not claims["sub"]
                or not isinstance(scopes, str)
                or not scopes.strip()
                or not isinstance(roles, list)
                or any(not isinstance(role, str) for role in roles)
            ):
                raise AuthenticationFailed("A valid delegated access token is required.")
        except jwt.PyJWKClientConnectionError as exc:
            raise AuthenticationUnavailable("Signing keys are temporarily unavailable.") from exc
        except (jwt.PyJWTError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise AuthenticationFailed("A valid bearer access token is required.") from exc
        principal = Principal(tenant, subject, frozenset(scopes.split()), frozenset(roles))
        return AuthenticatedRequest(principal, access_token)
