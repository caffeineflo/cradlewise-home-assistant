"""Select controls for the Cradlewise local bridge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CradlewiseConfigEntry
from .coordinator import CradlewiseStatusCoordinator
from .entity import DEVICE_STATE_FRESHNESS, CradlewiseCoordinatorEntity
from .status_helpers import path_value, strict_bool

MODE_OPTIONS = ("Auto", "Manual")
MODE_VALUES = {"Auto": 0, "Manual": 1}
PROFILE_OPTIONS = ("gentle", "normal", "max")
CRY_SENSITIVITY_OPTIONS = ("Minimum", "Low", "Moderate", "High", "Maximum")
CRY_SENSITIVITY_VALUES = {
    "Minimum": 0,
    "Low": 1,
    "Moderate": 2,
    "High": 4,
    "Maximum": 6,
}
MUSIC_DURATION_VALUES = {
    "Off": -1,
    "60 minutes": 60,
    "180 minutes": 180,
}
RESPONSIVITY_VALUES = {"2": 2, "4": 4, "6": 6, "8": 8, "10": 10}
RECIPE_LEVEL_VALUES = {
    "Off": -1,
    "Gentle": 0,
    "Level 1": 1,
    "Level 2": 2,
    "Level 3": 3,
    "Level 4": 4,
}
RECIPE_LOCK_DURATION_VALUES = {
    "10 minutes": 10,
    "20 minutes": 20,
    "30 minutes": 30,
}


@dataclass(frozen=True, kw_only=True)
class CradlewiseSelectDescription(SelectEntityDescription):
    """Description for a writable bridge select."""

    path: tuple[str, ...]
    command: str
    values: dict[str, Any]


def _config_select(**kwargs: Any) -> CradlewiseSelectDescription:
    return CradlewiseSelectDescription(
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        **kwargs,
    )


SELECTS: tuple[CradlewiseSelectDescription, ...] = (
    CradlewiseSelectDescription(
        key="bounce_mode",
        translation_key="bounce_mode",
        path=("device_state", "bounce_mode"),
        command="bounce_mode",
        options=MODE_OPTIONS,
        values=MODE_VALUES,
    ),
    CradlewiseSelectDescription(
        key="music_mode",
        translation_key="music_mode",
        path=("device_state", "music_mode"),
        command="music_mode",
        options=MODE_OPTIONS,
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
    _config_select(
        key="volume_profile",
        translation_key="volume_profile",
        path=("device_state", "volume_profile"),
        command="volume_profile",
        options=PROFILE_OPTIONS,
        values={profile: profile for profile in PROFILE_OPTIONS},
    ),
    _config_select(
        key="light_indicator_mode",
        translation_key="light_indicator_mode",
        path=("device_state", "light_indicator_brightness_mode"),
        command="light_indicator_mode",
        options=MODE_OPTIONS,
        values=MODE_VALUES,
    ),
    _config_select(
        key="cry_sensitivity",
        translation_key="cry_sensitivity",
        path=("device_state", "control_cry_sensitivity"),
        command="cry_sensitivity",
        options=CRY_SENSITIVITY_OPTIONS,
        values=CRY_SENSITIVITY_VALUES,
    ),
    _config_select(
        key="responsivity_setting",
        translation_key="responsivity_setting",
        path=("device_state", "responsivity_setting"),
        command="responsivity_setting",
        options=tuple(RESPONSIVITY_VALUES),
        values=RESPONSIVITY_VALUES,
    ),
    _config_select(
        key="start_recipe_music_level",
        translation_key="start_recipe_music_level",
        path=("device_state", "start_recipe_music_level"),
        command="start_recipe_music_level",
        options=tuple(RECIPE_LEVEL_VALUES),
        values=RECIPE_LEVEL_VALUES,
    ),
    _config_select(
        key="start_recipe_bounce_level",
        translation_key="start_recipe_bounce_level",
        path=("device_state", "start_recipe_bounce_level"),
        command="start_recipe_bounce_level",
        options=tuple(RECIPE_LEVEL_VALUES),
        values=RECIPE_LEVEL_VALUES,
    ),
    _config_select(
        key="start_recipe_lock_duration",
        translation_key="start_recipe_lock_duration",
        path=("device_state", "start_recipe_lock_duration"),
        command="start_recipe_lock_duration",
        options=tuple(RECIPE_LOCK_DURATION_VALUES),
        values=RECIPE_LOCK_DURATION_VALUES,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CradlewiseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cradlewise writable selects."""
    coordinator = entry.runtime_data.coordinator
    if coordinator is None:
        return
    async_add_entities(
        CradlewiseBridgeSelect(entry, coordinator, description)
        for description in SELECTS
    )


class CradlewiseBridgeSelect(CradlewiseCoordinatorEntity, SelectEntity):
    """Select entity backed by the bridge command API."""

    entity_description: CradlewiseSelectDescription

    def __init__(
        self,
        entry: CradlewiseConfigEntry,
        coordinator: CradlewiseStatusCoordinator,
        description: CradlewiseSelectDescription,
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
            if normalized == str(option_value).lower():
                return option
            if normalized == option.lower():
                return option
        return None

    async def async_select_option(self, option: str) -> None:
        """Select a new option."""
        await self.coordinator.async_send_command(
            self.entity_description.command,
            self.entity_description.values[option],
        )
