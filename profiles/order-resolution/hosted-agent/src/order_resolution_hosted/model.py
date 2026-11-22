import os

from agent_framework_foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential


def create_chat_client() -> FoundryChatClient:
    """Create the public Foundry client from injected deployment configuration."""

    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "").strip()
    model = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "").strip()
    if not endpoint or not model:
        raise ValueError(
            "FOUNDRY_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME are required."
        )
    return FoundryChatClient(
        project_endpoint=endpoint,
        model=model,
        credential=DefaultAzureCredential(),
    )
