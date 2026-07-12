"""
Shared Cradlewise API client.

Handles Cognito authentication, SigV4 request signing, and REST API calls
against the Cradlewise backend. Used by both fetch_certs.py and stream_local.py.
"""

import json
import logging
import os
from getpass import getpass

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
from pycognito import Cognito

# Cradlewise Amplify configuration (from amplifyconfiguration.json in the APK)
USER_POOL_ID = "us-east-1_hRGLsOxun"
CLIENT_ID = "4jnn2bbtroa3e6ra73dc8m8luh"
CLIENT_SECRET = "qfmc9tv70upcacajmhpl4a9n3orehteo93icbng0fljkt6916em"
IDENTITY_POOL_ID = "us-east-1:53b70db5-7440-4ecf-8dac-d6202eb6c1d2"
REGION = "us-east-1"
API_ENDPOINT = "https://backend.cradlewise.com/prod-latest"
S3_BUCKET = "cradlewise-device-certs"
REQUEST_TIMEOUT_SECONDS = 10

_LOGGER = logging.getLogger(__name__)


class CradlewiseAPIError(RuntimeError):
    """Raised when every Cradlewise API fallback fails."""


def get_credentials_interactive():
    """Get Cradlewise email/password from env vars or interactive prompt."""
    email = os.environ.get("CRADLEWISE_EMAIL")
    password = os.environ.get("CRADLEWISE_PASSWORD")
    if not email:
        email = input("Cradlewise email: ").strip()
    if not password:
        password = getpass("Cradlewise password: ")
    return email, password


def authenticate(email, password):
    """Authenticate with Cognito and return (cognito, id_token).

    Raises Exception on auth failure.
    """
    cognito = Cognito(
        USER_POOL_ID,
        CLIENT_ID,
        username=email,
        client_secret=CLIENT_SECRET,
    )
    cognito.authenticate(password=password)
    return cognito, cognito.id_token


def get_aws_credentials(id_token):
    """Exchange a Cognito id_token for temporary AWS credentials.

    Returns (Credentials, raw_creds_dict) where raw_creds_dict has
    AccessKeyId, SecretKey, SessionToken for direct boto3 use.
    """
    identity_client = boto3.client("cognito-identity", region_name=REGION)
    logins = {
        f"cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}": id_token,
    }

    identity_resp = identity_client.get_id(
        IdentityPoolId=IDENTITY_POOL_ID,
        Logins=logins,
    )
    creds_resp = identity_client.get_credentials_for_identity(
        IdentityId=identity_resp["IdentityId"],
        Logins=logins,
    )
    aws_creds = creds_resp["Credentials"]
    credentials = Credentials(
        access_key=aws_creds["AccessKeyId"],
        secret_key=aws_creds["SecretKey"],
        token=aws_creds["SessionToken"],
    )
    return credentials, aws_creds


def sign_request(method, url, credentials, body=None, headers=None):
    """Sign an HTTP request with SigV4 for the execute-api service."""
    if headers is None:
        headers = {}
    request = AWSRequest(method=method, url=url, data=body, headers=headers)
    SigV4Auth(credentials, "execute-api", REGION).add_auth(request)
    return dict(request.headers)


def get_accounts(email, credentials):
    """Fetch baby/cradle accounts for the given email.

    Returns list of account dicts with baby_id, cradle_id, name, etc.
    """
    url = f"{API_ENDPOINT}/accounts?emailId={requests.utils.quote(email)}"
    headers = sign_request("GET", url, credentials)
    resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
    resp.raise_for_status()
    return resp.json().get("accounts", [])


def get_cradle_ip(cradle_id, credentials):
    """Get the crib's local IP from the Cradlewise cloud API.

    Tries the v2 endpoint first (state_message -> info.connectivity.localIP),
    then falls back to v1 (local_ip field directly).

    Returns the IP string, or None if unavailable.
    """
    v2_error = None
    v2_url = f"{API_ENDPOINT}/cradles/{cradle_id}/onlineStatus/v2"
    headers = sign_request("GET", v2_url, credentials)
    try:
        resp = requests.get(
            v2_url,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        state_message_str = data.get("state_message")
        if state_message_str:
            state_msg = json.loads(state_message_str)
            ip = state_msg.get("info", {}).get("connectivity", {}).get("localIP")
            if ip:
                return ip
    except (requests.RequestException, TypeError, ValueError) as exc:
        v2_error = exc
        _LOGGER.warning(
            "Cradlewise online status v2 failed for cradle %s; trying v1: %s",
            cradle_id,
            exc,
        )

    v1_error = None
    v1_url = f"{API_ENDPOINT}/cradles/{cradle_id}/onlineStatus"
    headers = sign_request("GET", v1_url, credentials)
    try:
        resp = requests.get(
            v1_url,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        ip = data.get("local_ip")
        if ip:
            return ip
    except (requests.RequestException, TypeError, ValueError) as exc:
        v1_error = exc
        _LOGGER.error(
            "Cradlewise online status v1 failed for cradle %s: %s",
            cradle_id,
            exc,
        )

    if v2_error is not None and v1_error is not None:
        raise CradlewiseAPIError(
            f"Cradlewise online status failed for cradle {cradle_id}: "
            f"v2={v2_error}; v1={v1_error}"
        ) from v1_error

    return None
