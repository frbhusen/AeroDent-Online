import os
from io import BytesIO
from pathlib import Path


class LocalFileStorage:
    """Private filesystem storage behind a relative, server-generated key."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, storage_key):
        if not isinstance(storage_key, str) or not storage_key:
            raise ValueError("Invalid storage key.")
        candidate = (self.root / Path(storage_key)).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError("Storage key escapes storage root.")
        return candidate

    def save(self, content, storage_key):
        path = self._path(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def open(self, storage_key):
        return self._path(storage_key).open("rb")

    def delete(self, storage_key):
        path = self._path(storage_key)
        if path.exists():
            path.unlink()

    def exists(self, storage_key):
        return self._path(storage_key).is_file()


class S3FileStorage:
    """S3-compatible object storage (AWS S3, Cloudflare R2, MinIO)."""

    def __init__(self, bucket_name, endpoint_url=None, region_name="auto", access_key=None, secret_key=None):
        import boto3
        from botocore.config import Config as BotoConfig

        self.bucket = bucket_name
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region_name,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=BotoConfig(signature_version="s3v4"),
        )

    def save(self, content, storage_key):
        self.client.put_object(
            Bucket=self.bucket,
            Key=storage_key,
            Body=content,
        )

    def open(self, storage_key):
        response = self.client.get_object(Bucket=self.bucket, Key=storage_key)
        return BytesIO(response["Body"].read())

    def delete(self, storage_key):
        self.client.delete_object(Bucket=self.bucket, Key=storage_key)

    def exists(self, storage_key):
        from botocore.exceptions import ClientError
        try:
            self.client.head_object(Bucket=self.bucket, Key=storage_key)
            return True
        except ClientError:
            return False


def get_storage(root_path=None):
    """Returns configured storage driver (S3 if S3_BUCKET is set, otherwise LocalFileStorage)."""
    s3_bucket = os.environ.get("S3_BUCKET")
    if s3_bucket:
        try:
            return S3FileStorage(
                bucket_name=s3_bucket,
                endpoint_url=os.environ.get("S3_ENDPOINT_URL"),
                region_name=os.environ.get("S3_REGION", "auto"),
                access_key=os.environ.get("S3_ACCESS_KEY_ID"),
                secret_key=os.environ.get("S3_SECRET_ACCESS_KEY"),
            )
        except ImportError:
            pass

    return LocalFileStorage(root_path or os.environ.get("STORAGE_ROOT", "uploads"))