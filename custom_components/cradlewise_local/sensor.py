"""Sensors for the Cradlewise local bridge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CRADLE_ID, DOMAIN
from .status_helpers import path_value


@dataclass(frozen=True, kw_only=True)
class CradlewiseSensorDescription(SensorEntityDescription):
    """Description for a bridge status sensor."""

    path: tuple[str, ...]


SENSORS: tuple[CradlewiseSensorDescription, ...] = (
    CradlewiseSensorDescription(
        key="webrtc_connection_state",
        name="WebRTC Connection State",
        path=("webrtc", "connection_state"),
    ),
    CradlewiseSensorDescription(
        key="ice_connection_state",
        name="ICE Connection State",
        path=("webrtc", "ice_connection_state"),
    ),
    CradlewiseSensorDescription(
        key="video_frames",
        name="Video Frames",
        path=("media", "video_frames"),
    ),
    CradlewiseSensorDescription(
        key="audio_frames",
        name="Audio Frames",
        path=("media", "audio_frames"),
    ),
    CradlewiseSensorDescription(
        key="resolution",
        name="Resolution",
        path=("media", "resolution"),
    ),
    CradlewiseSensorDescription(
        key="uptime",
        name="Bridge Uptime",
        path=("bridge", "uptime_seconds"),
        native_unit_of_measurement=UnitOfTime.SECONDS,
    ),
    CradlewiseSensorDescription(
        key="cradle_state",
        name="Cradle State",
        path=("cradle_state", "state"),
    ),
    CradlewiseSensorDescription(
        key="cradle_op_mode",
        name="Cradle Op Mode",
        path=("cradle_state", "op_mode"),
    ),
    CradlewiseSensorDescription(
        key="wifi_strength",
        name="WiFi Strength",
        path=("cradle_state", "wifi_strength"),
        native_unit_of_measurement="dBm",
    ),
    CradlewiseSensorDescription(
        key="wifi_ssid",
        name="WiFi SSID",
        path=("cradle_state", "wifi_ssid"),
    ),
    CradlewiseSensorDescription(
        key="local_ip",
        name="Local IP",
        path=("cradle_state", "local_ip"),
    ),
    CradlewiseSensorDescription(
        key="sleep_state",
        name="Sleep State",
        path=("device_state", "sleep_state"),
    ),
    CradlewiseSensorDescription(
        key="sleep_phase",
        name="Sleep Phase",
        path=("device_state", "sleep_phase"),
    ),
    CradlewiseSensorDescription(
        key="cradle_mode",
        name="Cradle Mode",
        path=("device_state", "cradle_mode"),
    ),
    CradlewiseSensorDescription(
        key="bounce_mode",
        name="Bounce Mode",
        path=("device_state", "bounce_mode"),
    ),
    CradlewiseSensorDescription(
        key="bounce_setting",
        name="Bounce Setting",
        path=("device_state", "bounce_setting"),
    ),
    CradlewiseSensorDescription(
        key="bounce_amplitude",
        name="Bounce Amplitude",
        path=("device_state", "bounce_amplitude"),
    ),
    CradlewiseSensorDescription(
        key="responsivity_setting",
        name="Responsivity Setting",
        path=("device_state", "responsivity_setting"),
    ),
    CradlewiseSensorDescription(
        key="music_mood",
        name="Music Mood",
        path=("device_state", "music_mood"),
    ),
    CradlewiseSensorDescription(
        key="music_volume",
        name="Music Volume",
        path=("device_state", "music_volume"),
    ),
    CradlewiseSensorDescription(
        key="music_mode",
        name="Music Mode",
        path=("device_state", "music_mode"),
    ),
    CradlewiseSensorDescription(
        key="light_intensity",
        name="Light Intensity",
        path=("device_state", "light_intensity"),
    ),
    CradlewiseSensorDescription(
        key="battery_life",
        name="Battery Life",
        path=("device_state", "battery_life"),
    ),
    CradlewiseSensorDescription(
        key="sleep_time",
        name="Sleep Time",
        path=("device_state", "sleep_time"),
    ),
    CradlewiseSensorDescription(
        key="wake_up_time",
        name="Wake Up Time",
        path=("device_state", "wake_up_time"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cradlewise status sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id].get("coordinator")
    if coordinator is None:
        return

    async_add_entities(
        CradlewiseStatusSensor(entry, coordinator, description)
        for description in SENSORS
    )


class CradlewiseStatusSensor(CoordinatorEntity, SensorEntity):
    """Sensor backed by the bridge status API."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator,
        description: CradlewiseSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._cradle_id = entry.data[CONF_CRADLE_ID]
        self._attr_name = description.name
        self._attr_unique_id = f"{self._cradle_id}_{description.key}"
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._cradle_id)},
            manufacturer="Cradlewise",
            name=entry.data.get(CONF_NAME, "Cradlewise Local"),
        )

    @property
    def native_value(self) -> Any:
        return path_value(self.coordinator.data, self.entity_description.path)
