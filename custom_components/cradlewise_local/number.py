"""Number controls for the Cradlewise local bridge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CradlewiseConfigEntry
from .coordinator import CradlewiseStatusCoordinator
from .entity import DEVICE_STATE_FRESHNESS, CradlewiseCoordinatorEntity
from .status_helpers import bounded_number, path_value, strict_bool


@dataclass(frozen=True, kw_only=True)
class CradlewiseNumberDescription(NumberEntityDescription):
    """Description for a writable bridge number."""

    path: tuple[str, ...]
    command: str
    limit_path: tuple[str, ...] | None = None


def _config_number(**kwargs: Any) -> CradlewiseNumberDescription:
    return CradlewiseNumberDescription(
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        **kwargs,
    )


NUMBERS: tuple[CradlewiseNumberDescription, ...] = (
    CradlewiseNumberDescription(
        key="bounce_level",
        translation_key="bounce_level",
        path=("device_state", "bounce_level"),
        command="bounce_level",
        native_min_value=0,
        native_max_value=5,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
    CradlewiseNumberDescription(
        key="music_level",
        translation_key="music_level",
        path=("device_state", "music_level"),
        command="music_level",
        native_min_value=0,
        native_max_value=5,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
    CradlewiseNumberDescription(
        key="bounce_amplitude",
        translation_key="bounce_amplitude",
        path=("device_state", "bounce_amplitude"),
        command="bounce_amplitude",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        limit_path=("device_state", "max_bounce_limit"),
    ),
    CradlewiseNumberDescription(
        key="bounce_duration",
        translation_key="bounce_duration",
        path=("device_state", "bounce_duration"),
        command="bounce_duration",
        native_min_value=1,
        native_max_value=60,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        mode=NumberMode.SLIDER,
        limit_path=("device_state", "bounce_duration_limit"),
    ),
    _config_number(
        key="always_on_bounce_intensity",
        translation_key="always_on_bounce_intensity",
        path=("device_state", "bounce_always_on_intensity"),
        command="always_on_bounce_intensity",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
    ),
    _config_number(
        key="bounce_setting",
        translation_key="bounce_setting",
        path=("device_state", "bounce_setting"),
        command="bounce_setting",
        native_min_value=0,
        native_max_value=10,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
    CradlewiseNumberDescription(
        key="music_volume",
        translation_key="music_volume",
        path=("device_state", "music_volume"),
        command="music_volume",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        limit_path=("device_state", "max_volume_limit"),
    ),
    _config_number(
        key="keep_music_on_during_sleep_level",
        translation_key="keep_music_on_during_sleep_level",
        path=("device_state", "keep_music_on_during_sleep_level"),
        command="keep_music_on_during_sleep_level",
        native_min_value=0,
        native_max_value=5,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
    _config_number(
        key="keep_bounce_on_during_sleep_level",
        translation_key="keep_bounce_on_during_sleep_level",
        path=("device_state", "keep_bounce_on_during_sleep_level"),
        command="keep_bounce_on_during_sleep_level",
        native_min_value=0,
        native_max_value=1,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
    _config_number(
        key="auto_mode_lock_duration",
        translation_key="auto_mode_lock_duration",
        path=("device_state", "auto_mode_lock_duration"),
        command="auto_mode_lock_duration",
        native_min_value=1,
        native_max_value=60,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        mode=NumberMode.SLIDER,
    ),
    _config_number(
        key="max_bounce_limit",
        translation_key="max_bounce_limit",
        path=("device_state", "max_bounce_limit"),
        command="max_bounce_limit",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
    ),
    _config_number(
        key="max_volume_limit",
        translation_key="max_volume_limit",
        path=("device_state", "max_volume_limit"),
        command="max_volume_limit",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CradlewiseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cradlewise writable numbers."""
    coordinator = entry.runtime_data.coordinator
    if coordinator is None:
        return
    async_add_entities(
        CradlewiseBridgeNumber(entry, coordinator, description)
        for description in NUMBERS
    )


class CradlewiseBridgeNumber(CradlewiseCoordinatorEntity, NumberEntity):
    """Number entity backed by the bridge command API."""

    entity_description: CradlewiseNumberDescription

    def __init__(
        self,
        entry: CradlewiseConfigEntry,
        coordinator: CradlewiseStatusCoordinator,
        description: CradlewiseNumberDescription,
    ) -> None:
        super().__init__(entry, coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        """Require current state and an active MQTT publisher for controls."""
        return (
            super().available
            and self._fresh(DEVICE_STATE_FRESHNESS)
            and strict_bool(path_value(self.coordinator.data, ("mqtt", "connected")))
            is True
            and (
                self.entity_description.limit_path is None
                or self._dynamic_limit() is not None
            )
            and self.native_value is not None
        )

    def _dynamic_limit(self) -> float | None:
        """Return the device-advertised maximum for a limited control."""
        if self.entity_description.limit_path is None:
            return None
        return bounded_number(
            path_value(self.coordinator.data, self.entity_description.limit_path),
            minimum=self.native_min_value,
            maximum=self.entity_description.native_max_value,
        )

    @property
    def native_max_value(self) -> float:
        """Use the current device limit when the control has one."""
        dynamic_limit = self._dynamic_limit()
        if dynamic_limit is not None:
            return dynamic_limit
        maximum = self.entity_description.native_max_value
        assert maximum is not None
        return maximum

    @property
    def native_value(self) -> float | None:
        value = path_value(self.coordinator.data, self.entity_description.path)
        return bounded_number(
            value,
            minimum=self.entity_description.native_min_value,
            maximum=self.native_max_value,
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set the numeric value."""
        await self.coordinator.async_send_command(
            self.entity_description.command,
            int(value),
        )
