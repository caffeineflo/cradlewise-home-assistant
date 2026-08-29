"""Sensor platform for Cradlewise."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CradlewiseConfigEntry
from .coordinator import CradlewiseCoordinator
from .entity import DEVICE_STATE_FRESHNESS, CradlewiseCoordinatorEntity
from .status_helpers import bounded_number, nonnegative_int, path_value, positive_int


def _nonempty_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _timestamp(value: Any) -> datetime | None:
    parsed = bounded_number(value, minimum=0)
    if parsed is None:
        return None
    return datetime.fromtimestamp(parsed, tz=UTC)


def _temperature(value: Any) -> float | None:
    return bounded_number(value, minimum=-50, maximum=80)


@dataclass(frozen=True, kw_only=True)
class CradlewiseSensorDescription(SensorEntityDescription):
    """Describe one useful Cradlewise sensor."""

    path: tuple[str, ...]
    value_fn: Callable[[Any], Any]
    freshness_paths: tuple[tuple[str, ...], ...] = DEVICE_STATE_FRESHNESS


SENSORS: tuple[CradlewiseSensorDescription, ...] = (
    CradlewiseSensorDescription(
        key="device_state_source",
        translation_key="device_state_source",
        path=("device_state", "source"),
        value_fn=_nonempty_string,
        freshness_paths=(),
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    CradlewiseSensorDescription(
        key="device_state_updated_at",
        translation_key="device_state_updated_at",
        path=("device_state", "updated_at"),
        value_fn=_timestamp,
        freshness_paths=(),
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    CradlewiseSensorDescription(
        key="sleep_state",
        translation_key="sleep_state",
        path=("device_state", "sleep_state"),
        value_fn=_nonempty_string,
    ),
    CradlewiseSensorDescription(
        key="sleep_phase",
        translation_key="sleep_phase",
        path=("device_state", "sleep_phase"),
        value_fn=_nonempty_string,
    ),
    CradlewiseSensorDescription(
        key="bounce_time_remaining",
        translation_key="bounce_time_remaining",
        path=("device_state", "bounce_time_remaining"),
        value_fn=nonnegative_int,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
    ),
    CradlewiseSensorDescription(
        key="music_mood",
        translation_key="music_mood",
        path=("device_state", "music_mood"),
        value_fn=_nonempty_string,
    ),
    CradlewiseSensorDescription(
        key="music_time_remaining",
        translation_key="music_time_remaining",
        path=("device_state", "music_time_remaining"),
        value_fn=nonnegative_int,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
    ),
    CradlewiseSensorDescription(
        key="ambient_temperature",
        translation_key="ambient_temperature",
        path=("device_state", "ambient_temperature"),
        value_fn=_temperature,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    CradlewiseSensorDescription(
        key="breath_rate",
        translation_key="breath_rate",
        path=("device_state", "breath_rate"),
        value_fn=positive_int,
        native_unit_of_measurement="breaths/min",
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CradlewiseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cradlewise sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        CradlewiseStatusSensor(entry, coordinator, description)
        for description in SENSORS
    )


class CradlewiseStatusSensor(CradlewiseCoordinatorEntity, SensorEntity):
    """Sensor backed by the selected providers."""

    entity_description: CradlewiseSensorDescription

    def __init__(
        self,
        entry: CradlewiseConfigEntry,
        coordinator: CradlewiseCoordinator,
        description: CradlewiseSensorDescription,
    ) -> None:
        super().__init__(entry, coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        """Require fresh provider data and a valid value."""
        return (
            super().available
            and (
                not self.entity_description.freshness_paths
                or self._fresh(self.entity_description.freshness_paths)
            )
            and self.native_value is not None
        )

    @property
    def native_value(self) -> Any:
        value = path_value(self.coordinator.data, self.entity_description.path)
        return self.entity_description.value_fn(value)
