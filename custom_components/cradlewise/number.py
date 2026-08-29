"""Number control platform for Cradlewise."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CradlewiseConfigEntry
from .coordinator import CradlewiseCoordinator
from .entity import DEVICE_STATE_FRESHNESS, CradlewiseCoordinatorEntity
from .status_helpers import bounded_number, path_value


@dataclass(frozen=True, kw_only=True)
class CradlewiseNumberDescription(NumberEntityDescription):
    """Describe one useful Cradlewise number control."""

    path: tuple[str, ...]
    command: str
    limit_path: tuple[str, ...] | None = None


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
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CradlewiseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cradlewise number controls."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        CradlewiseNumber(entry, coordinator, description) for description in NUMBERS
    )


class CradlewiseNumber(CradlewiseCoordinatorEntity, NumberEntity):
    """Number control backed by the selected command provider."""

    entity_description: CradlewiseNumberDescription

    def __init__(
        self,
        entry: CradlewiseConfigEntry,
        coordinator: CradlewiseCoordinator,
        description: CradlewiseNumberDescription,
    ) -> None:
        super().__init__(entry, coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        """Require current state, limits, and a command provider."""
        return (
            super().available
            and self._fresh(DEVICE_STATE_FRESHNESS)
            and self.coordinator.command_available
            and (
                self.entity_description.limit_path is None
                or self._dynamic_limit() is not None
            )
            and self.native_value is not None
        )

    def _dynamic_limit(self) -> float | None:
        if self.entity_description.limit_path is None:
            return None
        return bounded_number(
            path_value(self.coordinator.data, self.entity_description.limit_path),
            minimum=self.native_min_value,
            maximum=self.entity_description.native_max_value,
        )

    @property
    def native_max_value(self) -> float:
        dynamic_limit = self._dynamic_limit()
        if dynamic_limit is not None:
            return dynamic_limit
        maximum = self.entity_description.native_max_value
        assert maximum is not None
        return maximum

    @property
    def native_value(self) -> float | None:
        return bounded_number(
            path_value(self.coordinator.data, self.entity_description.path),
            minimum=self.entity_description.native_min_value,
            maximum=self.native_max_value,
        )

    async def async_set_native_value(self, value: float) -> None:
        """Set the numeric value."""
        await self.coordinator.async_send_command(
            self.entity_description.command,
            int(value),
        )


CradlewiseBridgeNumber = CradlewiseNumber
