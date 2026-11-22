"""Verify hosted API composition without opening Azure or PostgreSQL connections."""

from app.composition import create_app
from app.config import Settings
from app.order_resolution.application import build_application
from app.order_resolution.persistence import OrderResolutionStore


settings = Settings(
    tenant_id="10000000-0000-4000-8000-000000000001",
    api_client_id="20000000-0000-4000-8000-000000000002",
    database_url=(
        "postgresql://runtime@database.postgres.database.azure.com/app"
        "?sslmode=verify-full&sslrootcert=system"
    ),
    checkpoint_root=None,
    host_mode="hosted",
    hosted_workflow_endpoint=(
        "https://project.services.ai.azure.com/api/projects/project/"
        "openai/responses?api-version=2025-11-15-preview"
    ),
    hosted_conversation_endpoint=(
        "https://project.services.ai.azure.com/api/projects/project/"
        "openai/conversations?api-version=2025-11-15-preview"
    ),
    hosted_workflow_scope="https://ai.azure.com/.default",
    api_managed_identity_client_id="30000000-0000-4000-8000-000000000003",
    hosted_service_principal_id="40000000-0000-4000-8000-000000000004",
    hosted_service_app_role="Hosted.Workflow.Invoke",
    database_auth_mode="managed-identity",
    database_managed_identity_client_id="30000000-0000-4000-8000-000000000003",
    database_tls_mode="verify-full",
    database_tls_root_cert="system",
)
store = object.__new__(OrderResolutionStore)
application = create_app(
    settings,
    build_application(),
    store=store,
    identity=object(),
)
host = application.state.service.host
if type(host).__module__ != "order_resolution_hosted.bridge":
    raise RuntimeError("Hosted API composition did not select the generated Responses bridge.")

print(f"{type(host).__module__}:{type(host).__name__}")
