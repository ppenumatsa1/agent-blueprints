import base64
import binascii
import json
import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.errors import InvalidInput
from app.domain.models import CaseHistory, DurableActivity


MAX_CURSOR_LENGTH = 512
MAX_ACTIVITY_ID = 2**63 - 1
_CURSOR_CHARS = re.compile(r"[A-Za-z0-9_-]+")


@dataclass(frozen=True)
class CursorPosition:
    created_at: datetime
    row_id: UUID | int


@dataclass(frozen=True)
class HistoryPage:
    items: tuple[CaseHistory, ...]
    next_cursor: str | None


@dataclass(frozen=True)
class ActivityPage:
    items: tuple[DurableActivity, ...]
    next_cursor: str | None


def _encode_cursor(kind: str, created_at: datetime, row_id: UUID | int, status: str | None):
    value = {
        "version": 1,
        "kind": kind,
        "created_at": created_at.isoformat(),
        "id": str(row_id),
        "status": status,
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None, kind: str, status: str | None) -> CursorPosition | None:
    if cursor is None:
        return None
    if (
        not isinstance(cursor, str)
        or not cursor
        or len(cursor) > MAX_CURSOR_LENGTH
        or not _CURSOR_CHARS.fullmatch(cursor)
    ):
        raise InvalidInput("The history cursor is invalid.")
    try:
        encoded = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        value = json.loads(encoded)
        if (
            not isinstance(value, dict)
            or set(value) != {"version", "kind", "created_at", "id", "status"}
            or value["version"] != 1
            or value["kind"] != kind
            or value["status"] != status
            or not isinstance(value["created_at"], str)
            or not isinstance(value["id"], str)
        ):
            raise ValueError
        created_at = datetime.fromisoformat(value["created_at"])
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError
        if kind == "history":
            row_id: UUID | int = UUID(value["id"])
            if str(row_id) != value["id"]:
                raise ValueError
        else:
            if not re.fullmatch(r"[1-9][0-9]{0,18}", value["id"]):
                raise ValueError
            row_id = int(value["id"])
            if row_id > MAX_ACTIVITY_ID:
                raise ValueError
        return CursorPosition(created_at, row_id)
    except (
        binascii.Error,
        UnicodeDecodeError,
        json.JSONDecodeError,
        OverflowError,
        TypeError,
        ValueError,
    ) as exc:
        raise InvalidInput("The history cursor is invalid.") from exc


def decode_history_cursor(cursor: str | None, status: str | None) -> CursorPosition | None:
    return _decode_cursor(cursor, "history", status)


def decode_activity_cursor(cursor: str | None) -> CursorPosition | None:
    return _decode_cursor(cursor, "activity", None)


def history_page(items: list[CaseHistory], has_more: bool, status: str | None) -> HistoryPage:
    next_cursor = (
        _encode_cursor("history", items[-1].created_at, items[-1].id, status)
        if has_more and items
        else None
    )
    return HistoryPage(tuple(items), next_cursor)


def activity_page(items: list[DurableActivity], has_more: bool) -> ActivityPage:
    next_cursor = (
        _encode_cursor("activity", items[-1].created_at, items[-1].cursor_id, None)
        if has_more and items
        else None
    )
    return ActivityPage(tuple(items), next_cursor)
