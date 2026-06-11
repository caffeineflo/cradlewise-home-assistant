"""Binary sensors for the Cradlewise local bridge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CRADLE_ID, DOMAIN
from .status_helpers import path_value


@dataclass(frozen=True, kw_only=True)
class CradlewiseBinarySensorDescription(BinarySensorEntityDescription):
    """Description for a bridge binary sensor."""

    path: tuple[str, ...]


BINARY_SENSORS: tuple[CradlewiseBinarySensorDescription, ...] = (
    CradlewiseBinarySensorDescription(
        key="bridge_healthy",
        name="Bridge Healthy",
        path=("bridge", "healthy"),
    ),
    CradlewiseBinarySensorDescription(
        key="mqtt_connected",
        name="MQTT Connected",
        path=("mqtt", "connected"),
    ),
    CradlewiseBinarySensorDescription(
        key="audio_track",
        name="Audio Track",
        path=("media", "audio_track"),
    ),
    CradlewiseBinarySensorDescription(
        key="baby_present",
        name="Baby Present",
        path=("device_state", "baby_present"),
        device_class=BinarySensorDeviceClass.OCCUPANCY,
    ),
    CradlewiseBinarySensorDescription(
        key="baby_needs_attention",
        name="Baby Needs Attention",
        path=("device_state", "baby_needs_attention"),
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    CradlewiseBinarySensorDescription(
        key="baby_needs_help",
        name="Baby Needs Help",
        path=("device_state", "baby_needs_help"),
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    CradlewiseBinarySensorDescription(
        key="crib_helping",
        name="Crib Helping",
        path=("device_state", "crib_helping"),
    ),
    CradlewiseBinarySensorDescription(
        key="bouncing",
        name="Bouncing",
        path=("device_state", "bouncing"),
    ),
    CradlewiseBinarySensorDescription(
        key="music_playing",
        name="Music Playing",
        path=("device_state", "music_playing"),
    ),
    CradlewiseBinarySensorDescription(
        key="light_on",
        name="Night Light",
        path=("device_state", "light_on"),
    ),
    CradlewiseBinarySensorDescription(
        key="loud_sound_detected",
        name="Loud Sound Detected",
        path=("device_state", "loud_sound_detected"),
        device_class=BinarySensorDeviceClass.SOUND,
    ),
    CradlewiseBinarySensorDescription(
        key="inside_sleep_schedule",
        name="In Sleep Schedule",
        path=("device_state", "inside_sleep_schedule"),
    ),
    CradlewiseBinarySensorDescription(
        key="inside_soothing_window",
        name="In Soothing Window",
        path=("device_state", "inside_soothing_window"),
    ),
    CradlewiseBinarySensorDescription(
        key="rocking_not_effective",
        name="Rocking Not Effective",
        path=("device_state", "rocking_not_effective"),
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    CradlewiseBinarySensorDescription(
        key="charging",
        name="Charging",
        path=("device_state", "charging"),
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
    ),
    CradlewiseBinarySensorDescription(
        key="power_supply_removed",
        name="Power Supply Removed",
        path=("device_state", "power_supply_removed"),
        device_class=BinarySensorDeviceClass.PLUG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cradlewise status binary sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id].get("coordinator")
    if coordinator is None:
        return

    async_add_entities(
        CradlewiseStatusBinarySensor(entry, coordinator, description)
        for description in BINARY_SENSORS
    )


class CradlewiseStatusBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor backed by the bridge status API."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator,
        description: CradlewiseBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._cradle_id = entry.data[CONF_CRADLE_ID]
        self._attr_name = description.name
        self._attr_unique_id = f"{self._cradle_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._cradle_id)},
            manufacturer="Cradlewise",
            name=entry.data.get(CONF_NAME, "Cradlewise Local"),
        )

    @property
    def is_on(self) -> bool | None:
        value: Any = path_value(self.coordinator.data, self.entity_description.path)
        if value is None:
            return None
        return bool(value)
