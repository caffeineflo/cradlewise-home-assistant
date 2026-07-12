"""Switch controls for the Cradlewise local bridge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CradlewiseConfigEntry
from .coordinator import CradlewiseStatusCoordinator
from .entity import DEVICE_STATE_FRESHNESS, CradlewiseCoordinatorEntity
from .status_helpers import path_value, strict_bool


@dataclass(frozen=True, kw_only=True)
class CradlewiseSwitchDescription(SwitchEntityDescription):
    """Description for a writable bridge switch."""

    path: tuple[str, ...]
    command: str


def _config_switch(**kwargs: Any) -> CradlewiseSwitchDescription:
    return CradlewiseSwitchDescription(
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        **kwargs,
    )


SWITCHES: tuple[CradlewiseSwitchDescription, ...] = (
    CradlewiseSwitchDescription(
        key="actuator_on",
        translation_key="actuator_on",
        path=("device_state", "bouncing"),
        command="actuator_on",
    ),
    _config_switch(
        key="disable_bounce",
        translation_key="disable_bounce",
        path=("device_state", "bounce_disabled"),
        command="disable_bounce",
    ),
    _config_switch(
        key="super_gentle_bounce",
        translation_key="super_gentle_bounce",
        path=("device_state", "bounce_super_gentle"),
        command="super_gentle_bounce",
    ),
    _config_switch(
        key="always_on_bounce",
        translation_key="always_on_bounce",
        path=("device_state", "bounce_always_on"),
        command="always_on_bounce",
    ),
    _config_switch(
        key="tap_detection_enabled",
        translation_key="tap_detection_enabled",
        path=("device_state", "bounce_tap_detection_enabled"),
        command="tap_detection_enabled",
    ),
    _config_switch(
        key="push_gesture_enabled",
        translation_key="push_gesture_enabled",
        path=("device_state", "bounce_push_gesture_enabled"),
        command="push_gesture_enabled",
    ),
    CradlewiseSwitchDescription(
        key="music_playing",
        translation_key="music_playing",
        path=("device_state", "music_playing"),
        command="music_playing",
    ),
    _config_switch(
        key="keep_music_on_during_sleep",
        translation_key="keep_music_on_during_sleep",
        path=("device_state", "keep_music_on_during_sleep"),
        command="keep_music_on_during_sleep",
    ),
    _config_switch(
        key="keep_bounce_on_during_sleep",
        translation_key="keep_bounce_on_during_sleep",
        path=("device_state", "keep_bounce_on_during_sleep"),
        command="keep_bounce_on_during_sleep",
    ),
    _config_switch(
        key="auto_mode_lock_on",
        translation_key="auto_mode_lock_on",
        path=("device_state", "auto_mode_lock_on"),
        command="auto_mode_lock_on",
    ),
    _config_switch(
        key="start_recipe_enabled",
        translation_key="start_recipe_enabled",
        path=("device_state", "start_recipe_enabled"),
        command="start_recipe_enabled",
    ),
    CradlewiseSwitchDescription(
        key="adaptive_soothing_enabled",
        translation_key="adaptive_soothing_enabled",
        path=("device_state", "control_adaptive_soothing_enabled"),
        command="adaptive_soothing_enabled",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CradlewiseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cradlewise writable switches."""
    coordinator = entry.runtime_data.coordinator
    if coordinator is None:
        return
    async_add_entities(
        CradlewiseBridgeSwitch(entry, coordinator, description)
        for description in SWITCHES
    )


class CradlewiseBridgeSwitch(CradlewiseCoordinatorEntity, SwitchEntity):
    """Switch backed by the bridge command API."""

    entity_description: CradlewiseSwitchDescription

    def __init__(
        self,
        entry: CradlewiseConfigEntry,
        coordinator: CradlewiseStatusCoordinator,
        description: CradlewiseSwitchDescription,
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
            self.entity_description.command, False
        )
