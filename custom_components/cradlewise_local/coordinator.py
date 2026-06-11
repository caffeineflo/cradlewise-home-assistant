"""Data coordinator for the Cradlewise local bridge status API."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_BRIDGE_STATUS_URL, DOMAIN
from .status_helpers import build_state_url

_LOGGER = logging.getLogger(__name__)


class CradlewiseStatusCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll the bridge status API."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=15),
        )
        self._session = async_get_clientsession(hass)
        self._state_url = build_state_url(entry.data[CONF_BRIDGE_STATUS_URL])

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            response = await self._session.get(self._state_url, timeout=10)
            if response.status != 200:
                raise UpdateFailed(f"HTTP {response.status} from bridge status API")
            data = await response.json()
            if not isinstance(data, dict):
                raise UpdateFailed("Bridge status API returned non-object JSON")
            return data
        except UpdateFailed:
            raise
        except Exception as exc:
            raise UpdateFailed(f"Bridge status API request failed: {exc}") from exc
