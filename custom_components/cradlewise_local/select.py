"""Select controls for the Cradlewise local bridge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CRADLE_ID, DOMAIN
from .status_helpers import path_value

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


@dataclass(frozen=True, kw_only=True)
class CradlewiseSelectDescription(SelectEntityDescription):
    """Description for a writable bridge select."""

    path: tuple[str, ...]
    command: str
    values: dict[str, Any]


SELECTS: tuple[CradlewiseSelectDescription, ...] = (
    CradlewiseSelectDescription(
        key="bounce_mode",
        name="Bounce Mode",
        path=("device_state", "bounce_mode"),
        command="bounce_mode",
        options=MODE_OPTIONS,
        values=MODE_VALUES,
    ),
    CradlewiseSelectDescription(
        key="music_mode",
        name="Music Mode",
        path=("device_state", "music_mode"),
        command="music_mode",
        options=MODE_OPTIONS,
        values=MODE_VALUES,
    ),
    CradlewiseSelectDescription(
        key="volume_profile",
        name="Volume Profile",
        path=("device_state", "volume_profile"),
        command="volume_profile",
        options=PROFILE_OPTIONS,
        values={profile: profile for profile in PROFILE_OPTIONS},
    ),
    CradlewiseSelectDescription(
        key="light_indicator_mode",
        name="Indicator Brightness Mode",
        path=("device_state", "light_indicator_brightness_mode"),
        command="light_indicator_mode",
        options=MODE_OPTIONS,
        values=MODE_VALUES,
    ),
    CradlewiseSelectDescription(
        key="cry_sensitivity",
        name="Cry Sensitivity",
        path=("device_state", "control_cry_sensitivity"),
        command="cry_sensitivity",
        options=CRY_SENSITIVITY_OPTIONS,
        values=CRY_SENSITIVITY_VALUES,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cradlewise writable selects."""
    coordinator = hass.data[DOMAIN][entry.entry_id].get("coordinator")
    if coordinator is None:
        return

    async_add_entities(
        CradlewiseBridgeSelect(entry, coordinator, description)
        for description in SELECTS
    )


class CradlewiseBridgeSelect(CoordinatorEntity, SelectEntity):
    """Select entity backed by the bridge command API."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator,
        description: CradlewiseSelectDescription,
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
