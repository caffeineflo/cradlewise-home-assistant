"""Cradlewise account discovery and certificate provisioning."""

from __future__ import annotations

import datetime
import json
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
from botocore.exceptions import BotoCoreError, ClientError
from pycognito import Cognito
from pycognito.exceptions import WarrantException

USER_POOL_ID = "us-east-1_hRGLsOxun"
CLIENT_ID = "4jnn2bbtroa3e6ra73dc8m8luh"
# Public native-app configuration embedded in the distributed Android APK.
# This is not an account credential and cannot be kept confidential by a
# mobile client.
CLIENT_SECRET = "qfmc9tv70upcacajmhpl4a9n3orehteo93icbng0fljkt6916em"
IDENTITY_POOL_ID = "us-east-1:53b70db5-7440-4ecf-8dac-d6202eb6c1d2"
REGION = "us-east-1"
API_ENDPOINT = "https://backend.cradlewise.com/prod-latest"
S3_BUCKET = "cradlewise-device-certs"
REQUEST_TIMEOUT_SECONDS = 10
ANDROID_DEVICE_MODELS = (
    "Pixel 8",
    "Pixel 8a",
    "SM-S921U1",
    "SM-S926U1",
    "CPH2583",
)


class CloudAuthenticationError(RuntimeError):
    """Raised when account credentials cannot be authenticated."""


class CloudApiError(RuntimeError):
    """Raised when a Cradlewise cloud request fails."""


class CloudProvisioningError(CloudApiError):
    """Raised when device certificates cannot be provisioned."""


@dataclass(frozen=True)
class CradleAccount:
    """One baby profile and its associated cradle."""

    baby_id: int
    cradle_id: str
    name: str


@dataclass(frozen=True)
class ProvisionedCredentials:
    """PEM material returned for local and AWS IoT MQTT connections."""

    device_id: str
    client_certificate: str
    client_private_key: str
    group_ca_certificate: str


@dataclass(frozen=True)
class UserDevice:
    """One device registration associated with the authenticated account."""

    device_id: str
    device_name: str | None
    os: str | None
    model: str | None


def sign_request(
    method: str,
    url: str,
    credentials: Credentials,
    *,
    body: str | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, str]:
    """Sign one Cradlewise API request with temporary AWS credentials."""
    request = AWSRequest(
        method=method,
        url=url,
        data=body,
        headers=headers or {},
    )
    SigV4Auth(credentials, "execute-api", REGION).add_auth(request)
    return dict(request.headers)


