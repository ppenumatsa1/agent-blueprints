import os
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import ANY, patch

from app.composition import create_app
from app.config import Settings
from app.domain.errors import HostedWorkflowError
from app.infrastructure.database import (
    BoundedConnectionPool,
    DatabaseConnectionOptions,
    DatabaseConnector,
    POSTGRES_TOKEN_SCOPE,
)
from app.infrastructure.store import PostgresStore


TENANT = "10000000-0000-4000-8000-000000000001"
API = "20000000-0000-4000-8000-000000000002"
API_IDENTITY = "30000000-0000-4000-8000-000000000003"
HOSTED_SERVICE = "40000000-0000-4000-8000-000000000004"


class StaticTokenProvider:
    def __init__(self, value: str = "managed-identity-token"):
        self.value = value
        self.scopes = []

    def get_token(self, scope: str) -> str:
        self.scopes.append(scope)
        return self.value


def hosted_settings() -> Settings:
    return Settings(
        TENANT,
        API,
        "postgresql://runtime@database.postgres.database.azure.com/app?sslmode=verify-full",
        None,
        host_mode="hosted",
        hosted_workflow_endpoint=(
            "https://example.test/agents/order/endpoint/responses?api-version=v1"
        ),
        hosted_conversation_endpoint=("https://example.test/openai/conversations?api-version=v1"),
        hosted_workflow_scope="https://ai.azure.com/.default",
        api_managed_identity_client_id=API_IDENTITY,
        hosted_service_principal_id=HOSTED_SERVICE,
        hosted_service_app_role="Hosted.Workflow.Invoke",
        database_auth_mode="managed-identity",
        database_tls_mode="verify-full",
        database_tls_root_cert="system",
    )


