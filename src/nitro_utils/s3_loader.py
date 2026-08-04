import asyncio
import csv
import io
import logging
from datetime import date

import boto3
from botocore.exceptions import ClientError

from nitro_utils.config import settings

logger = logging.getLogger(__name__)


def _load_from_s3_sync(s3_key: str) -> list[dict[str, str]]:
    """Synchronous S3 loader (called via asyncio.to_thread)."""
    s3_client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
    )

    # Check existence via list_objects_v2 (HEAD lies with ContentLength=0)
    try:
        response = s3_client.list_objects_v2(
            Bucket=settings.s3_bucket,
            Prefix=s3_key,
            MaxKeys=1,
        )
        if "Contents" not in response or len(response["Contents"]) == 0:
            logger.info("Watchlist artifact not found: s3://%s/%s", settings.s3_bucket, s3_key)
            return []
    except ClientError as e:
        logger.exception("S3 list_objects_v2 failed for %s", s3_key)
        raise RuntimeError(f"S3 list_objects_v2 failed for {s3_key}: {e}") from e

    # Download CSV
    try:
        obj = s3_client.get_object(Bucket=settings.s3_bucket, Key=s3_key)
        csv_bytes = obj["Body"].read()
        csv_text = csv_bytes.decode("utf-8")

        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)

        logger.info(
            "Loaded frozen watchlist from s3://%s/%s: %d rows",
            settings.s3_bucket,
            s3_key,
            len(rows),
        )
        return rows

    except ClientError as e:
        logger.exception("S3 get_object failed for %s", s3_key)
        raise RuntimeError(f"Failed to load watchlist from S3: {e}") from e
    except Exception as e:
        logger.exception("Failed to parse watchlist CSV from S3")
        raise RuntimeError(f"Failed to parse watchlist CSV: {e}") from e


async def load_frozen_watchlist(target_date: date) -> list[dict[str, str]]:
    """Load frozen prediction watchlist from S3.

    Reads ml-v3/watchlists/{YYYY-MM-DD}.csv artifact.
    Returns empty list if artifact doesn't exist (builder never ran for that date).
    """
    s3_key = f"ml-v3/watchlists/{target_date}.csv"
    return await asyncio.to_thread(_load_from_s3_sync, s3_key)
