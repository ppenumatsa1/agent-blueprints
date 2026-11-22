import os
import sys
import time
from pathlib import Path
from uuid import UUID

from app.infrastructure.store import PostgresStore
from examples.external_effect_boundary import ExternalEffectAction
from tests.test_external_effect import DurableDestination, FixtureAuthorizer


def main():
    case_id, database, marker, barrier = sys.argv[1:]

    def wait():
        Path(marker).write_text("reached", encoding="utf-8")
        while True:
            time.sleep(1)

    class PausingDestination(DurableDestination):
        def send(self, request, *, timeout_seconds):
            super().send(request, timeout_seconds=timeout_seconds)
            if barrier == "after-effect":
                wait()

    class PausingAction:
        def apply(self, connection, case):
            ExternalEffectAction(
                FixtureAuthorizer(),
                PausingDestination(database),
                operation="fixture-v1",
                destination_id="fixture",
            ).apply(connection, case)
            if barrier == "after-ack":
                wait()

    store = PostgresStore(os.environ["MAF_TEST_DATABASE_URL"])
    store.apply_once(UUID(case_id), True, PausingAction())


if __name__ == "__main__":
    main()
