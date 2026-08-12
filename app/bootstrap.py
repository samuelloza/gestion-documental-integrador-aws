from __future__ import annotations

from .application import DocumentService
from .config import Settings
from .infrastructure.repositories import PostgresDocuments, SQLiteDocuments
from .infrastructure.storage import LocalObjectStorage, S3ObjectStorage


def build_service(settings: Settings | None = None) -> DocumentService:
    settings = settings or Settings.from_env()
    if settings.metadata_backend == "sqlite":
        repository = SQLiteDocuments(settings.data_dir / "documents.db")
    elif settings.metadata_backend == "postgres":
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is required for METADATA_BACKEND=postgres")
        repository = PostgresDocuments(settings.database_url)
    else:
        raise RuntimeError("METADATA_BACKEND must be sqlite or postgres")
    if settings.storage_backend == "local":
        storage = LocalObjectStorage(settings.data_dir / "objects")
    elif settings.storage_backend == "s3":
        if not settings.s3_bucket:
            raise RuntimeError("S3_BUCKET is required for STORAGE_BACKEND=s3")
        storage = S3ObjectStorage(settings.s3_bucket, settings.aws_region)
    else:
        raise RuntimeError("STORAGE_BACKEND must be local or s3")
    return DocumentService(repository, storage, settings.s3_prefix)
