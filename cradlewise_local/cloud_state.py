"""Optional Cradlewise cloud state polling for the local bridge."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import requests
from botocore.credentials import Credentials

from cradlewise_api import API_ENDPOINT, authenticate, get_aws_credentials, sign_request

from .config import BridgeConfig
from .status import BridgeStatusStore

log = logging.getLogger(__name__)


class CloudStateError(RuntimeError):
    """Raised when cloud state cannot be fetched."""


@dataclass
class CradlewiseCloudStateClient:
    """Blocking Cradlewise REST client for cloud-backed device state."""

    email: str
    password: str
    timeout_seconds: int = 10
    _credentials: Credentials | None = None

    def authenticate(self) -> None:
        """Authenticate and cache temporary AWS credentials."""
        _, id_token = authenticate(self.email, self.password)
        credentials, _ = get_aws_credentials(id_token)
        self._credentials = credentials

    def get_cradle_state(self, cradle_id: str) -> dict[str, Any]:
        """Fetch the cloud state/shadow payload for a cradle."""
        return self._signed_get_json(f"{API_ENDPOINT}/cradles/{cradle_id}/state")

    def _signed_get_json(self, url: str) -> dict[str, Any]:
        if self._credentials is None:
            self.authenticate()

        assert self._credentials is not None
        headers = sign_request("GET", url, self._credentials)
        response = requests.get(url, headers=headers, timeout=self.timeout_seconds)

        if response.status_code in {401, 403}:
            self.authenticate()
            assert self._credentials is not None
            headers = sign_request("GET", url, self._credentials)
            response = requests.get(url, headers=headers, timeout=self.timeout_seconds)

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise CloudStateError(
                f"Cradlewise cloud state request failed: HTTP {response.status_code}"
            ) from exc

        payload = response.json()
        if not isinstance(payload, dict):
            raise CloudStateError("Cradlewise cloud state response was not an object")
        return payload


async def poll_cloud_state(
    config: BridgeConfig,
    status_store: BridgeStatusStore,
) -> None:
    """Poll cloud state until cancelled and merge it into bridge status."""
    if not config.cloud_state_enabled:
        return

    assert config.cloud_email is not None
    assert config.cloud_password is not None
    client = CradlewiseCloudStateClient(
        email=config.cloud_email,
        password=config.cloud_password,
    )
    log.info(
        "Cloud state polling enabled for cradle %s every %d seconds",
        config.cradle_id,
        config.cloud_state_poll_interval,
    )

    while True:
        try:
            payload = await asyncio.to_thread(client.get_cradle_state, config.cradle_id)
            status_store.update_device_state(payload, source="cloud")
            log.debug("Cloud device state updated")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Cloud state poll failed: %s", exc)

        await asyncio.sleep(config.cloud_state_poll_interval)
