import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID


def _origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
        or "*" in value
    ):
        raise ValueError("CORS origins must be explicit HTTP(S) origins.")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Plain HTTP origins are permitted only on loopback.")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("A CORS origin has an invalid port.") from exc
    return value


@dataclass(frozen=True)
class Settings:
    tenant_id: str
    api_client_id: str
    database_url: str = field(repr=False)
    checkpoint_root: Path
    cors_origins: tuple[str, ...] = ()
    host_mode: str = "local"
    obo_enabled: bool = False
    obo_client_secret: str | None = field(default=None, repr=False)
    obo_allowed_scopes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "tenant_id", str(UUID(self.tenant_id)))
            object.__setattr__(self, "api_client_id", str(UUID(self.api_client_id)))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError(
                "Entra tenant and API client IDs must be configured as UUIDs."
            ) from exc
        if not self.database_url or urlsplit(self.database_url).scheme not in (
            "postgres",
            "postgresql",
        ):
            raise ValueError("A PostgreSQL connection URL is required.")
        if not str(self.checkpoint_root):
            raise ValueError("A local checkpoint root is required.")
        if self.host_mode != "local":
            raise ValueError("Only the explicitly selected local host is implemented.")
        for value in self.cors_origins:
            _origin(value)
        if self.obo_enabled and (not self.obo_client_secret or not self.obo_allowed_scopes):
            raise ValueError("Enabled OBO requires a client secret and allowed downstream scopes.")
        for scope in self.obo_allowed_scopes:
            parsed = urlsplit(scope)
            if (
                parsed.scheme not in ("https", "api")
                or not parsed.netloc
                or any(c.isspace() for c in scope)
            ):
                raise ValueError("OBO scopes must be explicit resource-qualified scopes.")

    @classmethod
    def from_environment(cls) -> "Settings":
        def values(name: str) -> tuple[str, ...]:
            return tuple(
                value.strip() for value in os.environ.get(name, "").split(",") if value.strip()
            )

        enabled = os.environ.get("OBO_ENABLED", "false").lower()
        if enabled not in ("true", "false"):
            raise ValueError("OBO_ENABLED must be true or false.")
        checkpoint_root = os.environ.get("CHECKPOINT_ROOT")
        if not checkpoint_root:
            raise ValueError("CHECKPOINT_ROOT is required.")
        return cls(
            tenant_id=os.environ.get("ENTRA_TENANT_ID", ""),
            api_client_id=os.environ.get("ENTRA_API_CLIENT_ID", ""),
            database_url=os.environ.get("DATABASE_URL", ""),
            checkpoint_root=Path(checkpoint_root),
            cors_origins=values("CORS_ORIGINS"),
            host_mode=os.environ.get("WORKFLOW_HOST", "local"),
            obo_enabled=enabled == "true",
            obo_client_secret=os.environ.get("ENTRA_API_CLIENT_SECRET") or None,
            obo_allowed_scopes=values("OBO_ALLOWED_SCOPES"),
        )
