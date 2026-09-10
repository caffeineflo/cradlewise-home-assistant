"""
Shared Cradlewise API client.

Handles Cognito authentication, SigV4 request signing, and REST API calls
against the Cradlewise backend. Used by both fetch_certs.py and stream_local.py.
"""

import json
import logging
import os
from getpass import getpass

import requests
from cradlewise_client.cloud import API_ENDPOINT as API_ENDPOINT
from cradlewise_client.cloud import CLIENT_ID as CLIENT_ID
from cradlewise_client.cloud import CLIENT_SECRET as CLIENT_SECRET
from cradlewise_client.cloud import IDENTITY_POOL_ID as IDENTITY_POOL_ID
from cradlewise_client.cloud import REGION as REGION
from cradlewise_client.cloud import S3_BUCKET as S3_BUCKET
from cradlewise_client.cloud import USER_POOL_ID as USER_POOL_ID
from cradlewise_client.cloud import authenticate as authenticate
from cradlewise_client.cloud import get_aws_credentials as get_aws_credentials
from cradlewise_client.cloud import sign_request as sign_request

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
