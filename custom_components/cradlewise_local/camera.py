"""Camera platform for Cradlewise local bridge streams."""

from __future__ import annotations

import logging

import aiohttp
from haffmpeg.tools import IMAGE_JPEG
from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.components.camera.prefs import get_dynamic_camera_stream_settings
from homeassistant.components.ffmpeg import async_get_image
from homeassistant.components.stream import HLS_PROVIDER
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CradlewiseConfigEntry
from .config_helpers import same_url_origin, snapshot_url_from_status_url
from .const import (
    CONF_BEARER_TOKEN,
    CONF_BRIDGE_STATUS_URL,
    CONF_CRADLE_ID,
    CONF_SNAPSHOT_URL,
    CONF_STREAM_URL,
)
from .coordinator import CradlewiseStatusCoordinator, request_headers
from .entity import device_info
from .status_helpers import path_value, strict_bool

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CradlewiseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Cradlewise camera from a config entry."""
    async_add_entities([CradlewiseBridgeCamera(entry, entry.runtime_data.coordinator)])


class CradlewiseBridgeCamera(Camera):
    """Camera entity backed by the local Cradlewise bridge."""

    _attr_supported_features = CameraEntityFeature.STREAM
    _attr_has_entity_name = True
    _attr_translation_key = "camera"
    _attr_brand = "Cradlewise"

    def __init__(
        self,
        entry: CradlewiseConfigEntry,
        coordinator: CradlewiseStatusCoordinator | None,
    ) -> None:
        super().__init__()
        self._entry = entry
        self._coordinator = coordinator
        self._stream_url = entry.data[CONF_STREAM_URL]
        self._snapshot_url = entry.data.get(CONF_SNAPSHOT_URL)
        if not self._snapshot_url and entry.data.get(CONF_BRIDGE_STATUS_URL):
            self._snapshot_url = snapshot_url_from_status_url(
                entry.data[CONF_BRIDGE_STATUS_URL]
            )
        self._attr_unique_id = f"{entry.data[CONF_CRADLE_ID]}_camera"

    @property
    def available(self) -> bool:
        """Return whether the optional status endpoint is reachable."""
        return self._coordinator is None or (
            self._coordinator.last_update_success
            and strict_bool(path_value(self._coordinator.data, ("bridge", "healthy")))
            is True
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return stable device registry information."""
        return device_info(self._entry, self._coordinator)

    async def async_added_to_hass(self) -> None:
        """Subscribe the camera to coordinator availability updates."""
        await super().async_added_to_hass()
        if self._coordinator is not None:
            self.async_on_remove(
                self._coordinator.async_add_listener(self.async_write_ha_state)
            )
        stream_settings = await get_dynamic_camera_stream_settings(
            self.hass, self.entity_id
        )
        if stream_settings.preload_stream:
            stream = await self.async_create_stream()
            if stream is not None:
                stream.add_provider(HLS_PROVIDER)
                await stream.start()

    async def async_will_remove_from_hass(self) -> None:
        """Stop a preloaded stream before the camera entity is replaced."""
        try:
            if self.stream is not None:
                stream_settings = self.stream.dynamic_stream_settings
                preload_stream = stream_settings.preload_stream
                stream_settings.preload_stream = False
                try:
                    await self.stream.stop()
                finally:
                    stream_settings.preload_stream = preload_stream
        finally:
            self.stream = None
            await super().async_will_remove_from_hass()

    async def stream_source(self) -> str | None:
        """Return the raw stream URL for HA's stream component."""
        return self._stream_url

    def _ffmpeg_input(self) -> str:
        if self._stream_url.startswith(("rtsp://", "rtsps://")):
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
        bridge_status_url = self._entry.data.get(CONF_BRIDGE_STATUS_URL)
        bearer_token = None
        if bridge_status_url and same_url_origin(self._snapshot_url, bridge_status_url):
            bearer_token = (
                self._coordinator.bearer_token
                if self._coordinator is not None
                else self._entry.data.get(CONF_BEARER_TOKEN)
            )
        try:
            async with session.get(
                self._snapshot_url,
                headers=request_headers(bearer_token),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status != 200:
                    await response.read()
                    _LOGGER.debug(
                        "Snapshot request failed for %s: HTTP %s",
                        self.entity_id,
                        response.status,
                    )
                    return None
                return await response.read()
        except (aiohttp.ClientError, TimeoutError) as exc:
            _LOGGER.debug("Snapshot request failed for %s: %s", self.entity_id, exc)
            return None
