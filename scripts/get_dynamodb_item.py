#!/usr/bin/env python3
"""
Utility script for fetching a single record from an AWS DynamoDB table
by its partition key.

Usage example:

    python scripts/get_dynamodb_item.py \
        --table MyTable \
        --partition-key userId \
        --value 123 \
        --key-type number \
        --region us-east-1

AWS credentials must be configured in the environment (via environment
variables, AWS config files, or instance profile).
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from typing import Any, Dict

import boto3
from botocore.exceptions import BotoCoreError, ClientError


KeyValue = Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch a DynamoDB item by partition key."
    )
    parser.add_argument(
        "--table",
        required=True,
        help="Name of the DynamoDB table to query.",
    )
    parser.add_argument(
        "--partition-key",
        required=True,
        help="Name of the partition key attribute.",
    )
    parser.add_argument(
        "--value",
        required=True,
        help="Value to match for the partition key.",
    )
    parser.add_argument(
        "--key-type",
        choices=("string", "number", "binary"),
        default="string",
        help="Data type of the partition key value (default: string).",
    )
    parser.add_argument(
        "--region",
        help=(
            "AWS region where the table resides. If omitted, the AWS SDK "
            "default resolution chain is used."
        ),
    )
    parser.add_argument(
        "--consistent-read",
        action="store_true",
        help="Use strongly consistent reads.",
    )
    return parser.parse_args()


def convert_key_value(raw_value: str, key_type: str) -> KeyValue:
    if key_type == "string":
        return raw_value
    if key_type == "number":
        try:
            return Decimal(raw_value)
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError(
                f"Failed to convert '{raw_value}' to Decimal for numeric key."
            ) from exc
    if key_type == "binary":
        try:
            return bytes.fromhex(raw_value)
        except ValueError as exc:
            raise ValueError(
                "Binary key expects a hex-encoded string (e.g. '0A1B')."
            ) from exc
    raise ValueError(f"Unsupported key type '{key_type}'.")


def get_item(
    table_name: str,
    partition_key: str,
    value: KeyValue,
    *,
    region: str | None,
    consistent_read: bool,
) -> Dict[str, Any] | None:
    session_kwargs: Dict[str, Any] = {}
    if region:
        session_kwargs["region_name"] = region

    dynamodb = boto3.resource("dynamodb", **session_kwargs)
    table = dynamodb.Table(table_name)

    try:
        response = table.get_item(
            Key={partition_key: value},
            ConsistentRead=consistent_read,
        )
    except (ClientError, BotoCoreError) as exc:
        raise RuntimeError(f"Failed to fetch item: {exc}") from exc

    return response.get("Item")


def main() -> int:
    args = parse_args()

    try:
        key_value = convert_key_value(args.value, args.key_type)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        item = get_item(
            args.table,
            args.partition_key,
            key_value,
            region=args.region,
            consistent_read=args.consistent_read,
        )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if not item:
        print("No item found for the provided key.", file=sys.stderr)
        return 3

    print(json.dumps(item, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
