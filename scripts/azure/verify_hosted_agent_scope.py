#!/usr/bin/env python3
"""Derive and verify the documented Foundry agent-level RBAC scope."""

from __future__ import annotations

import argparse
import json
import re


class ScopeEvidenceError(ValueError):
    """Raised when an input cannot identify one exact Foundry agent scope."""


PROJECT_PATTERN = re.compile(
    r"^/subscriptions/[^/]+/resourceGroups/[^/]+/providers/"
    r"Microsoft\.CognitiveServices/accounts/[^/]+/projects/[^/]+$",
    re.IGNORECASE,
)
AGENT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def derive_scope(project_id: str, agent_name: str) -> str:
    project = project_id.rstrip("/")
    if not PROJECT_PATTERN.fullmatch(project):
        raise ScopeEvidenceError("Foundry project ID is not a canonical ARM project ID.")
    if not AGENT_NAME_PATTERN.fullmatch(agent_name):
        raise ScopeEvidenceError("Hosted agent name is not one safe ARM path segment.")
    return f"{project}/agents/{agent_name}"


def verify_exact_scope(candidate: str, project_id: str, agent_name: str) -> str:
    expected = derive_scope(project_id, agent_name)
    if candidate.rstrip("/").lower() != expected.lower():
        raise ScopeEvidenceError(
            "RBAC scope is not the documented exact Foundry agent scope."
        )
    return expected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--agent-name", required=True)
    parser.add_argument("--candidate-scope")
    arguments = parser.parse_args()
    try:
        scope = derive_scope(arguments.project_id, arguments.agent_name)
        if arguments.candidate_scope:
            scope = verify_exact_scope(
                arguments.candidate_scope,
                arguments.project_id,
                arguments.agent_name,
            )
    except ScopeEvidenceError as error:
        parser.error(str(error))
    print(
        json.dumps(
            {
                "scope": scope,
                "source": "official-foundry-agent-scope",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
