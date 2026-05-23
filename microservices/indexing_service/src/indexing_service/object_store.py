"""
object_store.py — MinIO Object Storage
=======================================
Uploads crop PNGs and page images to MinIO and returns public URLs.
Migrated from my_work/upload_to_minio.py with proper error handling.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from indexing_service.config import settings

log = logging.getLogger(__name__)

_PUBLIC_READ_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": "*",
            "Action": ["s3:GetObject"],
            "Resource": [],  # filled per-bucket
        }
    ],
}


def _get_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.minio_endpoint,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def _ensure_bucket(client, bucket_name: str) -> None:
    """Create bucket if it doesn't exist and make it publicly readable."""
    try:
        client.head_bucket(Bucket=bucket_name)
        return
    except ClientError:
        pass

    client.create_bucket(Bucket=bucket_name)
    policy = dict(_PUBLIC_READ_POLICY)
    policy["Statement"][0]["Resource"] = [f"arn:aws:s3:::{bucket_name}/*"]
    client.put_bucket_policy(Bucket=bucket_name, Policy=json.dumps(policy))
    log.info(f"Created MinIO bucket: {bucket_name}")


def upload_crops(
    pipeline_output_dir: Path,
    doc_id: str,
) -> dict[str, str]:
    """
    Upload all crop PNGs for a document to MinIO.

    Returns:
        {relative_crop_path → public_minio_url}
    """
    client = _get_client()
    _ensure_bucket(client, settings.minio_bucket_crops)

    crops_dir = pipeline_output_dir / "crops" / doc_id
    if not crops_dir.exists():
        log.warning(f"Crops directory not found: {crops_dir}")
        return {}

    url_map: dict[str, str] = {}
    count = 0

    for crop_file in crops_dir.rglob("*.png"):
        # S3 key = relative path from pipeline_output_dir
        s3_key = str(crop_file.relative_to(pipeline_output_dir))
        client.upload_file(
            str(crop_file),
            settings.minio_bucket_crops,
            s3_key,
            ExtraArgs={"ContentType": "image/png"},
        )
        url = f"{settings.minio_endpoint}/{settings.minio_bucket_crops}/{s3_key}"
        # Map the relative crop_path stored in the JSON → public URL
        url_map[s3_key] = url
        count += 1

    log.info(f"Uploaded {count} crop PNGs for doc_id='{doc_id}'")
    return url_map


def upload_page_images(
    docs_images_dir: Path,
    doc_id: str,
) -> dict[str, str]:
    """
    Upload page PNG images for a document to MinIO.

    Returns:
        {page_filename → public_minio_url}  e.g. {"page_001.png": "http://..."}
    """
    client = _get_client()
    _ensure_bucket(client, settings.minio_bucket_pages)

    doc_images_dir = docs_images_dir / doc_id
    if not doc_images_dir.exists():
        log.warning(f"Page images directory not found: {doc_images_dir}")
        return {}

    url_map: dict[str, str] = {}
    count = 0

    for img_file in sorted(doc_images_dir.glob("*.png")):
        s3_key = f"{doc_id}/{img_file.name}"
        client.upload_file(
            str(img_file),
            settings.minio_bucket_pages,
            s3_key,
            ExtraArgs={"ContentType": "image/png"},
        )
        url = f"{settings.minio_endpoint}/{settings.minio_bucket_pages}/{s3_key}"
        url_map[img_file.name] = url
        count += 1

    log.info(f"Uploaded {count} page images for doc_id='{doc_id}'")
    return url_map


def health_check() -> bool:
    """Returns True if MinIO is reachable."""
    try:
        client = _get_client()
        client.list_buckets()
        return True
    except Exception:
        return False
