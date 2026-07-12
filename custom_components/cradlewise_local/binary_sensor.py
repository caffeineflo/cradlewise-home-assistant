"""Binary sensors for the Cradlewise local bridge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CradlewiseConfigEntry
from .coordinator import CradlewiseStatusCoordinator
from .entity import DEVICE_STATE_FRESHNESS, CradlewiseCoordinatorEntity
from .status_helpers import path_value, strict_bool


@dataclass(frozen=True, kw_only=True)
class CradlewiseBinarySensorDescription(BinarySensorEntityDescription):
    """Description for a bridge binary sensor."""

    path: tuple[str, ...]
    freshness_paths: tuple[tuple[str, ...], ...] = DEVICE_STATE_FRESHNESS


BINARY_SENSORS: tuple[CradlewiseBinarySensorDescription, ...] = (
    CradlewiseBinarySensorDescription(
        key="bridge_healthy",
        translation_key="bridge_healthy",
        path=("bridge", "healthy"),
        freshness_paths=(),
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    CradlewiseBinarySensorDescription(
        key="mqtt_connected",
        translation_key="mqtt_connected",
        path=("mqtt", "connected"),
        freshness_paths=(),
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    CradlewiseBinarySensorDescription(
        key="audio_track",
        translation_key="audio_track",
        path=("media", "audio_track"),
        freshness_paths=(),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    CradlewiseBinarySensorDescription(
        key="baby_present",
        translation_key="baby_present",
        path=("device_state", "baby_present"),
        device_class=BinarySensorDeviceClass.OCCUPANCY,
    ),
    CradlewiseBinarySensorDescription(
        key="baby_presence_being_determined",
        translation_key="baby_presence_being_determined",
        path=("device_state", "baby_presence_being_determined"),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    CradlewiseBinarySensorDescription(
        key="sleep_state_being_determined",
        translation_key="sleep_state_being_determined",
        path=("device_state", "sleep_state_being_determined"),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    CradlewiseBinarySensorDescription(
        key="baby_needs_attention",
        translation_key="baby_needs_attention",
        path=("device_state", "baby_needs_attention"),
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    CradlewiseBinarySensorDescription(
        key="baby_needs_help",
        translation_key="baby_needs_help",
        path=("device_state", "baby_needs_help"),
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    CradlewiseBinarySensorDescription(
        key="crib_helping",
        translation_key="crib_helping",
        path=("device_state", "crib_helping"),
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
    CradlewiseBinarySensorDescription(
        key="bounce_quiescent",
        translation_key="bounce_quiescent",
        path=("device_state", "bounce_quiescent"),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    CradlewiseBinarySensorDescription(
        key="lullabies_timer_on",
        translation_key="lullabies_timer_on",
        path=("device_state", "lullabies_timer_on"),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    CradlewiseBinarySensorDescription(
        key="light_on",
        translation_key="light_on",
        path=("device_state", "light_on"),
        device_class=BinarySensorDeviceClass.LIGHT,
    ),
    CradlewiseBinarySensorDescription(
        key="loud_sound_detected",
        translation_key="loud_sound_detected",
        path=("device_state", "loud_sound_detected"),
        device_class=BinarySensorDeviceClass.SOUND,
    ),
    CradlewiseBinarySensorDescription(
        key="inside_sleep_schedule",
        translation_key="inside_sleep_schedule",
        path=("device_state", "inside_sleep_schedule"),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    CradlewiseBinarySensorDescription(
        key="inside_soothing_window",
        translation_key="inside_soothing_window",
        path=("device_state", "inside_soothing_window"),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    CradlewiseBinarySensorDescription(
        key="rocking_not_effective",
        translation_key="rocking_not_effective",
        path=("device_state", "rocking_not_effective"),
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    CradlewiseBinarySensorDescription(
        key="obstruction_detected",
        translation_key="obstruction_detected",
        path=("device_state", "obstruction_detected"),
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    CradlewiseBinarySensorDescription(
        key="breath_trigger",
        translation_key="breath_trigger",
        path=("device_state", "breath_trigger"),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    CradlewiseBinarySensorDescription(
        key="lower_breath_rate_alert",
        translation_key="lower_breath_rate_alert",
        path=("device_state", "lower_breath_rate_alert"),
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    CradlewiseBinarySensorDescription(
        key="is_calibration_done",
        translation_key="is_calibration_done",
        path=("device_state", "is_calibration_done"),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    CradlewiseBinarySensorDescription(
        key="control_breath_enabled",
        translation_key="control_breath_enabled",
        path=("device_state", "control_breath_enabled"),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    CradlewiseBinarySensorDescription(
        key="start_recipe_on",
        translation_key="start_recipe_on",
        path=("device_state", "start_recipe_on"),
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    CradlewiseBinarySensorDescription(
        key="upload_3d_data_enabled",
        translation_key="upload_3d_data_enabled",
        path=("device_state", "upload_3d_data_enabled"),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    CradlewiseBinarySensorDescription(
        key="upload_rgb_data_enabled",
        translation_key="upload_rgb_data_enabled",
        path=("device_state", "upload_rgb_data_enabled"),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CradlewiseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cradlewise status binary sensors."""
    coordinator = entry.runtime_data.coordinator
    if coordinator is None:
        return
    async_add_entities(
        CradlewiseStatusBinarySensor(entry, coordinator, description)
        for description in BINARY_SENSORS
    )


class CradlewiseStatusBinarySensor(CradlewiseCoordinatorEntity, BinarySensorEntity):
    """Binary sensor backed by the bridge status API."""

    entity_description: CradlewiseBinarySensorDescription

    def __init__(
        self,
        entry: CradlewiseConfigEntry,
        coordinator: CradlewiseStatusCoordinator,
        description: CradlewiseBinarySensorDescription,
    ) -> None:
        super().__init__(entry, coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        """Return availability with freshness for device-backed state."""
        return (
            super().available
            and (
                not self.entity_description.freshness_paths
                or self._fresh(self.entity_description.freshness_paths)
            )
            and self.is_on is not None
        )

    @property
    def is_on(self) -> bool | None:
        value: Any = path_value(self.coordinator.data, self.entity_description.path)
        return strict_bool(value)
