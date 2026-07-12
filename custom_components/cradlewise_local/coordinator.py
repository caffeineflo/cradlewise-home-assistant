"""Data coordinator for the Cradlewise local bridge status API."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_BEARER_TOKEN,
    CONF_BRIDGE_STATUS_URL,
    CONF_CRADLE_ID,
    DEVICE_STATE_MAX_AGE_SECONDS,
    DOMAIN,
)
from .status_helpers import (
    build_command_url,
    build_state_url,
    device_state_is_available,
    strict_bool,
)

_LOGGER = logging.getLogger(__name__)


class BridgeApiError(HomeAssistantError):
    """Base error for bridge validation and requests."""


class BridgeAuthenticationError(BridgeApiError):
    """Raised when the bridge rejects the bearer token."""


class BridgeIdentityError(BridgeApiError):
    """Raised when the endpoint belongs to another cradle."""


def request_headers(bearer_token: str | None) -> dict[str, str] | None:
    """Build bridge request headers without retaining an empty credential."""
    if not bearer_token:
        return None
    return {"Authorization": f"Bearer {bearer_token}"}


async def async_fetch_bridge_state(
    session: aiohttp.ClientSession,
    state_url: str,
    bearer_token: str | None,
    expected_cradle_id: str,
) -> dict[str, Any]:
    """Fetch and validate one bridge state response."""
    async with session.get(
        state_url,
        headers=request_headers(bearer_token),
        timeout=aiohttp.ClientTimeout(total=10),
    ) as response:
        if response.status in {401, 403}:
            await response.read()
            raise BridgeAuthenticationError("Bridge authentication failed")
        if response.status != 200:
            await response.read()
            raise BridgeApiError(f"Bridge returned HTTP {response.status}")
        try:
            data = await response.json(content_type=None)
        except (ValueError, aiohttp.ContentTypeError) as exc:
            raise BridgeApiError("Bridge returned invalid JSON") from exc

    if not isinstance(data, dict):
        raise BridgeApiError("Bridge returned non-object JSON")
    bridge = data.get("bridge")
    if not isinstance(bridge, dict) or not isinstance(bridge.get("cradle_id"), str):
        raise BridgeApiError("Bridge response is missing bridge.cradle_id")
    if bridge["cradle_id"] != expected_cradle_id:
        raise BridgeIdentityError(
            "Bridge cradle ID does not match the configured cradle"
        )
    return data


class CradlewiseStatusCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll the bridge status API."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry[Any]) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=15),
        )
        self._session = async_get_clientsession(hass)
        self._state_url = build_state_url(entry.data[CONF_BRIDGE_STATUS_URL])
        self._command_url = build_command_url(entry.data[CONF_BRIDGE_STATUS_URL])
        self._bearer_token = entry.data.get(CONF_BEARER_TOKEN)
        self._cradle_id = entry.data[CONF_CRADLE_ID]

    @property
    def bearer_token(self) -> str | None:
        """Return the optional token for camera snapshot requests."""
        return self._bearer_token

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await async_fetch_bridge_state(
                self._session,
                self._state_url,
                self._bearer_token,
                self._cradle_id,
            )
        except (BridgeApiError, aiohttp.ClientError, TimeoutError) as exc:
            raise UpdateFailed(f"Bridge status request failed: {exc}") from exc

    async def async_send_command(self, command: str, value: Any) -> None:
        """Send a validated command through the bridge."""
        if strict_bool(self.data.get("mqtt", {}).get("connected")) is not True:
            raise HomeAssistantError("Bridge MQTT publisher is unavailable")
        if not device_state_is_available(
            self.data,
            DEVICE_STATE_MAX_AGE_SECONDS,
        ):
            raise HomeAssistantError("Cradle device state is unavailable")
        try:
            async with self._session.post(
                self._command_url,
                headers=request_headers(self._bearer_token),
                json={"command": command, "value": value},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                detail = await response.text()
                if response.status in {401, 403}:
                    raise HomeAssistantError("Bridge authentication failed")
                if response.status != 200:
                    raise HomeAssistantError(
                        f"Bridge command failed with HTTP {response.status}: {detail}"
                    )
        except HomeAssistantError:
            raise
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise HomeAssistantError(f"Bridge command request failed: {exc}") from exc
        await self.async_request_refresh()
