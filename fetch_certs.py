#!/usr/bin/env python3
"""Provision Cradlewise MQTT credentials with the shared client library."""

from __future__ import annotations

import argparse
import getpass
import os
import shutil
import tempfile
from pathlib import Path

from cradlewise_client.certificates import materialize_credentials
from cradlewise_client.cloud import (
    CloudAccountClient,
    CloudApiError,
    CloudAuthenticationError,
    CradleAccount,
    ProvisionedCredentials,
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


def _cleanup_directory(directory: Path, label: str) -> str | None:
    """Remove one temporary directory and describe any cleanup failure."""
    try:
        if directory.exists():
            shutil.rmtree(directory)
    except OSError as error:
        return f"{label} could not be removed from {directory}: {error}"
    return None


def _report_cleanup_warning(warning: str | None) -> None:
    if warning is not None:
        print(f"Warning: {warning}")


def _materialize_atomically(
    output_directory: Path,
    credentials: ProvisionedCredentials,
) -> str | None:
    """Replace a credential bundle only after every new file is written."""
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    server_ca_path = output_directory / "server_ca.pem"
    server_ca_certificate = (
        server_ca_path.read_text(encoding="utf-8") if server_ca_path.is_file() else None
    )
    staging_directory = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}-staging-",
            dir=output_directory.parent,
        )
    )
    try:
        materialize_credentials(
            staging_directory,
            credentials,
            server_ca_certificate=server_ca_certificate,
        )
    except BaseException:
        _report_cleanup_warning(
            _cleanup_directory(staging_directory, "Staged credentials")
        )
        raise

    if not output_directory.exists():
        try:
            staging_directory.replace(output_directory)
        except OSError:
            _report_cleanup_warning(
                _cleanup_directory(staging_directory, "Staged credentials")
            )
            raise
        return None

    try:
        backup_root = Path(
            tempfile.mkdtemp(
                prefix=f".{output_directory.name}-backup-",
                dir=output_directory.parent,
            )
        )
    except OSError:
        _report_cleanup_warning(
            _cleanup_directory(staging_directory, "Staged credentials")
        )
        raise
    previous_directory = backup_root / "credentials"
    try:
        output_directory.replace(previous_directory)
    except OSError:
        _report_cleanup_warning(
            _cleanup_directory(staging_directory, "Staged credentials")
        )
        _report_cleanup_warning(
            _cleanup_directory(backup_root, "Empty credential backup")
        )
        raise

    try:
        staging_directory.replace(output_directory)
    except OSError as install_error:
        try:
            previous_directory.replace(output_directory)
        except OSError as restore_error:
            _report_cleanup_warning(
                _cleanup_directory(staging_directory, "Staged credentials")
            )
            raise OSError(
                f"New credentials could not be installed: {install_error}. "
                "Previous credentials remain at "
                f"{previous_directory} because restoration failed: {restore_error}"
            ) from restore_error

        _report_cleanup_warning(
            _cleanup_directory(staging_directory, "Staged credentials")
        )
        _report_cleanup_warning(
            _cleanup_directory(backup_root, "Empty credential backup")
        )
        raise

    cleanup_warning = _cleanup_directory(backup_root, "Previous credentials")
    if cleanup_warning is None:
        return None
    return (
        f"{cleanup_warning}. Remove that backup manually after confirming the new "
        "credentials work."
    )


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
    try:
        cleanup_warning = _materialize_atomically(output_directory, credentials)
    except OSError as error:
        rollback_errors = []
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
    _report_cleanup_warning(cleanup_warning)
    print("Pin the crib's broker CA before connecting across the local network.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
