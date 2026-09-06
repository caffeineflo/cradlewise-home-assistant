#!/usr/bin/env python3
"""Provision Cradlewise MQTT credentials with the shared client library."""

from __future__ import annotations

import argparse
import getpass
import os
import shutil
from pathlib import Path

from cradlewise_client.certificates import materialize_credentials
from cradlewise_client.cloud import (
    CloudAccountClient,
    CloudApiError,
    CloudAuthenticationError,
    CradleAccount,
)


def _account_credentials() -> tuple[str, str]:
    """Read account credentials from the environment or an interactive prompt."""
    email = os.environ.get("CRADLEWISE_EMAIL") or input("Cradlewise email: ")
    password = os.environ.get("CRADLEWISE_PASSWORD") or getpass.getpass(
        "Cradlewise password: "
    )
    return email, password


def _select_account(accounts: list[CradleAccount]) -> CradleAccount:
    """Select the only account or prompt for one paired cradle."""
    if not accounts:
        raise CloudApiError("No paired cradle profiles were found")
    if len(accounts) == 1:
        return accounts[0]

    print("Multiple paired cradle profiles were found:")
    for index, account in enumerate(accounts):
        print(f"  [{index}] {account.name} ({account.cradle_id})")
    try:
        return accounts[int(input("Select profile number: "))]
    except (ValueError, IndexError) as error:
        raise CloudApiError("The selected profile number is invalid") from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Provision local MQTT credentials for a paired Cradlewise crib"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("certs"),
        help="Parent directory for the cradle-specific credential directory",
    )
    parser.add_argument(
        "--timezone",
        default=os.environ.get("TZ", "UTC"),
        help="IANA timezone reported during device registration (default: TZ or UTC)",
    )
    parser.add_argument(
        "--country",
        default=os.environ.get("CRADLEWISE_COUNTRY", "US"),
        help="Country code reported during device registration (default: US)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Authenticate, register one client, and save its MQTT credentials."""
    args = _parser().parse_args(argv)
    email, password = _account_credentials()
    print(f"Authenticating as {email}...")

    try:
        cloud = CloudAccountClient(email=email, password=password)
        cloud.authenticate()
        account = _select_account(cloud.list_accounts())
        credentials = cloud.provision_credentials(
            account,
            timezone=args.timezone,
            country=args.country,
        )
    except (CloudAuthenticationError, CloudApiError, OSError) as error:
        print(f"Credential provisioning failed: {error}")
        return 1

    output_directory = args.output_dir / account.cradle_id
    output_existed = output_directory.exists()
    try:
        materialize_credentials(output_directory, credentials)
    except OSError as error:
        rollback_errors = []
        if not output_existed and output_directory.exists():
            try:
                shutil.rmtree(output_directory)
            except OSError as rollback_error:
                rollback_errors.append(rollback_error)
        try:
            removed = cloud.remove_user_devices(account, [credentials.device_id])
            if removed != [credentials.device_id]:
                rollback_errors.append(
                    CloudApiError(
                        "Cradlewise did not confirm removal of the new registration"
                    )
                )
        except (CloudAuthenticationError, CloudApiError, OSError) as rollback_error:
            rollback_errors.append(rollback_error)

        print(f"Credential provisioning failed: {error}")
        for rollback_error in rollback_errors:
            print(f"Credential rollback failed: {rollback_error}")
        return 1

    print(f"Credentials saved to {output_directory}")
    print("Pin the crib's broker CA before connecting across the local network.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
