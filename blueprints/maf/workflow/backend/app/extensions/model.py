from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSelection:
    provider_id: str
    model_id: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.provider_id, str)
            or not self.provider_id
            or self.provider_id != self.provider_id.strip()
        ):
            raise ValueError("A non-empty, whitespace-trimmed model provider is required.")
        if (
            not isinstance(self.model_id, str)
            or not self.model_id
            or self.model_id != self.model_id.strip()
        ):
            raise ValueError("A non-empty, whitespace-trimmed model identifier is required.")
