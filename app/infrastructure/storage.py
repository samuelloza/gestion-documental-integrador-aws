from __future__ import annotations

from pathlib import Path


class LocalObjectStorage:
    """Development adapter. Production must use S3 via S3ObjectStorage."""
    def __init__(self, base: Path):
        self.base = base
        self.base.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, body: bytes, content_type: str) -> None:
        path = self.base / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)

    def get(self, key: str) -> bytes:
        return (self.base / key).read_bytes()

    def signed_get(self, key: str, expires_in: int) -> str | None:
        return None

    def delete(self, key: str) -> None:
        (self.base / key).unlink(missing_ok=True)


class S3ObjectStorage:
    def __init__(self, bucket: str, region: str | None):
        try:
            import boto3
        except ImportError as exc:
            raise RuntimeError("Install requirements.txt to use STORAGE_BACKEND=s3") from exc
        self.bucket = bucket
        self.client = boto3.client("s3", region_name=region)

    def put(self, key: str, body: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=body, ContentType=content_type)

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def signed_get(self, key: str, expires_in: int) -> str:
        return self.client.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires_in)

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)
