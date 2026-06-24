"""Switch controls for the Cradlewise local bridge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CRADLE_ID, DOMAIN
from .status_helpers import path_value


@dataclass(frozen=True, kw_only=True)
class CradlewiseSwitchDescription(SwitchEntityDescription):
    """Description for a writable bridge switch."""

    path: tuple[str, ...]
    command: str


SWITCHES: tuple[CradlewiseSwitchDescription, ...] = (
    CradlewiseSwitchDescription(
        key="actuator_on",
        name="Bounce",
        path=("device_state", "bouncing"),
        command="actuator_on",
    ),
    CradlewiseSwitchDescription(
        key="disable_bounce",
        name="Disable Bounce",
        path=("device_state", "bounce_disabled"),
        command="disable_bounce",
    ),
    CradlewiseSwitchDescription(
        key="super_gentle_bounce",
        name="Super Gentle Bounce",
        path=("device_state", "bounce_super_gentle"),
        command="super_gentle_bounce",
    ),
    CradlewiseSwitchDescription(
        key="always_on_bounce",
        name="Always On Bounce",
        path=("device_state", "bounce_always_on"),
        command="always_on_bounce",
    ),
    CradlewiseSwitchDescription(
        key="tap_detection_enabled",
        name="Tap Detection",
        path=("device_state", "bounce_tap_detection_enabled"),
        command="tap_detection_enabled",
    ),
    CradlewiseSwitchDescription(
        key="push_gesture_enabled",
        name="Push Gesture",
        path=("device_state", "bounce_push_gesture_enabled"),
        command="push_gesture_enabled",
    ),
    CradlewiseSwitchDescription(
        key="music_playing",
        name="Music",
        path=("device_state", "music_playing"),
        command="music_playing",
    ),
    CradlewiseSwitchDescription(
        key="keep_music_on_during_sleep",
        name="Keep Music On During Sleep",
        path=("device_state", "keep_music_on_during_sleep"),
        command="keep_music_on_during_sleep",
    ),
    CradlewiseSwitchDescription(
        key="keep_bounce_on_during_sleep",
        name="Keep Bounce On During Sleep",
        path=("device_state", "keep_bounce_on_during_sleep"),
        command="keep_bounce_on_during_sleep",
    ),
    CradlewiseSwitchDescription(
        key="auto_mode_lock_on",
        name="Auto Mode Lock",
        path=("device_state", "auto_mode_lock_on"),
        command="auto_mode_lock_on",
    ),
    CradlewiseSwitchDescription(
        key="start_recipe_enabled",
        name="Start Recipe Enabled",
        path=("device_state", "start_recipe_enabled"),
        command="start_recipe_enabled",
    ),
    CradlewiseSwitchDescription(
        key="adaptive_soothing_enabled",
        name="Adaptive Soothing",
        path=("device_state", "control_adaptive_soothing_enabled"),
        command="adaptive_soothing_enabled",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cradlewise writable switches."""
    coordinator = hass.data[DOMAIN][entry.entry_id].get("coordinator")
    if coordinator is None:
        return

    async_add_entities(
        CradlewiseBridgeSwitch(entry, coordinator, description)
        for description in SWITCHES
    )


class CradlewiseBridgeSwitch(CoordinatorEntity, SwitchEntity):
    """Switch backed by the bridge command API."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator,
        description: CradlewiseSwitchDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
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

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self.coordinator.async_send_command(self.entity_description.command, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self.coordinator.async_send_command(self.entity_description.command, False)
