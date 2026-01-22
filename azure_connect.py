"""Connect to Azure and list resource groups.

Setup:
  pip install -r requirements-azure.txt

Authentication options:
  1) Azure CLI login:
     az login
  2) Service principal (environment variables):
     export AZURE_CLIENT_ID="..."
     export AZURE_TENANT_ID="..."
     export AZURE_CLIENT_SECRET="..."

Required environment variable:
  export AZURE_SUBSCRIPTION_ID="..."
"""

from __future__ import annotations

import os
import sys

from azure.core.exceptions import ClientAuthenticationError, HttpResponseError
from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient


def require_subscription_id() -> str:
    subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
    if not subscription_id:
        raise ValueError(
            "AZURE_SUBSCRIPTION_ID is not set. "
            "Set it to your Azure subscription ID."
        )
    return subscription_id


def build_credential() -> DefaultAzureCredential:
    authority_host = os.getenv("AZURE_AUTHORITY_HOST")
    if authority_host:
        return DefaultAzureCredential(authority=authority_host)
    return DefaultAzureCredential()


def main() -> int:
    try:
        subscription_id = require_subscription_id()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    credential = build_credential()
    client = ResourceManagementClient(credential, subscription_id)

    try:
        resource_groups = list(client.resource_groups.list())
    except ClientAuthenticationError as exc:
        print("Authentication failed. Check your Azure credentials.", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 3
    except HttpResponseError as exc:
        print("Azure request failed.", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return 4

    if not resource_groups:
        print("Connected to Azure. No resource groups found.")
        return 0

    print("Connected to Azure. Resource groups:")
    for group in resource_groups:
        print(f"- {group.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
