import os
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
BUCKET = os.getenv("MINIO_BUCKET", "videotranslation")

_client = None


def get_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=MINIO_ENDPOINT,
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_access_key=MINIO_SECRET_KEY,
            config=Config(
                signature_version="s3v4",
                request_checksum_calculation="when_required",
            ),
            region_name="us-east-1",
        )
    return _client


def init_bucket():
    client = get_client()
    try:
        client.head_bucket(Bucket=BUCKET)
    except ClientError:
        client.create_bucket(Bucket=BUCKET)


def upload_file(local_path: str, key: str) -> str:
    get_client().upload_file(local_path, BUCKET, key)
    return key


def upload_fileobj(file_obj, key: str) -> str:
    get_client().upload_fileobj(file_obj, BUCKET, key)
    return key


def upload_bytes(data: bytes, key: str) -> str:
    get_client().put_object(Bucket=BUCKET, Key=key, Body=data)
    return key


def download_file(key: str, local_path: str):
    get_client().download_file(BUCKET, key, local_path)


def read_bytes(key: str) -> bytes:
    response = get_client().get_object(Bucket=BUCKET, Key=key)
    return response["Body"].read()


def object_exists(key: str) -> bool:
    try:
        get_client().head_object(Bucket=BUCKET, Key=key)
        return True
    except ClientError:
        return False


def get_object_size(key: str) -> int:
    response = get_client().head_object(Bucket=BUCKET, Key=key)
    return response["ContentLength"]


def read_range(key: str, start: int, end: int) -> bytes:
    response = get_client().get_object(Bucket=BUCKET, Key=key, Range=f"bytes={start}-{end}")
    return response["Body"].read()


def delete_object(key: str):
    try:
        get_client().delete_object(Bucket=BUCKET, Key=key)
    except ClientError:
        pass


def set_uploads_retention(prefix: str = "uploads/", days: int = 7):
    try:
        get_client().put_bucket_lifecycle_configuration(
            Bucket=BUCKET,
            LifecycleConfiguration={
                "Rules": [{
                    "ID": "expire-uploaded-videos",
                    "Filter": {"Prefix": prefix},
                    "Status": "Enabled",
                    "Expiration": {"Days": days},
                }]
            },
        )
    except ClientError as e:
        print(f"[minio] failed to set uploads retention lifecycle rule: {e}")
