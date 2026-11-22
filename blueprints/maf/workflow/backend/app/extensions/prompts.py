import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path


_ASSET_PART = re.compile(r"^[a-z][a-z0-9_-]*$")
_VERSION = re.compile(r"^v[1-9][0-9]*$")


@dataclass(frozen=True)
class PromptAsset:
    name: str
    version: str
    instructions: str
    content_sha256: str


def load_prompt_asset(name: str, version: str, path: Path) -> PromptAsset:
    if not _ASSET_PART.fullmatch(name):
        raise ValueError("Prompt asset names must be lowercase identifiers.")
    if not _VERSION.fullmatch(version):
        raise ValueError("Prompt asset versions must use an explicit vN identifier.")
    if path.name != f"{name}.{version}.md":
        raise ValueError("The prompt path must match its declared name and version.")
    raw_content = path.read_bytes()
    instructions = raw_content.decode("utf-8").strip()
    if not instructions:
        raise ValueError("Prompt assets must not be empty.")
    return PromptAsset(
        name=name,
        version=version,
        instructions=instructions,
        content_sha256=sha256(raw_content).hexdigest(),
    )
