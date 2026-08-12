from __future__ import annotations

from ..domain import Document, NotFoundError
from .ports import DocumentRepository, ObjectStorage


class DocumentService:
    def __init__(self, repository: DocumentRepository, storage: ObjectStorage, prefix: str):
        self._repository, self._storage, self._prefix = repository, storage, prefix

    def create(self, payload: dict):
        required = [key for key in ("folio", "name", "document_type") if not isinstance(payload.get(key), str) or not payload[key].strip()]
        if required:
            raise ValueError(f"required non-empty fields: {', '.join(required)}")
        return self._repository.create(payload)

    def get(self, identifier: str) -> Document:
        return self._repository.get(identifier)

    def list(self) -> list[Document]:
        return self._repository.list()

    def update(self, identifier: str, changes: dict) -> Document:
        return self._repository.update(identifier, changes)

    def upload(self, identifier: str, body: bytes, content_type: str):
        doc = self._repository.get(identifier)
        if not body:
            raise ValueError("file content cannot be empty")
        key = f"{self._prefix}/{doc.id}" if self._prefix else doc.id
        self._storage.put(key, body, content_type)
        return self._repository.attach_content(identifier, key, content_type, len(body))

    def download(self, identifier: str) -> tuple[Document, bytes]:
        doc = self._repository.get(identifier)
        if not doc.storage_key:
            raise NotFoundError("document content not found")
        return doc, self._storage.get(doc.storage_key)

    def signed_download(self, identifier: str, expires_in: int = 300) -> str | None:
        doc = self._repository.get(identifier)
        if not doc.storage_key:
            raise NotFoundError("document content not found")
        return self._storage.signed_get(doc.storage_key, expires_in)

    def delete(self, identifier: str):
        doc = self._repository.get(identifier)
        # Delete from S3 first: DB metadata remains available if object deletion fails.
        if doc.storage_key:
            self._storage.delete(doc.storage_key)
        return self._repository.delete(identifier)
