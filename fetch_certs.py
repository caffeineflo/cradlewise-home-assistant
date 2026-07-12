#!/usr/bin/env python3
"""
Fetch Cradlewise device certificates using Cognito auth.

Authenticates with your Cradlewise account, discovers your cradle,
and downloads the TLS certificates needed for local MQTT connections.

Usage:
    python3 fetch_certs.py

Set CRADLEWISE_EMAIL and CRADLEWISE_PASSWORD environment variables,
or enter them interactively.
"""

import datetime
import json
import sys
from pathlib import Path

import boto3
import requests

from cradlewise_api import (
    API_ENDPOINT,
    REGION,
    REQUEST_TIMEOUT_SECONDS,
    S3_BUCKET,
    authenticate,
    get_accounts,
    get_aws_credentials,
    get_credentials_interactive,
    sign_request,
)


def main():
    # -- Step 1: Get credentials --
    email, password = get_credentials_interactive()
    print(f"\nAuthenticating as {email}...")

    # -- Step 2: Cognito SRP auth --
    try:
        _, id_token = authenticate(email, password)
    except Exception as e:
        print(f"Authentication failed: {e}")
        sys.exit(1)
    print("Cognito auth successful.")

    # -- Step 3: Get temporary AWS credentials from Identity Pool --
    credentials, aws_creds = get_aws_credentials(id_token)
    print("AWS credentials obtained.")

    # -- Step 4: Get account info (baby_id, cradle_id) --
    accounts = get_accounts(email, credentials)
    if not accounts:
        print("No baby profiles found for this account.")
        sys.exit(1)

    # If multiple babies, let the user pick
    if len(accounts) == 1:
        account = accounts[0]
    else:
        print("\nMultiple baby profiles found:")
        for i, acc in enumerate(accounts):
            name = acc.get("name", "Unknown")
            cradle = acc.get("cradle_id", "no cradle")
            print(f"  [{i}] {name} (baby_id={acc.get('baby_id')}, cradle_id={cradle})")
        choice = int(input("Select profile number: "))
        account = accounts[choice]

    baby_id = account["baby_id"]
    cradle_id = account.get("cradle_id")
    baby_name = account.get("name", "Unknown")
    print(f"Selected: {baby_name} (baby_id={baby_id}, cradle_id={cradle_id})")

    if not cradle_id:
        print("No cradle paired to this baby profile.")
        sys.exit(1)

    # -- Step 5: Fetch device certificates --
    cert_url = f"{API_ENDPOINT}/cradles/pairedUsers/v3"
    cert_body = json.dumps(
        {
            "email_id": email,
            "baby_id": int(baby_id),
            "fcm_token": "local_stream_client",
            "device": {
                "registration_date": datetime.datetime.now().strftime("%Y-%m-%d"),
                "app_version": "2.55.5",
                "country": "US",
                "os": "android",
                "device_name": "Samsung Galaxy S24 Ultra",
                "os_version": "14",
                "timezone": "America/New_York",
                "type": "phone",
                "resolution": "{1440,3120}",
            },
        }
    )
    signed_headers = sign_request(
        "POST",
        cert_url,
        credentials,
        body=cert_body,
        headers={"Content-Type": "application/json"},
    )
    signed_headers["Content-Type"] = "application/json"

    resp = requests.post(
        cert_url,
        headers=signed_headers,
        data=cert_body,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if not resp.ok:
        print(f"Cert API failed: {resp.status_code} {resp.reason}")
        print(f"Response body: {resp.text[:1000]}")
        sys.exit(1)
    cert_data = resp.json()

    # Check for API-level errors
    if cert_data.get("errorType") == "API_FAILED":
        print(f"API error: {cert_data.get('message')}")
        sys.exit(1)

    device_config = cert_data.get("device_config")
    if not device_config:
        print("No device_config in response. Full response:")
        print(json.dumps(cert_data, indent=2))
        sys.exit(1)

    group_ca_cert = device_config.get("group_ca_cert")
    s3_keys = device_config.get("s3_object_keys", [])
    returned_cradle_id = device_config.get("cradle_id", cradle_id)

    print(f"Device config received for cradle: {returned_cradle_id}")
    print(f"  S3 keys: {s3_keys}")
    print(f"  CA cert present: {bool(group_ca_cert)}")

    # -- Step 6: Download certs from S3 --
    s3_client = boto3.client(
        "s3",
        region_name=REGION,
        aws_access_key_id=aws_creds["AccessKeyId"],
        aws_secret_access_key=aws_creds["SecretKey"],
        aws_session_token=aws_creds["SessionToken"],
    )

    out_dir = Path("certs") / returned_cradle_id
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save CA certificate
    if group_ca_cert:
        ca_path = out_dir / "ca.pem"
        ca_path.write_text(group_ca_cert)
        print(f"  Saved CA cert: {ca_path}")

    # Extract device UUID from the S3 cert key path.
    # Pattern: {cradleId}/android/{deviceUuid}.pem
    device_uuid = None
    if s3_keys:
        cert_key = s3_keys[0]
        device_uuid = cert_key.rsplit("/", 1)[-1].removesuffix(".pem")
        print(f"  Device UUID: {device_uuid}")

    # Download client cert and private key from S3
    file_names = ["client_cert.pem", "client_key.pem"]
    for i, s3_key in enumerate(s3_keys):
        local_name = file_names[i] if i < len(file_names) else f"cert_file_{i}.pem"
        local_path = out_dir / local_name
        print(f"  Downloading s3://{S3_BUCKET}/{s3_key} -> {local_path}")
        try:
            s3_client.download_file(S3_BUCKET, s3_key, str(local_path))
        except Exception as e:
            print(f"  S3 download failed: {e}")
            print("  Trying with StoragePath prefix...")
            # Amplify Storage may prefix with "public/"
            try:
                s3_client.download_file(S3_BUCKET, f"public/{s3_key}", str(local_path))
            except Exception as e2:
                print(f"  Also failed with public/ prefix: {e2}")
                continue
        print(f"  Saved: {local_path}")

    # Save device UUID (needed as MQTT client ID for local connections)
    if device_uuid:
        (out_dir / "device_id").write_text(device_uuid)
        print(f"  Saved device ID: {out_dir}/device_id")

    # Set restrictive permissions on private key
    key_path = out_dir / "client_key.pem"
    if key_path.exists():
        key_path.chmod(0o600)

    # Also grab device_id directly from the response if available
    response_device_id = device_config.get("device_id")
    if response_device_id:
        device_uuid = response_device_id
        (out_dir / "device_id").write_text(device_uuid)
        print(f"  Device ID (from response): {device_uuid}")

    print(f"\nDone! Certificates saved to {out_dir}/")
    print("\nTo use with a local MQTT client:")
    print(f"  CA cert:     {out_dir}/ca.pem")
    print(f"  Client cert: {out_dir}/client_cert.pem")
    print(f"  Client key:  {out_dir}/client_key.pem")
    print(f"  Device ID:   {out_dir}/device_id")
    print("  Broker:      ssl://<crib_ip>:8883")
    print(f"  Cradle ID:   {returned_cradle_id}")


if __name__ == "__main__":
    main()
