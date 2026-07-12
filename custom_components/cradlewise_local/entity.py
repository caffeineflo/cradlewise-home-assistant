"""Shared entity support for the Cradlewise integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .config_helpers import bridge_base_url
from .const import (
    CONF_BRIDGE_STATUS_URL,
    CONF_CRADLE_ID,
    DEVICE_STATE_MAX_AGE_SECONDS,
    DOMAIN,
)
from .coordinator import CradlewiseStatusCoordinator
from .status_helpers import (
    device_state_is_available,
    path_value,
    timestamp_is_fresh,
)

if TYPE_CHECKING:
    from . import CradlewiseConfigEntry


DEVICE_STATE_FRESHNESS = (("device_state", "updated_at"),)
CRADLE_STATE_FRESHNESS = (
    ("cradle_state", "updated_at"),
    ("device_state", "updated_at"),
)


def device_info(
    entry: ConfigEntry[Any],
    coordinator: CradlewiseStatusCoordinator | None = None,
) -> DeviceInfo:
    """Build stable device registry information from config and current state."""
    data = coordinator.data if coordinator is not None else None
    software_version = path_value(data, ("device_state", "software_version"))
    status_url = entry.data.get(CONF_BRIDGE_STATUS_URL)
    return DeviceInfo(
        configuration_url=bridge_base_url(status_url) if status_url else None,
        identifiers={(DOMAIN, entry.data[CONF_CRADLE_ID])},
        manufacturer="Cradlewise",
        model="Smart Crib",
        name=entry.data.get(CONF_NAME, entry.title),
        serial_number=entry.data[CONF_CRADLE_ID],
        sw_version=str(software_version) if software_version else None,
    )


class CradlewiseCoordinatorEntity(CoordinatorEntity[CradlewiseStatusCoordinator]):
    """Base entity with stable identity and shared device information."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: CradlewiseConfigEntry,
        coordinator: CradlewiseStatusCoordinator,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.data[CONF_CRADLE_ID]}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information that can include current firmware."""
        return device_info(self._entry, self.coordinator)

    def _fresh(self, paths: tuple[tuple[str, ...], ...]) -> bool:
        """Return whether at least one source timestamp is current."""
        if paths == DEVICE_STATE_FRESHNESS:
            return device_state_is_available(
                self.coordinator.data,
                DEVICE_STATE_MAX_AGE_SECONDS,
            )
        return timestamp_is_fresh(
            self.coordinator.data,
            paths,
            DEVICE_STATE_MAX_AGE_SECONDS,
        )
