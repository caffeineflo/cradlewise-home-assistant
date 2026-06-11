"""Camera platform for Cradlewise local bridge streams."""

from __future__ import annotations

import logging

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.components.ffmpeg import async_get_image
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from haffmpeg.tools import IMAGE_JPEG

from .const import CONF_CRADLE_ID, CONF_SNAPSHOT_URL, CONF_STREAM_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cradlewise camera from a config entry."""
    async_add_entities([CradlewiseBridgeCamera(entry)])


class CradlewiseBridgeCamera(Camera):
    """Camera entity backed by the local Cradlewise bridge."""

    _attr_supported_features = CameraEntityFeature.STREAM
    _attr_has_entity_name = False
    _attr_brand = "Cradlewise"

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__()
        self._entry = entry
        self._cradle_id = entry.data[CONF_CRADLE_ID]
        self._stream_url = entry.data[CONF_STREAM_URL]
        self._snapshot_url = entry.data.get(CONF_SNAPSHOT_URL)
        self._attr_name = entry.data.get(CONF_NAME, "Cradlewise Local")
        self._attr_unique_id = f"{self._cradle_id}_camera"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._cradle_id)},
            manufacturer="Cradlewise",
            name=self._attr_name,
        )

    async def stream_source(self) -> str | None:
        """Return the raw stream URL for HA's stream component."""
        if " -i " in self._stream_url:
            return self._stream_url.rsplit(" -i ", maxsplit=1)[-1]
        return self._stream_url

    def _ffmpeg_input(self) -> str:
        if self._stream_url.startswith("rtsp://"):
            return f"-rtsp_transport tcp -i {self._stream_url}"
        return self._stream_url

    async def async_camera_image(
        self,
        width: int | None = None,
        height: int | None = None,
    ) -> bytes | None:
        """Return a still image if the bridge exposes one."""
        if not self._snapshot_url:
            return await async_get_image(
                self.hass,
                self._ffmpeg_input(),
                output_format=IMAGE_JPEG,
            )

        session = async_get_clientsession(self.hass)
        try:
            response = await session.get(self._snapshot_url, timeout=10)
            if response.status != 200:
                _LOGGER.debug(
                    "Snapshot request failed for %s: HTTP %s",
                    self.entity_id,
                    response.status,
                )
                return None
            return await response.read()
        except Exception as exc:
            _LOGGER.debug("Snapshot request failed for %s: %s", self.entity_id, exc)
            return None
