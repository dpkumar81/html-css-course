"""Detailed Azure connection example with CLI options.

Setup:
  pip install -r requirements-azure.txt

Quick start (Azure CLI login):
  az login
  export AZURE_SUBSCRIPTION_ID="..."
  python azure_connect.py list-groups

Service principal login:
  export AZURE_TENANT_ID="..."
  export AZURE_CLIENT_ID="..."
  export AZURE_CLIENT_SECRET="..."
  export AZURE_SUBSCRIPTION_ID="..."
  python azure_connect.py list-resources --resource-group my-rg

Notes:
  - By default the script uses DefaultAzureCredential, which tries multiple
    auth sources (environment, managed identity, Azure CLI, etc.).
  - If tenant/client/secret are provided, ClientSecretCredential is used.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional, Sequence

from azure.core.exceptions import ClientAuthenticationError, HttpResponseError
from azure.identity import ClientSecretCredential, DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient

MANAGEMENT_SCOPE = "https://management.azure.com/.default"


@dataclass(frozen=True)
class AzureConfig:
    subscription_id: str
    tenant_id: Optional[str]
    client_id: Optional[str]
    client_secret: Optional[str]
    authority_host: Optional[str]
    debug: bool

    @property
    def uses_service_principal(self) -> bool:
        return any([self.tenant_id, self.client_id, self.client_secret])


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Connect to Azure and perform simple resource queries.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--subscription-id",
        default=os.getenv("AZURE_SUBSCRIPTION_ID"),
        help="Azure subscription ID (or set AZURE_SUBSCRIPTION_ID).",
    )
    parser.add_argument(
        "--tenant-id",
        default=os.getenv("AZURE_TENANT_ID"),
        help="Azure tenant ID (or set AZURE_TENANT_ID).",
    )
    parser.add_argument(
        "--client-id",
        default=os.getenv("AZURE_CLIENT_ID"),
        help="Service principal client ID (or set AZURE_CLIENT_ID).",
    )
    parser.add_argument(
        "--client-secret",
        default=os.getenv("AZURE_CLIENT_SECRET"),
        help="Service principal client secret (or set AZURE_CLIENT_SECRET).",
    )
    parser.add_argument(
        "--authority-host",
        default=os.getenv("AZURE_AUTHORITY_HOST"),
        help="Authority host for sovereign clouds (optional).",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=0,
        help="Limit output to N items (0 means no limit).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging for troubleshooting.",
    )

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("list-groups", help="List resource groups.")

    show_group = subparsers.add_parser("show-group", help="Show one group.")
    show_group.add_argument("resource_group", help="Resource group name.")

    list_resources = subparsers.add_parser(
        "list-resources", help="List resources in a group or subscription."
    )
    list_resources.add_argument(
        "--resource-group",
        help="Limit resources to a specific group.",
    )

    subparsers.add_parser(
        "validate-token",
        help="Validate auth by requesting a management token.",
    )

    parser.set_defaults(command="list-groups")
    return parser.parse_args(argv)


def configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def build_config(args: argparse.Namespace) -> AzureConfig:
    if not args.subscription_id:
        raise ValueError(
            "Missing subscription ID. Provide --subscription-id or set "
            "AZURE_SUBSCRIPTION_ID."
        )

    return AzureConfig(
        subscription_id=args.subscription_id,
        tenant_id=args.tenant_id,
        client_id=args.client_id,
        client_secret=args.client_secret,
        authority_host=args.authority_host,
        debug=args.debug,
    )


def build_credential(config: AzureConfig):
    if config.uses_service_principal:
        missing = [
            name
            for name, value in [
                ("AZURE_TENANT_ID", config.tenant_id),
                ("AZURE_CLIENT_ID", config.client_id),
                ("AZURE_CLIENT_SECRET", config.client_secret),
            ]
            if not value
        ]
        if missing:
            missing_list = ", ".join(missing)
            raise ValueError(
                "Service principal auth selected but missing: "
                f"{missing_list}."
            )
        return ClientSecretCredential(
            tenant_id=config.tenant_id,
            client_id=config.client_id,
            client_secret=config.client_secret,
            authority=config.authority_host,
        )

    if config.authority_host:
        return DefaultAzureCredential(authority=config.authority_host)
    return DefaultAzureCredential()


def limit_iterable(items: Iterable, max_items: int) -> Iterable:
    if max_items <= 0:
        return items
    count = 0
    for item in items:
        if count >= max_items:
            break
        yield item
        count += 1


def list_groups(client: ResourceManagementClient, max_items: int) -> int:
    groups = list(limit_iterable(client.resource_groups.list(), max_items))
    if not groups:
        print("Connected to Azure. No resource groups found.")
        return 0

    print("Resource groups:")
    for group in groups:
        tags = group.tags or {}
        tag_text = ", ".join(f"{key}={value}" for key, value in tags.items()) or "-"
        print(f"- {group.name} | {group.location} | tags: {tag_text}")
    return 0


def show_group(client: ResourceManagementClient, name: str) -> int:
    group = client.resource_groups.get(name)
    tags = group.tags or {}
    tag_text = ", ".join(f"{key}={value}" for key, value in tags.items()) or "-"
    print("Resource group details:")
    print(f"  name: {group.name}")
    print(f"  location: {group.location}")
    print(f"  id: {group.id}")
    print(f"  tags: {tag_text}")
    return 0


def list_resources(
    client: ResourceManagementClient, resource_group: Optional[str], max_items: int
) -> int:
    if resource_group:
        resources = client.resources.list_by_resource_group(resource_group)
    else:
        resources = client.resources.list()

    resources = list(limit_iterable(resources, max_items))
    if not resources:
        print("No resources found.")
        return 0

    print("Resources:")
    for resource in resources:
        location = resource.location or "-"
        print(f"- {resource.name} | {resource.type} | {location}")
    return 0


def validate_token(credential) -> int:
    token = credential.get_token(MANAGEMENT_SCOPE)
    expires_at = datetime.fromtimestamp(token.expires_on, tz=timezone.utc)
    print("Token acquired.")
    print(f"  expires_at: {expires_at.isoformat()}")
    return 0


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    try:
        config = build_config(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    configure_logging(config.debug)

    try:
        credential = build_credential(config)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    client = ResourceManagementClient(credential, config.subscription_id)

    try:
        if args.command == "list-groups":
            return list_groups(client, args.max_items)
        if args.command == "show-group":
            return show_group(client, args.resource_group)
        if args.command == "list-resources":
            return list_resources(client, args.resource_group, args.max_items)
        if args.command == "validate-token":
            return validate_token(credential)
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 2
    except ClientAuthenticationError as exc:
        print("Authentication failed. Check your Azure credentials.", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 3
    except HttpResponseError as exc:
        print("Azure request failed.", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
