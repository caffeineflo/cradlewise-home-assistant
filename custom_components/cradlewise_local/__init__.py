"""Home Assistant integration for Cradlewise local bridge streams."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TypeAlias

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import CONF_BRIDGE_STATUS_URL, CONF_CRADLE_ID
from .coordinator import CradlewiseStatusCoordinator
from .entity_policy import ENTITY_POLICIES

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CAMERA,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]


@dataclass
class CradlewiseRuntimeData:
    """Objects owned by one Cradlewise config entry."""

    coordinator: CradlewiseStatusCoordinator | None


CradlewiseConfigEntry: TypeAlias = ConfigEntry[CradlewiseRuntimeData]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CradlewiseConfigEntry,
) -> bool:
    """Set up Cradlewise from a config entry."""
    coordinator: CradlewiseStatusCoordinator | None = None
    if entry.data.get(CONF_BRIDGE_STATUS_URL):
        coordinator = CradlewiseStatusCoordinator(hass, entry)
        await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = CradlewiseRuntimeData(coordinator=coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: CradlewiseConfigEntry,
) -> bool:
    """Unload a Cradlewise config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Apply the version 2 entity policy without relying on mutable entity IDs."""
    if entry.version > 2:
        _LOGGER.error(
            "Cannot migrate Cradlewise config entry version %s",
            entry.version,
        )
        return False

    if entry.version == 2 and entry.minor_version >= 1:
        return True

    if entry.version == 2:
        hass.config_entries.async_update_entry(entry, minor_version=1)
        return True

    registry = er.async_get(hass)
    prefix = f"{entry.data[CONF_CRADLE_ID]}_"
    removed = 0
    disabled = 0
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if not registry_entry.unique_id.startswith(prefix):
            continue
        domain = registry_entry.entity_id.partition(".")[0]
        policy = ENTITY_POLICIES.get(domain)
        if policy is None:
            continue
        key = registry_entry.unique_id.removeprefix(prefix)
        if key in policy.removed:
            registry.async_remove(registry_entry.entity_id)
            removed += 1
        elif key in policy.disabled and registry_entry.disabled_by is None:
            registry.async_update_entity(
                registry_entry.entity_id,
                disabled_by=er.RegistryEntryDisabler.INTEGRATION,
            )
            disabled += 1

    hass.config_entries.async_update_entry(entry, version=2, minor_version=1)
    _LOGGER.info(
        "Migrated Cradlewise entity registry: removed %d and disabled %d entities",
        removed,
        disabled,
    )
    return True