class CloudAccountClient:
    """Blocking account client intended for an executor in async consumers."""

    def __init__(
        self,
        *,
        email: str,
        password: str,
        session: requests.Session | None = None,
    ) -> None:
        if not email.strip() or not password:
            raise CloudAuthenticationError("email and password are required")
        self.email = email.strip()
        self._password = password
        self._session = session or requests.Session()
        self._credentials: Credentials | None = None
        self._raw_credentials: dict[str, Any] | None = None

    def authenticate(self) -> None:
        """Authenticate with Cognito and cache temporary AWS credentials."""
        try:
            cognito = Cognito(
                USER_POOL_ID,
                CLIENT_ID,
                username=self.email,
                client_secret=CLIENT_SECRET,
            )
            cognito.authenticate(password=self._password)
            if not cognito.id_token:
                raise CloudAuthenticationError(
                    "Cradlewise authentication returned no ID token"
                )
            identity = boto3.client("cognito-identity", region_name=REGION)
            logins = {
                f"cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}": (cognito.id_token)
            }
            identity_response = identity.get_id(
                IdentityPoolId=IDENTITY_POOL_ID,
                Logins=logins,
            )
            credentials_response = identity.get_credentials_for_identity(
                IdentityId=identity_response["IdentityId"],
                Logins=logins,
            )
            raw = credentials_response["Credentials"]
            self._credentials = Credentials(
                access_key=raw["AccessKeyId"],
                secret_key=raw["SecretKey"],
                token=raw["SessionToken"],
            )
            self._raw_credentials = raw
        except CloudAuthenticationError:
            raise
        except ClientError as exc:
            error = exc.response.get("Error", {})
            if error.get("Code") in {
                "NotAuthorizedException",
                "PasswordResetRequiredException",
                "UserNotConfirmedException",
                "UserNotFoundException",
            }:
                raise CloudAuthenticationError(
                    "Cradlewise account authentication failed"
                ) from exc
            raise CloudApiError(
                "Cradlewise authentication service is unavailable"
            ) from exc
        except (BotoCoreError, requests.RequestException, OSError) as exc:
            raise CloudApiError(
                "Cradlewise authentication service is unavailable"
            ) from exc
        except WarrantException as exc:
            raise CloudAuthenticationError(
                "Cradlewise account authentication failed"
            ) from exc

    def list_accounts(self) -> list[CradleAccount]:
        """List paired cradle profiles for the authenticated account."""
        payload = self._request_json(
            "GET",
            f"{API_ENDPOINT}/accounts?emailId={quote(self.email)}",
        )
        accounts = payload.get("accounts")
        if not isinstance(accounts, list):
            raise CloudApiError("Cradlewise accounts response has no account list")
        result = []
        for account in accounts:
            if not isinstance(account, dict) or not account.get("cradle_id"):
                continue
            try:
                baby_id = int(account["baby_id"])
            except (KeyError, TypeError, ValueError):
                continue
            result.append(
                CradleAccount(
                    baby_id=baby_id,
                    cradle_id=str(account["cradle_id"]).strip(),
                    name=str(account.get("name") or "Cradlewise"),
                )
            )
        return result

    def get_cradle_state(self, cradle_id: str) -> dict[str, Any]:
        """Fetch the cloud shadow state through the Cradlewise REST API."""
        return self._request_json(
            "GET",
            f"{API_ENDPOINT}/cradles/{cradle_id}/state",
        )

    def get_cradle_ip(self, cradle_id: str) -> str | None:
        """Resolve the last reported local address, preferring onlineStatus v2."""
        v2_error: CloudApiError | None = None
        try:
            payload = self._request_json(
                "GET",
                f"{API_ENDPOINT}/cradles/{cradle_id}/onlineStatus/v2",
            )
            state_message = payload.get("state_message")
            if isinstance(state_message, str):
                parsed = json.loads(state_message)
                address = _local_ip(parsed)
                if address:
                    return address
        except (CloudApiError, json.JSONDecodeError, TypeError) as exc:
            v2_error = (
                exc
                if isinstance(exc, CloudApiError)
                else CloudApiError("invalid onlineStatus v2 state message")
            )

        try:
            payload = self._request_json(
                "GET",
                f"{API_ENDPOINT}/cradles/{cradle_id}/onlineStatus",
            )
            address = payload.get("local_ip")
            return (
                address.strip()
                if isinstance(address, str) and address.strip()
                else None
            )
        except CloudApiError as exc:
            if v2_error is not None:
                raise CloudApiError(
                    f"Cradlewise online status failed: v2={v2_error}; v1={exc}"
                ) from exc
            raise

    def provision_credentials(
        self,
        account: CradleAccount,
        *,
        app_version: str = "2.55.5",
        timezone: str = "UTC",
        country: str = "US",
    ) -> ProvisionedCredentials:
        """Register a compatible client and download its MQTT certificate."""
        body = json.dumps(
            {
                "email_id": self.email,
                "baby_id": account.baby_id,
                # Android uses an empty string until Firebase supplies a token.
                # This client does not implement Firebase push notifications.
                "fcm_token": "",
                "device": {
                    "registration_date": datetime.date.today().isoformat(),
                    "app_version": app_version,
                    "country": country,
                    "os": "android",
                    "device_name": _android_device_name(),
                    "os_version": "14",
                    "timezone": timezone,
                    "type": "phone",
                    "resolution": "{1440,3120}",
                },
            },
            separators=(",", ":"),
        )
        payload = self._request_json(
            "POST",
            f"{API_ENDPOINT}/cradles/pairedUsers/v3",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        if payload.get("errorType") == "API_FAILED":
            raise CloudProvisioningError(
                str(payload.get("message") or "certificate provisioning failed")
            )
        device_config = payload.get("device_config")
        if not isinstance(device_config, dict):
            raise CloudProvisioningError(
                "Cradlewise certificate response has no device configuration"
            )
        group_ca = device_config.get("group_ca_cert")
        object_keys = device_config.get("s3_object_keys")
        if not isinstance(group_ca, str) or not group_ca.strip():
            raise CloudProvisioningError(
                "Cradlewise certificate response has no group CA"
            )
        if not isinstance(object_keys, list) or not object_keys:
            raise CloudProvisioningError(
                "Cradlewise certificate response has no certificate objects"
            )

        raw = self._require_raw_credentials()
        s3 = boto3.client(
            "s3",
            region_name=REGION,
            aws_access_key_id=raw["AccessKeyId"],
            aws_secret_access_key=raw["SecretKey"],
            aws_session_token=raw["SessionToken"],
        )
        pem_objects = [self._download_s3_text(s3, str(key)) for key in object_keys]
        client_certificate = next(
            (value for value in pem_objects if "BEGIN CERTIFICATE" in value),
            None,
        )
        private_key = next(
            (value for value in pem_objects if "PRIVATE KEY" in value),
            None,
        )
        if client_certificate is None or private_key is None:
            raise CloudProvisioningError(
                "Cradlewise certificate objects did not contain a certificate and key"
            )

        device_id = device_config.get("device_id")
        if not isinstance(device_id, str) or not device_id.strip():
            first_key = str(object_keys[0])
            device_id = first_key.rsplit("/", 1)[-1].removesuffix(".pem")
        if not device_id:
            raise CloudProvisioningError(
                "Cradlewise certificate response has no device identity"
            )
        return ProvisionedCredentials(
            device_id=device_id.strip(),
            client_certificate=client_certificate,
            client_private_key=private_key,
            group_ca_certificate=group_ca,
        )

    def list_user_devices(self, account: CradleAccount) -> list[UserDevice]:
        """List this account's device registrations for one baby profile."""
        payload = self._request_json(
            "GET",
            (
                f"{API_ENDPOINT}/babyProfiles/{account.baby_id}/userDevices"
                f"?email_id={quote(self.email)}"
            ),
        )
        user_devices = payload.get("user_devices")
        if not isinstance(user_devices, list):
            raise CloudApiError("Cradlewise user devices response has no device list")

        result = []
        for user in user_devices:
            if not isinstance(user, dict):
                continue
            email = user.get("email_id")
            if not isinstance(email, str) or email.casefold() != self.email.casefold():
                continue
            devices = user.get("devices")
            if not isinstance(devices, list):
                continue
            for device in devices:
                if not isinstance(device, dict):
                    continue
                device_id = device.get("device_id")
                if not isinstance(device_id, str) or not device_id.strip():
                    continue
                result.append(
                    UserDevice(
                        device_id=device_id.strip(),
                        device_name=_optional_string(device.get("device_name")),
                        os=_optional_string(device.get("os")),
                        model=_optional_string(device.get("model")),
                    )
                )
        return result

    def remove_user_devices(
        self,
        account: CradleAccount,
        device_ids: list[str],
    ) -> list[str]:
        """Remove exact device registrations and return confirmed removals."""
        requested = [device_id.strip() for device_id in device_ids if device_id.strip()]
        if not requested:
            raise CloudApiError("at least one device registration is required")
        body = json.dumps({"device_ids": requested}, separators=(",", ":"))
        payload = self._request_json(
            "POST",
            f"{API_ENDPOINT}/babyProfiles/{account.baby_id}/userDevices/remove",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        removed = payload.get("removed_devices")
        if not isinstance(removed, list) or not all(
            isinstance(device_id, str) for device_id in removed
        ):
            raise CloudApiError(
                "Cradlewise remove devices response has no confirmed device list"
            )
        return [device_id.strip() for device_id in removed if device_id.strip()]

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        body: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        credentials = self._require_credentials()
        response = self._send(method, url, credentials, body=body, headers=headers)
        if response.status_code in {401, 403}:
            self.authenticate()
            credentials = self._require_credentials()
            response = self._send(
                method,
                url,
                credentials,
                body=body,
                headers=headers,
            )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise CloudApiError(
                f"Cradlewise cloud request failed: HTTP {response.status_code}"
            ) from exc
        try:
            payload = response.json()
        except requests.JSONDecodeError as exc:
            raise CloudApiError("Cradlewise cloud response was not JSON") from exc
        if not isinstance(payload, dict):
            raise CloudApiError("Cradlewise cloud response was not an object")
        return payload

    def _send(
        self,
        method: str,
        url: str,
        credentials: Credentials,
        *,
        body: str | None,
        headers: dict[str, str] | None,
    ) -> requests.Response:
        signed_headers = sign_request(
            method,
            url,
            credentials,
            body=body,
            headers=headers,
        )
        try:
            return self._session.request(
                method,
                url,
                headers=signed_headers,
                data=body,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise CloudApiError("Cradlewise cloud request failed") from exc

    def _require_credentials(self) -> Credentials:
        if self._credentials is None:
            self.authenticate()
        if self._credentials is None:
            raise CloudAuthenticationError(
                "Cradlewise authentication returned no AWS credentials"
            )
        return self._credentials

    def _require_raw_credentials(self) -> dict[str, Any]:
        self._require_credentials()
        if self._raw_credentials is None:
            raise CloudAuthenticationError(
                "Cradlewise authentication returned no raw AWS credentials"
            )
        return self._raw_credentials

    @staticmethod
    def _download_s3_text(s3: Any, key: str) -> str:
        last_error: Exception | None = None
        for candidate in (key, f"public/{key}"):
            try:
                response = s3.get_object(Bucket=S3_BUCKET, Key=candidate)
                value = response["Body"].read().decode("utf-8")
                if value.strip():
                    return value
            except (BotoCoreError, ClientError, KeyError, OSError, UnicodeError) as exc:
                last_error = exc
        error = CloudProvisioningError(
            f"could not download provisioned certificate object {key}"
        )
        if last_error is None:
            raise error
        raise error from last_error


def _local_ip(payload: dict[str, Any]) -> str | None:
    address = (
        payload.get("info", {}).get("connectivity", {}).get("localIP")
        if isinstance(payload.get("info"), dict)
        else None
    )
    return address.strip() if isinstance(address, str) and address.strip() else None


def _optional_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _android_device_name() -> str:
    """Return the model-and-ID shape used by the Android application."""
    return f"{secrets.choice(ANDROID_DEVICE_MODELS)}_{secrets.token_hex(8)}"
