"""Select control platform for Cradlewise."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CradlewiseConfigEntry
from .coordinator import CradlewiseCoordinator
from .entity import DEVICE_STATE_FRESHNESS, CradlewiseCoordinatorEntity
from .status_helpers import path_value

MODE_VALUES = {"Auto": 0, "Manual": 1}
MUSIC_DURATION_VALUES = {
    "Off": -1,
    "60 minutes": 60,
    "180 minutes": 180,
}


@dataclass(frozen=True, kw_only=True)
class CradlewiseSelectDescription(SelectEntityDescription):
    """Describe one useful Cradlewise select control."""

    path: tuple[str, ...]
    command: str
    values: dict[str, Any]


SELECTS: tuple[CradlewiseSelectDescription, ...] = (
    CradlewiseSelectDescription(
        key="bounce_mode",
        translation_key="bounce_mode",
        path=("device_state", "bounce_mode"),
        command="bounce_mode",
        options=tuple(MODE_VALUES),
        values=MODE_VALUES,
    ),
    CradlewiseSelectDescription(
        key="music_mode",
        translation_key="music_mode",
        path=("device_state", "music_mode"),
        command="music_mode",
        options=tuple(MODE_VALUES),
        values=MODE_VALUES,
    ),
    CradlewiseSelectDescription(
        key="music_duration",
        translation_key="music_duration",
        path=("device_state", "music_duration"),
        command="music_duration",
        options=tuple(MUSIC_DURATION_VALUES),
        values=MUSIC_DURATION_VALUES,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CradlewiseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cradlewise select controls."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        CradlewiseSelect(entry, coordinator, description) for description in SELECTS
    )


class CradlewiseSelect(CradlewiseCoordinatorEntity, SelectEntity):
    """Select control backed by the selected command provider."""

    entity_description: CradlewiseSelectDescription

    def __init__(
        self,
        entry: CradlewiseConfigEntry,
        coordinator: CradlewiseCoordinator,
        description: CradlewiseSelectDescription,
    ) -> None:
        super().__init__(entry, coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        """Require current state and a command provider."""
        return (
            super().available
            and self._fresh(DEVICE_STATE_FRESHNESS)
            and self.coordinator.command_available
            and self.current_option is not None
        )

    @property
    def current_option(self) -> str | None:
        value = path_value(self.coordinator.data, self.entity_description.path)
        if value is None:
            return None
        normalized = str(value).lower()
        for option, option_value in self.entity_description.values.items():
            if value == option_value:
                return option
            if normalized in {str(option_value).lower(), option.lower()}:
                return option
        return None

    async def async_select_option(self, option: str) -> None:
        """Select a new option."""
        await self.coordinator.async_send_command(
            self.entity_description.command,
            self.entity_description.values[option],
        )


CradlewiseBridgeSelect = CradlewiseSelect
