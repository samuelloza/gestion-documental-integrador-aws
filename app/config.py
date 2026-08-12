from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    static_dir: Path
    storage_backend: str
    metadata_backend: str
    s3_bucket: str | None
    s3_prefix: str
    aws_region: str | None
    database_url: str | None
    bind_host: str = "127.0.0.1"
    auth_users_json: str | None = None
    cors_origin: str | None = None
    auth_mode: str = "basic"
    cognito_user_pool_id: str | None = None
    cognito_client_id: str | None = None

    @classmethod
    def from_env(cls, root: Path | None = None) -> "Settings":
        root = root or Path(__file__).resolve().parents[1]
        load_dotenv(root / ".env.local")
        load_dotenv(root / ".env")
        return cls(
            data_dir=Path(os.getenv("DATA_DIR", root / "data")),
            static_dir=root / "web",
            storage_backend=os.getenv("STORAGE_BACKEND", "local").lower(),
            metadata_backend=os.getenv("METADATA_BACKEND", "postgres").lower(),
            s3_bucket=os.getenv("S3_BUCKET") or None,
            s3_prefix=os.getenv("S3_PREFIX", "documents").strip("/"),
            aws_region=os.getenv("AWS_REGION") or None,
            database_url=os.getenv("DATABASE_URL") or None,
            bind_host=os.getenv("BIND_HOST", "127.0.0.1"),
            auth_users_json=os.getenv("AUTH_USERS_JSON") or None,
            cors_origin=os.getenv("CORS_ORIGIN") or None,
            auth_mode=os.getenv("AUTH_MODE", "basic").lower(),
            cognito_user_pool_id=os.getenv("COGNITO_USER_POOL_ID") or None,
            cognito_client_id=os.getenv("COGNITO_CLIENT_ID") or None,
        )
