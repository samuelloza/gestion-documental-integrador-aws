from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import sqlite3
import uuid

from ..domain import ConflictError, Document, NotFoundError, utc_now


class SQLiteDocuments:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS documents (
              id TEXT PRIMARY KEY, folio TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
              document_type TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL, storage_key TEXT, content_type TEXT, size_bytes INTEGER
            )""")

    def _connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _row(row: sqlite3.Row) -> Document:
        return Document(**dict(row))

    def create(self, payload: dict) -> Document:
        now, identifier = utc_now(), str(uuid.uuid4())
        doc = Document(identifier, payload["folio"], payload["name"], payload["document_type"],
                       payload.get("status", "PENDING_UPLOAD"), now, now)
        try:
            with self._connect() as db:
                db.execute("INSERT INTO documents VALUES (:id,:folio,:name,:document_type,:status,:created_at,:updated_at,:storage_key,:content_type,:size_bytes)", asdict(doc))
        except sqlite3.IntegrityError as exc:
            raise ConflictError("folio already exists") from exc
        return doc

    def get(self, identifier: str) -> Document:
        with self._connect() as db:
            row = db.execute("SELECT * FROM documents WHERE id = ?", (identifier,)).fetchone()
        if row is None:
            raise NotFoundError("document not found")
        return self._row(row)

    def list(self) -> list[Document]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
        return [self._row(row) for row in rows]

    def update(self, identifier: str, changes: dict) -> Document:
        allowed = {key: value for key, value in changes.items() if key in {"name", "document_type", "status"}}
        if not allowed:
            return self.get(identifier)
        allowed["updated_at"] = utc_now()
        assignments = ", ".join(f"{key} = :{key}" for key in allowed)
        allowed["id"] = identifier
        with self._connect() as db:
            result = db.execute(f"UPDATE documents SET {assignments} WHERE id = :id", allowed)
        if result.rowcount == 0:
            raise NotFoundError("document not found")
        return self.get(identifier)

    def attach_content(self, identifier: str, key: str, content_type: str, size: int) -> Document:
        with self._connect() as db:
            result = db.execute("UPDATE documents SET storage_key=?, content_type=?, size_bytes=?, status=?, updated_at=? WHERE id=?", (key, content_type, size, "UPLOADED", utc_now(), identifier))
        if result.rowcount == 0:
            raise NotFoundError("document not found")
        return self.get(identifier)

    def delete(self, identifier: str) -> Document:
        doc = self.get(identifier)
        with self._connect() as db:
            db.execute("DELETE FROM documents WHERE id = ?", (identifier,))
        return doc


class PostgresDocuments:
    def __init__(self, database_url: str):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("Install requirements.txt to use METADATA_BACKEND=postgres") from exc
        self._psycopg, self._dict_row, self._database_url = psycopg, dict_row, database_url
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS documents (
              id UUID PRIMARY KEY, folio TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
              document_type TEXT NOT NULL, status TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL,
              updated_at TIMESTAMPTZ NOT NULL, storage_key TEXT, content_type TEXT, size_bytes BIGINT
            )""")

    def _connect(self):
        return self._psycopg.connect(self._database_url)

    @staticmethod
    def _doc(row: dict) -> Document:
        return Document(**row)

    def create(self, payload: dict) -> Document:
        now, identifier = utc_now(), str(uuid.uuid4())
        doc = Document(identifier, payload["folio"], payload["name"], payload["document_type"], payload.get("status", "PENDING_UPLOAD"), now, now)
        try:
            with self._connect() as db:
                db.execute("""INSERT INTO documents VALUES
                  (%(id)s, %(folio)s, %(name)s, %(document_type)s, %(status)s, %(created_at)s,
                   %(updated_at)s, %(storage_key)s, %(content_type)s, %(size_bytes)s)""", asdict(doc))
        except self._psycopg.errors.UniqueViolation as exc:
            raise ConflictError("folio already exists") from exc
        return doc

    def get(self, identifier: str) -> Document:
        with self._connect() as db, db.cursor(row_factory=self._dict_row) as cursor:
            cursor.execute("SELECT * FROM documents WHERE id = %s", (identifier,))
            row = cursor.fetchone()
        if row is None:
            raise NotFoundError("document not found")
        return self._doc(row)

    def list(self) -> list[Document]:
        with self._connect() as db, db.cursor(row_factory=self._dict_row) as cursor:
            cursor.execute("SELECT * FROM documents ORDER BY created_at DESC")
            return [self._doc(row) for row in cursor.fetchall()]

    def update(self, identifier: str, changes: dict) -> Document:
        allowed = {key: value for key, value in changes.items() if key in {"name", "document_type", "status"}}
        if not allowed:
            return self.get(identifier)
        allowed["updated_at"] = utc_now()
        allowed["id"] = identifier
        assignments = ", ".join(f"{key} = %({key})s" for key in allowed if key != "id")
        with self._connect() as db:
            result = db.execute(f"UPDATE documents SET {assignments} WHERE id = %(id)s", allowed)
        if result.rowcount == 0:
            raise NotFoundError("document not found")
        return self.get(identifier)

    def attach_content(self, identifier: str, key: str, content_type: str, size: int) -> Document:
        with self._connect() as db:
            result = db.execute("""UPDATE documents SET storage_key=%s, content_type=%s, size_bytes=%s,
              status=%s, updated_at=%s WHERE id=%s""", (key, content_type, size, "UPLOADED", utc_now(), identifier))
        if result.rowcount == 0:
            raise NotFoundError("document not found")
        return self.get(identifier)

    def delete(self, identifier: str) -> Document:
        with self._connect() as db, db.cursor(row_factory=self._dict_row) as cursor:
            cursor.execute("DELETE FROM documents WHERE id = %s RETURNING *", (identifier,))
            row = cursor.fetchone()
        if row is None:
            raise NotFoundError("document not found")
        return self._doc(row)