class CloudConfigurationTests(unittest.TestCase):
    def test_hosted_mode_is_explicit_and_requires_tls_and_managed_identity(self):
        settings = hosted_settings()
        self.assertEqual(settings.host_mode, "hosted")
        self.assertIsNone(settings.checkpoint_root)
        self.assertNotIn("password", repr(settings))
        with self.assertRaises(ValueError):
            replace(settings, database_tls_mode="require")
        with self.assertRaises(ValueError):
            replace(settings, database_tls_root_cert=None)
        with self.assertRaises(ValueError):
            replace(settings, database_tls_root_cert="untrusted.pem")
        with self.assertRaises(ValueError):
            replace(
                settings,
                database_auth_mode="managed-identity",
                database_password="secret",
            )
        with self.assertRaises(ValueError):
            replace(settings, hosted_workflow_endpoint="http://agent.example.test")
        with self.assertRaises(ValueError):
            replace(settings, hosted_conversation_endpoint=None)
        with self.assertRaisesRegex(ValueError, "Hosted.Workflow.Invoke"):
            replace(settings, hosted_service_app_role="Workflow.HostedService")

    def test_managed_identity_database_token_is_separate_and_tls_verified(self):
        provider = StaticTokenProvider("database-managed-identity-token")
        connector = DatabaseConnector(
            DatabaseConnectionOptions(
                "postgresql://runtime@database.postgres.database.azure.com/app",
                "managed-identity",
                None,
                API_IDENTITY,
                "verify-full",
                "system",
            ),
            provider,
        )
        with patch("app.infrastructure.database.psycopg.connect") as connect:
            connector.connect()
        self.assertEqual(provider.scopes, [POSTGRES_TOKEN_SCOPE])
        connect.assert_called_once_with(
            "postgresql://runtime@database.postgres.database.azure.com/app",
            row_factory=ANY,
            sslmode="verify-full",
            sslrootcert="system",
            password="database-managed-identity-token",
        )

    def test_store_composition_defers_managed_identity_until_connection_open(self):
        provider = StaticTokenProvider("database-managed-identity-token")
        connection = SimpleNamespace(
            closed=False,
            commit=lambda: None,
            rollback=lambda: None,
            close=lambda: None,
        )
        with patch(
            "app.infrastructure.database.psycopg.connect",
            return_value=connection,
        ) as connect:
            store = PostgresStore.from_settings(
                hosted_settings(),
                token_provider=provider,
            )
            self.assertEqual(provider.scopes, [])
            connect.assert_not_called()
            with store.connect():
                pass
        self.assertEqual(provider.scopes, [POSTGRES_TOKEN_SCOPE])
        connect.assert_called_once()

    def test_libpq_system_root_and_url_query_match_agent_b_runtime_contract(self):
        environment = {
            "ENTRA_TENANT_ID": TENANT,
            "ENTRA_API_CLIENT_ID": API,
            "DATABASE_URL": (
                "postgresql://runtime@database.postgres.database.azure.com/app"
                "?sslmode=verify-full&sslrootcert=system"
            ),
            "WORKFLOW_HOST": "hosted",
            "HOSTED_WORKFLOW_ENDPOINT": (
                "https://example.test/agents/order/endpoint/responses?api-version=v1"
            ),
            "HOSTED_CONVERSATION_ENDPOINT": (
                "https://example.test/openai/conversations?api-version=v1"
            ),
            "HOSTED_WORKFLOW_SCOPE": "https://ai.azure.com/.default",
            "API_MANAGED_IDENTITY_CLIENT_ID": API_IDENTITY,
            "HOSTED_SERVICE_PRINCIPAL_ID": HOSTED_SERVICE,
            "HOSTED_SERVICE_APP_ROLE": "Hosted.Workflow.Invoke",
            "DATABASE_AUTH_MODE": "managed-identity",
            "PGSSLROOTCERT": "system",
            "AGENT_VERSION": "2",
            "HOSTED_AGENT_VERSION": "3",
        }
        with patch.dict(os.environ, environment, clear=True):
            settings = Settings.from_environment()
            store = PostgresStore.from_settings(settings)
        self.assertEqual(settings.agent_version, "3")
        self.assertEqual(settings.database_tls_mode, "verify-full")
        self.assertEqual(settings.database_tls_root_cert, "system")
        self.assertEqual(store._connector.options.tls_mode, "verify-full")
        self.assertEqual(store._connector.options.tls_root_cert, "system")

    def test_postgres_pool_has_a_hard_borrower_bound(self):
        class Connection:
            closed = False

            def commit(self):
                pass

            def rollback(self):
                pass

            def close(self):
                self.closed = True

        pool = BoundedConnectionPool(
            Connection,
            min_size=0,
            max_size=1,
            timeout_seconds=0.01,
            max_lifetime_seconds=60,
        )
        with pool.connection():
            with self.assertRaisesRegex(TimeoutError, "pool is exhausted"):
                with pool.connection():
                    self.fail("A second borrower exceeded the pool maximum.")
        pool.close()

    def test_pool_reports_only_physical_open_replacement_and_checkout_failure(self):
        class Connection:
            def __init__(self):
                self.closed = False

            def commit(self):
                pass

            def rollback(self):
                pass

            def close(self):
                self.closed = True

        reasons = []
        failures = []

        def open_connection(reason):
            reasons.append(reason)
            return Connection()

        pool = BoundedConnectionPool(
            Connection,
            min_size=1,
            max_size=1,
            timeout_seconds=0.01,
            max_lifetime_seconds=60,
            open_connection=open_connection,
            checkout_failure=failures.append,
        )
        with pool.connection() as first:
            with self.assertRaisesRegex(TimeoutError, "pool is exhausted"):
                with pool.connection():
                    self.fail("A second borrower exceeded the pool maximum.")
        first.closed = True
        with pool.connection():
            pass
        self.assertEqual(reasons, ["initial", "replacement"])
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], TimeoutError)
        pool.close()

    def test_hosted_composition_fails_closed_without_agent_a_adapter(self):
        components = SimpleNamespace(
            action=object(),
            rules=object(),
            policy=object(),
            workflow_factory=object(),
            initialize=lambda _store: None,
        )
        with self.assertRaisesRegex(
            HostedWorkflowError,
            "integrated Agent A Responses workflow adapter",
        ):
            create_app(
                hosted_settings(),
                components,
                store=object(),
                identity=object(),
            )


if __name__ == "__main__":
    unittest.main()
