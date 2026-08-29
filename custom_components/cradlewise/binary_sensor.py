"""Binary sensor platform for Cradlewise."""

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
from .coordinator import CradlewiseCoordinator
from .entity import DEVICE_STATE_FRESHNESS, CradlewiseCoordinatorEntity
from .status_helpers import path_value, strict_bool


@dataclass(frozen=True, kw_only=True)
class CradlewiseBinarySensorDescription(BinarySensorEntityDescription):
    """Describe one useful Cradlewise binary sensor."""

    path: tuple[str, ...]
    freshness_paths: tuple[tuple[str, ...], ...] = DEVICE_STATE_FRESHNESS


BINARY_SENSORS: tuple[CradlewiseBinarySensorDescription, ...] = (
    CradlewiseBinarySensorDescription(
        key="bridge_healthy",
        translation_key="connectivity",
        path=("bridge", "provider_healthy"),
        freshness_paths=(),
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    CradlewiseBinarySensorDescription(
        key="baby_present",
        translation_key="baby_present",
        path=("device_state", "baby_present"),
        device_class=BinarySensorDeviceClass.OCCUPANCY,
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
        key="lower_breath_rate_alert",
        translation_key="lower_breath_rate_alert",
        path=("device_state", "lower_breath_rate_alert"),
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CradlewiseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cradlewise binary sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        CradlewiseStatusBinarySensor(entry, coordinator, description)
        for description in BINARY_SENSORS
    )


class CradlewiseStatusBinarySensor(CradlewiseCoordinatorEntity, BinarySensorEntity):
    """Binary sensor backed by the selected providers."""

    entity_description: CradlewiseBinarySensorDescription

    def __init__(
        self,
        entry: CradlewiseConfigEntry,
        coordinator: CradlewiseCoordinator,
        description: CradlewiseBinarySensorDescription,
    ) -> None:
        super().__init__(entry, coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        """Require current provider data and a valid boolean value."""
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
