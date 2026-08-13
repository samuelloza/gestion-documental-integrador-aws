from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Document:
    id: str
    folio: str
    name: str
    document_type: str
    status: str
    created_at: str
    updated_at: str
    storage_key: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None

    def public(self) -> dict:
        return asdict(self)


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass
