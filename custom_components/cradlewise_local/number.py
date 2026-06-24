"""Number controls for the Cradlewise local bridge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CRADLE_ID, DOMAIN
from .status_helpers import path_value


@dataclass(frozen=True, kw_only=True)
class CradlewiseNumberDescription(NumberEntityDescription):
    """Description for a writable bridge number."""

    path: tuple[str, ...]
    command: str


NUMBERS: tuple[CradlewiseNumberDescription, ...] = (
    CradlewiseNumberDescription(
        key="bounce_level",
        name="Bounce Level",
        path=("device_state", "bounce_level"),
        command="bounce_level",
        native_min_value=0,
        native_max_value=5,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
    CradlewiseNumberDescription(
        key="music_level",
        name="Sound Level",
        path=("device_state", "music_level"),
        command="music_level",
        native_min_value=0,
        native_max_value=5,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
    CradlewiseNumberDescription(
        key="bounce_amplitude",
        name="Bounce Amplitude",
        path=("device_state", "bounce_amplitude"),
        command="bounce_amplitude",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
    CradlewiseNumberDescription(
        key="bounce_duration",
        name="Bounce Duration",
        path=("device_state", "bounce_duration"),
        command="bounce_duration",
        native_min_value=0,
        native_max_value=1440,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
    CradlewiseNumberDescription(
        key="always_on_bounce_intensity",
        name="Always On Bounce Intensity",
        path=("device_state", "bounce_always_on_intensity"),
        command="always_on_bounce_intensity",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
    CradlewiseNumberDescription(
        key="bounce_setting",
        name="Bounce Setting",
        path=("device_state", "bounce_setting"),
        command="bounce_setting",
        native_min_value=0,
        native_max_value=10,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
    CradlewiseNumberDescription(
        key="responsivity_setting",
        name="Responsivity Setting",
        path=("device_state", "responsivity_setting"),
        command="responsivity_setting",
        native_min_value=0,
        native_max_value=10,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
    CradlewiseNumberDescription(
        key="music_volume",
        name="Music Volume",
        path=("device_state", "music_volume"),
        command="music_volume",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
    CradlewiseNumberDescription(
        key="keep_music_on_during_sleep_level",
        name="Keep Music On During Sleep Level",
        path=("device_state", "keep_music_on_during_sleep_level"),
        command="keep_music_on_during_sleep_level",
        native_min_value=0,
        native_max_value=5,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
    CradlewiseNumberDescription(
        key="keep_bounce_on_during_sleep_level",
        name="Keep Bounce On During Sleep Level",
        path=("device_state", "keep_bounce_on_during_sleep_level"),
        command="keep_bounce_on_during_sleep_level",
        native_min_value=0,
        native_max_value=5,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
    CradlewiseNumberDescription(
        key="music_duration",
        name="Music Duration",
        path=("device_state", "music_duration"),
        command="music_duration",
        native_min_value=0,
        native_max_value=1440,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
    CradlewiseNumberDescription(
        key="auto_mode_lock_duration",
        name="Auto Mode Lock Duration",
        path=("device_state", "auto_mode_lock_duration"),
        command="auto_mode_lock_duration",
        native_min_value=0,
        native_max_value=1440,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
    CradlewiseNumberDescription(
        key="max_bounce_limit",
        name="Max Bounce Limit",
        path=("device_state", "max_bounce_limit"),
        command="max_bounce_limit",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
    CradlewiseNumberDescription(
        key="max_volume_limit",
        name="Max Volume Limit",
        path=("device_state", "max_volume_limit"),
        command="max_volume_limit",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
    CradlewiseNumberDescription(
        key="start_recipe_music_level",
        name="Start Recipe Music Level",
        path=("device_state", "start_recipe_music_level"),
        command="start_recipe_music_level",
        native_min_value=0,
        native_max_value=5,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
    CradlewiseNumberDescription(
        key="start_recipe_bounce_level",
        name="Start Recipe Bounce Level",
        path=("device_state", "start_recipe_bounce_level"),
        command="start_recipe_bounce_level",
        native_min_value=0,
        native_max_value=5,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
    CradlewiseNumberDescription(
        key="start_recipe_lock_duration",
        name="Start Recipe Lock Duration",
        path=("device_state", "start_recipe_lock_duration"),
        command="start_recipe_lock_duration",
        native_min_value=0,
        native_max_value=1440,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
    CradlewiseNumberDescription(
        key="light_indicator_brightness",
        name="Indicator Brightness",
        path=("device_state", "light_intensity"),
        command="light_indicator_brightness",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        mode=NumberMode.SLIDER,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cradlewise writable numbers."""
    coordinator = hass.data[DOMAIN][entry.entry_id].get("coordinator")
    if coordinator is None:
        return

    async_add_entities(
        CradlewiseBridgeNumber(entry, coordinator, description)
        for description in NUMBERS
    )


class CradlewiseBridgeNumber(CoordinatorEntity, NumberEntity):
    """Number entity backed by the bridge command API."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator,
        description: CradlewiseNumberDescription,
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
    def native_value(self) -> int | None:
        value = path_value(self.coordinator.data, self.entity_description.path)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        """Set the numeric value."""
        await self.coordinator.async_send_command(
            self.entity_description.command,
            int(value),
        )
