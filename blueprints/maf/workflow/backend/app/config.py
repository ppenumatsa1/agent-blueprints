import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

HOSTED_SERVICE_APP_ROLE = "Hosted.Workflow.Invoke"


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


def _foundry_endpoint(value: str | None, suffix: str, label: str) -> str:
    parsed = urlsplit(value or "")
    query = parse_qs(parsed.query, strict_parsing=True)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
        or not parsed.path.rstrip("/").endswith(suffix)
        or set(query) != {"api-version"}
        or len(query["api-version"]) != 1
        or not query["api-version"][0]
    ):
        raise ValueError(f"{label} must be an explicit Foundry HTTPS endpoint.")
    return value or ""


@dataclass(frozen=True)
class Settings:
    tenant_id: str
    api_client_id: str
    database_url: str = field(repr=False)
    checkpoint_root: Path | None
    api_app_id_uri: str | None = None
    cors_origins: tuple[str, ...] = ()
    host_mode: str = "local"
    hosted_workflow_endpoint: str | None = None
    hosted_conversation_endpoint: str | None = None
    hosted_workflow_scope: str | None = None
    api_managed_identity_client_id: str | None = None
    hosted_service_principal_id: str | None = None
    hosted_service_app_role: str | None = None
    database_auth_mode: str = "password"
    database_password: str | None = field(default=None, repr=False)
    database_managed_identity_client_id: str | None = None
    database_tls_mode: str = "disable"
    database_tls_root_cert: str | None = None
    database_pool_min_size: int = 1
    database_pool_max_size: int = 8
    database_pool_timeout_seconds: float = 5.0
    database_connection_max_lifetime_seconds: float = 2700.0
    obo_enabled: bool = False
    obo_client_secret: str | None = field(default=None, repr=False)
    obo_allowed_scopes: tuple[str, ...] = ()
    telemetry_mode: str = "local"
    applicationinsights_connection_string: str | None = field(default=None, repr=False)
    agent_version: str = "0.1.0"
    deployment_revision: str = "local-unversioned"
    acceptance_mode: bool = False

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "tenant_id", str(UUID(self.tenant_id)))
            object.__setattr__(self, "api_client_id", str(UUID(self.api_client_id)))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError(
                "Entra tenant and API client IDs must be configured as UUIDs."
            ) from exc
        if self.api_app_id_uri is not None:
            audience = urlsplit(self.api_app_id_uri)
            if (
                audience.scheme not in ("api", "https")
                or not audience.netloc
                or audience.username
                or audience.password
                or audience.query
                or audience.fragment
            ):
                raise ValueError("ENTRA_API_APP_ID_URI must be an explicit API audience.")
        database = urlsplit(self.database_url)
        if not self.database_url or database.scheme not in (
            "postgres",
            "postgresql",
        ):
            raise ValueError("A PostgreSQL connection URL is required.")
        if self.database_auth_mode not in ("password", "managed-identity"):
            raise ValueError("DATABASE_AUTH_MODE must be password or managed-identity.")
        if self.database_tls_mode not in ("disable", "require", "verify-full"):
            raise ValueError("DATABASE_TLS_MODE must be disable, require, or verify-full.")
        configured_sslmode = parse_qs(database.query).get("sslmode", [])
        if configured_sslmode and configured_sslmode != [self.database_tls_mode]:
            raise ValueError("DATABASE_TLS_MODE conflicts with DATABASE_URL sslmode.")
        configured_sslrootcert = parse_qs(database.query).get("sslrootcert", [])
        if configured_sslrootcert and configured_sslrootcert != [self.database_tls_root_cert]:
            raise ValueError("DATABASE_TLS_ROOT_CERT conflicts with DATABASE_URL sslrootcert.")
        if self.database_tls_mode == "verify-full":
            if self.database_tls_root_cert not in (
                "system",
                "/etc/ssl/certs/ca-certificates.crt",
            ):
                raise ValueError(
                    "Verify-full requires the system trust store or the container CA bundle."
                )
        elif self.database_tls_root_cert is not None:
            raise ValueError("DATABASE_TLS_ROOT_CERT requires DATABASE_TLS_MODE=verify-full.")
        if self.database_auth_mode == "managed-identity":
            if database.password or self.database_password:
                raise ValueError(
                    "Managed identity database authentication cannot include a password."
                )
            if not database.username:
                raise ValueError(
                    "Managed identity database authentication requires a database user."
                )
        if self.database_password and database.password:
            raise ValueError("Configure the database password once, not in two settings.")
        if (
            self.database_pool_min_size < 0
            or self.database_pool_max_size < 2
            or self.database_pool_min_size > self.database_pool_max_size
            or self.database_pool_max_size > 32
            or self.database_pool_timeout_seconds <= 0
            or not 60 <= self.database_connection_max_lifetime_seconds <= 3000
        ):
            raise ValueError("The PostgreSQL pool bounds are invalid.")
        if self.host_mode not in ("local", "hosted"):
            raise ValueError("WORKFLOW_HOST must be local or hosted.")
        if self.host_mode == "local":
            if self.checkpoint_root is None or not str(self.checkpoint_root):
                raise ValueError("A local checkpoint root is required.")
        else:
            _foundry_endpoint(
                self.hosted_workflow_endpoint,
                "/responses",
                "HOSTED_WORKFLOW_ENDPOINT",
            )
            _foundry_endpoint(
                self.hosted_conversation_endpoint,
                "/conversations",
                "HOSTED_CONVERSATION_ENDPOINT",
            )
            if self.hosted_workflow_scope != "https://ai.azure.com/.default":
                raise ValueError("HOSTED_WORKFLOW_SCOPE must be https://ai.azure.com/.default.")
            try:
                object.__setattr__(
                    self,
                    "api_managed_identity_client_id",
                    str(UUID(self.api_managed_identity_client_id or "")),
                )
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError(
                    "Hosted mode requires the API managed identity client UUID."
                ) from exc
            try:
                object.__setattr__(
                    self,
                    "hosted_service_principal_id",
                    str(UUID(self.hosted_service_principal_id or "")),
                )
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError("Hosted mode requires the hosted service principal UUID.") from exc
            if self.hosted_service_app_role != HOSTED_SERVICE_APP_ROLE:
                raise ValueError(f"HOSTED_SERVICE_APP_ROLE must be {HOSTED_SERVICE_APP_ROLE}.")
            if self.database_tls_mode != "verify-full":
                raise ValueError("Hosted mode requires PostgreSQL TLS verification.")
        if self.database_managed_identity_client_id:
            try:
                object.__setattr__(
                    self,
                    "database_managed_identity_client_id",
                    str(UUID(self.database_managed_identity_client_id)),
                )
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError("The database managed identity client ID must be a UUID.") from exc
        if self.telemetry_mode not in ("local", "azure-monitor"):
            raise ValueError("TELEMETRY_MODE must be local or azure-monitor.")
        if self.telemetry_mode == "azure-monitor" and (
            not isinstance(self.applicationinsights_connection_string, str)
            or not self.applicationinsights_connection_string.strip()
        ):
            raise ValueError("APPLICATIONINSIGHTS_CONNECTION_STRING is required for azure-monitor.")
        for name, value in (
            ("AGENT_VERSION", self.agent_version),
            ("DEPLOYMENT_REVISION", self.deployment_revision),
        ):
            if (
                not isinstance(value, str)
                or not value
                or len(value) > 128
                or not all(character.isalnum() or character in "._:/-" for character in value)
            ):
                raise ValueError(f"{name} must be a privacy-safe identifier.")
        if self.acceptance_mode and self.host_mode != "hosted":
            raise ValueError("Acceptance controls may be enabled only in hosted mode.")
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

        def integer(name: str, default: str) -> int:
            try:
                return int(os.environ.get(name, default))
            except ValueError as exc:
                raise ValueError(f"{name} must be an integer.") from exc

        def number(name: str, default: str) -> float:
            try:
                return float(os.environ.get(name, default))
            except ValueError as exc:
                raise ValueError(f"{name} must be a number.") from exc

        enabled = os.environ.get("OBO_ENABLED", "false").lower()
        if enabled not in ("true", "false"):
            raise ValueError("OBO_ENABLED must be true or false.")
        acceptance_mode = os.environ.get("ACCEPTANCE_MODE", "false").lower()
        if acceptance_mode not in ("true", "false"):
            raise ValueError("ACCEPTANCE_MODE must be true or false.")
        host_mode = os.environ.get("WORKFLOW_HOST", "")
        if not host_mode:
            raise ValueError("WORKFLOW_HOST must explicitly select local or hosted.")
        checkpoint_root = os.environ.get("CHECKPOINT_ROOT")
        if host_mode == "local" and not checkpoint_root:
            raise ValueError("CHECKPOINT_ROOT is required.")
        database_url = os.environ.get("DATABASE_URL", "")
        database_query = parse_qs(urlsplit(database_url).query)
        database_tls_mode = (
            os.environ.get("DATABASE_TLS_MODE") or database_query.get("sslmode", ["disable"])[0]
        )
        configured_root_cert = os.environ.get("DATABASE_TLS_ROOT_CERT")
        libpq_root_cert = os.environ.get("PGSSLROOTCERT")
        if configured_root_cert and libpq_root_cert and configured_root_cert != libpq_root_cert:
            raise ValueError("DATABASE_TLS_ROOT_CERT conflicts with PGSSLROOTCERT.")
        return cls(
            tenant_id=os.environ.get("ENTRA_TENANT_ID", ""),
            api_client_id=os.environ.get("ENTRA_API_CLIENT_ID", ""),
            database_url=database_url,
            checkpoint_root=Path(checkpoint_root) if checkpoint_root else None,
            api_app_id_uri=os.environ.get("ENTRA_API_APP_ID_URI") or None,
            cors_origins=values("CORS_ORIGINS"),
            host_mode=host_mode,
            hosted_workflow_endpoint=os.environ.get("HOSTED_WORKFLOW_ENDPOINT") or None,
            hosted_conversation_endpoint=os.environ.get("HOSTED_CONVERSATION_ENDPOINT") or None,
            hosted_workflow_scope=os.environ.get("HOSTED_WORKFLOW_SCOPE") or None,
            api_managed_identity_client_id=os.environ.get("API_MANAGED_IDENTITY_CLIENT_ID") or None,
            hosted_service_principal_id=os.environ.get("HOSTED_SERVICE_PRINCIPAL_ID") or None,
            hosted_service_app_role=os.environ.get("HOSTED_SERVICE_APP_ROLE") or None,
            database_auth_mode=os.environ.get("DATABASE_AUTH_MODE", "password"),
            database_password=os.environ.get("DATABASE_PASSWORD") or None,
            database_managed_identity_client_id=os.environ.get(
                "DATABASE_MANAGED_IDENTITY_CLIENT_ID"
            )
            or None,
            database_tls_mode=database_tls_mode,
            database_tls_root_cert=(
                configured_root_cert
                or libpq_root_cert
                or database_query.get("sslrootcert", [None])[0]
                or ("system" if database_tls_mode == "verify-full" else None)
            ),
            database_pool_min_size=integer("DATABASE_POOL_MIN_SIZE", "1"),
            database_pool_max_size=integer("DATABASE_POOL_MAX_SIZE", "8"),
            database_pool_timeout_seconds=number("DATABASE_POOL_TIMEOUT_SECONDS", "5"),
            database_connection_max_lifetime_seconds=number(
                "DATABASE_CONNECTION_MAX_LIFETIME_SECONDS", "2700"
            ),
            obo_enabled=enabled == "true",
            obo_client_secret=os.environ.get("ENTRA_API_CLIENT_SECRET") or None,
            obo_allowed_scopes=values("OBO_ALLOWED_SCOPES"),
            telemetry_mode=os.environ.get("TELEMETRY_MODE", "local"),
            applicationinsights_connection_string=os.environ.get(
                "APPLICATIONINSIGHTS_CONNECTION_STRING"
            )
            or None,
            agent_version=os.environ.get("AGENT_VERSION", "0.1.0"),
            deployment_revision=os.environ.get("DEPLOYMENT_REVISION", "local-unversioned"),
            acceptance_mode=acceptance_mode == "true",
        )
