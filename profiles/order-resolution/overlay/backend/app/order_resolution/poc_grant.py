"""Issue a protected synthetic decision grant as the existing Entra PostgreSQL owner."""

import argparse
import re
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import psycopg
from azure.identity import AzureCliCredential

from app.infrastructure.database import POSTGRES_TOKEN_SCOPE
from app.order_resolution.durability import Decision


def issue_grant(
    database_url: str,
    *,
    case_id: UUID,
    proposal_version: int,
    handle_digest: str,
    action: str,
    destination_id: str,
    decision: Decision,
) -> None:
    database = urlsplit(database_url)
    query = parse_qs(database.query, keep_blank_values=True)
    if (
        database.scheme != "postgresql"
        or not database.username
        or database.password is not None
        or not (database.hostname or "").endswith(".postgres.database.azure.com")
        or not database.path.strip("/")
        or database.fragment
        or set(query) - {"sslmode", "sslrootcert"}
        or query.get("sslmode") != ["verify-full"]
        or query.get("sslrootcert") != ["system"]
    ):
        raise ValueError("Use the explicit passwordless POC PostgreSQL URL with verified TLS.")
    if proposal_version < 1 or not re.fullmatch(r"[a-f0-9]{64}", handle_digest):
        raise ValueError("An exact proposal version and SHA-256 approval handle are required.")

    token = AzureCliCredential().get_token(POSTGRES_TOKEN_SCOPE).token
    with psycopg.connect(database_url, password=token, connect_timeout=5) as connection:
        connection.execute("SET LOCAL statement_timeout = '10s'")
        permitted = connection.execute(
            "SELECT ors_poc.issue_grant(%s, %s, %s, %s, %s, %s, %s)",
            (
                case_id,
                proposal_version,
                handle_digest,
                action,
                destination_id,
                decision.value,
                connection.info.host,
            ),
        ).fetchone()
        if permitted != (True,):
            raise PermissionError("The exact synthetic approval grant was denied.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--case-id", required=True, type=UUID)
    parser.add_argument("--proposal-version", required=True, type=int)
    parser.add_argument("--handle-digest", required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--destination-id", required=True)
    parser.add_argument("--decision", required=True, choices=[item.value for item in Decision])
    arguments = vars(parser.parse_args())
    arguments["decision"] = Decision(arguments["decision"])
    issue_grant(**arguments)


if __name__ == "__main__":
    main()
