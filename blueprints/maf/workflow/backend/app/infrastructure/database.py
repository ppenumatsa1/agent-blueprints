import os
import queue
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import parse_qs, urlsplit

import psycopg
from psycopg.rows import dict_row


POSTGRES_TOKEN_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"


class TokenProvider(Protocol):
    def get_token(self, scope: str) -> str: ...


class DefaultAzureCredentialTokenProvider:
    """Create the Azure credential only when the first token is requested."""

    def __init__(self, managed_identity_client_id: str | None):
        self._client_id = managed_identity_client_id
        self._credential = None
        self._lock = threading.Lock()

    def get_token(self, scope: str) -> str:
        if self._credential is None:
            with self._lock:
                if self._credential is None:
                    from azure.identity import DefaultAzureCredential

                    self._credential = DefaultAzureCredential(
                        managed_identity_client_id=self._client_id,
                        exclude_interactive_browser_credential=True,
                    )
        return self._credential.get_token(scope).token


@dataclass(frozen=True)
class DatabaseConnectionOptions:
    dsn: str
    auth_mode: str = "password"
    password: str | None = None
    managed_identity_client_id: str | None = None
    tls_mode: str | None = None
    tls_root_cert: str | None = None


class DatabaseConnector:
    def __init__(
        self,
        options: DatabaseConnectionOptions,
        token_provider: TokenProvider | None = None,
    ):
        self.options = options
        self.token_provider = token_provider

    def connect(self, *, dict_rows: bool = True):
        password = self.options.password
        if self.options.auth_mode == "managed-identity":
            provider = self.token_provider or DefaultAzureCredentialTokenProvider(
                self.options.managed_identity_client_id
            )
            self.token_provider = provider
            password = provider.get_token(POSTGRES_TOKEN_SCOPE)
        kwargs = {}
        if self.options.tls_mode:
            kwargs["sslmode"] = self.options.tls_mode
        if self.options.tls_root_cert:
            kwargs["sslrootcert"] = self.options.tls_root_cert
        if dict_rows:
            kwargs["row_factory"] = dict_row
        if password:
            kwargs["password"] = password
        return psycopg.connect(self.options.dsn, **kwargs)


class BoundedConnectionPool:
    """Small synchronous pool with bounded borrowers and expiring connections."""

    def __init__(
        self,
        factory: Callable[[], psycopg.Connection],
        *,
        min_size: int,
        max_size: int,
        timeout_seconds: float,
        max_lifetime_seconds: float,
        open_connection: Callable[[str], psycopg.Connection] | None = None,
        checkout_failure: Callable[[BaseException], None] | None = None,
    ):
        self._factory = factory
        self._open_connection = open_connection
        self._checkout_failure = checkout_failure
        self._min_size = min_size
        self._timeout = timeout_seconds
        self._max_lifetime = max_lifetime_seconds
        self._available: queue.LifoQueue[tuple[psycopg.Connection, float]] = queue.LifoQueue()
        self._borrowers = threading.BoundedSemaphore(max_size)
        self._opened = False
        self._closed = False
        self._lock = threading.Lock()

    def _create(self, reason: str) -> psycopg.Connection:
        if self._open_connection is not None:
            return self._open_connection(reason)
        return self._factory()

    def open(self) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("The PostgreSQL pool is closed.")
            if self._opened:
                return
            created = []
            try:
                for _ in range(self._min_size):
                    created.append((self._create("initial"), time.monotonic()))
            except BaseException:
                for connection, _ in created:
                    connection.close()
                raise
            for item in created:
                self._available.put(item)
            self._opened = True

    def _borrow(self) -> tuple[psycopg.Connection, float]:
        self.open()
        if not self._borrowers.acquire(timeout=self._timeout):
            error = TimeoutError("The PostgreSQL connection pool is exhausted.")
            if self._checkout_failure is not None:
                self._checkout_failure(error)
            raise error
        try:
            try:
                connection, created_at = self._available.get_nowait()
            except queue.Empty:
                return self._create("growth"), time.monotonic()
            if connection.closed or time.monotonic() - created_at >= self._max_lifetime:
                connection.close()
                return self._create("replacement"), time.monotonic()
            return connection, created_at
        except BaseException:
            self._borrowers.release()
            raise

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection]:
        connection, created_at = self._borrow()
        reusable = True
        try:
            yield connection
            connection.commit()
        except BaseException:
            reusable = False
            try:
                connection.rollback()
            finally:
                raise
        finally:
            expired = time.monotonic() - created_at >= self._max_lifetime
            if reusable and not connection.closed and not expired and not self._closed:
                self._available.put((connection, created_at))
            else:
                connection.close()
            self._borrowers.release()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            while True:
                try:
                    connection, _ = self._available.get_nowait()
                except queue.Empty:
                    break
                connection.close()


def connector_from_environment(dsn: str) -> DatabaseConnector:
    configured_tls = parse_qs(urlsplit(dsn).query).get("sslmode", ["disable"])[0]
    configured_root_cert = parse_qs(urlsplit(dsn).query).get("sslrootcert", [None])[0]
    tls_mode = os.environ.get("DATABASE_TLS_MODE", configured_tls)
    return DatabaseConnector(
        DatabaseConnectionOptions(
            dsn=dsn,
            auth_mode=os.environ.get("DATABASE_AUTH_MODE", "password"),
            password=os.environ.get("DATABASE_PASSWORD") or None,
            managed_identity_client_id=os.environ.get("DATABASE_MANAGED_IDENTITY_CLIENT_ID")
            or None,
            tls_mode=tls_mode,
            tls_root_cert=(
                os.environ.get("DATABASE_TLS_ROOT_CERT")
                or configured_root_cert
                or ("system" if tls_mode == "verify-full" else None)
            ),
        )
    )
