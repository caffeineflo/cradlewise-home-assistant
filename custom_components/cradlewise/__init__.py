"""Home Assistant integration for Cradlewise cribs."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TypeAlias

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from .const import CONF_STREAM_URL
from .coordinator import CradlewiseCoordinator

_LOGGER = logging.getLogger(__name__)


async def _async_reload_entry(
    hass: HomeAssistant,
    entry: CradlewiseConfigEntry,
) -> None:
    """Reload after connection or media options change."""
    await hass.config_entries.async_reload(entry.entry_id)


PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CAMERA,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


@dataclass
class CradlewiseRuntimeData:
    """Objects owned by one Cradlewise config entry."""

    coordinator: CradlewiseCoordinator


CradlewiseConfigEntry: TypeAlias = ConfigEntry[CradlewiseRuntimeData]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CradlewiseConfigEntry,
) -> bool:
    """Set up Cradlewise from a config entry."""
    config = {**entry.data, **entry.options}
    if config.get(CONF_STREAM_URL):
        if not await async_setup_component(hass, "ffmpeg", {}):
            return False
        if not await async_setup_component(hass, "stream", {}):
            return False
    coordinator = CradlewiseCoordinator(hass, entry)
    try:
        await coordinator.async_start()
        await coordinator.async_config_entry_first_refresh()
    except BaseException:
        await coordinator.async_stop()
        raise
    entry.runtime_data = CradlewiseRuntimeData(coordinator=coordinator)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: CradlewiseConfigEntry,
) -> bool:
    """Unload a Cradlewise config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.coordinator.async_stop()
    return unloaded


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Reject entries from a newer integration version."""
    if entry.version > 1:
        _LOGGER.error(
            "Cannot migrate Cradlewise config entry version %s",
            entry.version,
        )
        return False
    return True
