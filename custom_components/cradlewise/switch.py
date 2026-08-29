"""Switch control platform for Cradlewise."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CradlewiseConfigEntry
from .coordinator import CradlewiseCoordinator
from .entity import DEVICE_STATE_FRESHNESS, CradlewiseCoordinatorEntity
from .status_helpers import path_value, strict_bool


@dataclass(frozen=True, kw_only=True)
class CradlewiseSwitchDescription(SwitchEntityDescription):
    """Describe one useful Cradlewise switch control."""

    path: tuple[str, ...]
    command: str


SWITCHES: tuple[CradlewiseSwitchDescription, ...] = (
    CradlewiseSwitchDescription(
        key="actuator_on",
        translation_key="actuator_on",
        path=("device_state", "bouncing"),
        command="actuator_on",
    ),
    CradlewiseSwitchDescription(
        key="music_playing",
        translation_key="music_playing",
        path=("device_state", "music_playing"),
        command="music_playing",
    ),
    CradlewiseSwitchDescription(
        key="adaptive_soothing_enabled",
        translation_key="adaptive_soothing_enabled",
        path=("device_state", "adaptive_soothing_enabled"),
        command="adaptive_soothing_enabled",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CradlewiseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cradlewise switch controls."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        CradlewiseSwitch(entry, coordinator, description) for description in SWITCHES
    )


class CradlewiseSwitch(CradlewiseCoordinatorEntity, SwitchEntity):
    """Switch backed by the selected command provider."""

    entity_description: CradlewiseSwitchDescription

    def __init__(
        self,
        entry: CradlewiseConfigEntry,
        coordinator: CradlewiseCoordinator,
        description: CradlewiseSwitchDescription,
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
            and self.is_on is not None
        )

    @property
    def is_on(self) -> bool | None:
        value: Any = path_value(self.coordinator.data, self.entity_description.path)
        return strict_bool(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self.coordinator.async_send_command(self.entity_description.command, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self.coordinator.async_send_command(
            self.entity_description.command,
            False,
        )


CradlewiseBridgeSwitch = CradlewiseSwitch
