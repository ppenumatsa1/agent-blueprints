from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from agent_framework import SupportsChatGetResponse


@dataclass(frozen=True)
class ModelSelection:
    provider_id: str
    model_id: str

    def __post_init__(self) -> None:
        if not self.provider_id or self.provider_id != self.provider_id.strip():
            raise ValueError("A non-empty, whitespace-trimmed model provider is required.")
        if not self.model_id or self.model_id != self.model_id.strip():
            raise ValueError("A non-empty, whitespace-trimmed model identifier is required.")


class ModelClientFactory(Protocol):
    def __call__(self, selection: ModelSelection) -> SupportsChatGetResponse: ...


def select_chat_client(
    selection: ModelSelection,
    providers: Mapping[str, ModelClientFactory],
) -> SupportsChatGetResponse:
    factory = providers.get(selection.provider_id)
    if factory is None:
        raise ValueError(f"No model provider is registered for {selection.provider_id!r}.")
    client = factory(selection)
    if not isinstance(client, SupportsChatGetResponse):
        raise TypeError("The model provider must return a MAF chat client.")
    return client
