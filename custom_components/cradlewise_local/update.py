"""Firmware update status for the Cradlewise local bridge."""

from __future__ import annotations

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CradlewiseConfigEntry
from .coordinator import CradlewiseStatusCoordinator
from .entity import DEVICE_STATE_FRESHNESS, CradlewiseCoordinatorEntity
from .status_helpers import bounded_number, path_value, strict_bool

UPDATE_DESCRIPTION = UpdateEntityDescription(
    key="firmware",
    translation_key="firmware",
    device_class=UpdateDeviceClass.FIRMWARE,
    entity_category=EntityCategory.DIAGNOSTIC,
    entity_registry_enabled_default=False,
)


def _version(value: object) -> str | None:
    """Return a meaningful firmware version."""
    if value is None:
        return None
    version = str(value).strip()
    if not version or version == "0.0":
        return None
    return version


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CradlewiseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cradlewise firmware status."""
    coordinator = entry.runtime_data.coordinator
    if coordinator is None:
        return
    async_add_entities([CradlewiseFirmwareUpdate(entry, coordinator)])


class CradlewiseFirmwareUpdate(CradlewiseCoordinatorEntity, UpdateEntity):
    """Read-only firmware status derived from the device shadow."""

    entity_description = UPDATE_DESCRIPTION

    def __init__(
        self,
        entry: CradlewiseConfigEntry,
        coordinator: CradlewiseStatusCoordinator,
    ) -> None:
        super().__init__(entry, coordinator, UPDATE_DESCRIPTION.key)

    @property
    def available(self) -> bool:
        """Require current device state with a usable installed version."""
        return (
            super().available
            and self._fresh(DEVICE_STATE_FRESHNESS)
            and self.installed_version is not None
        )

    @property
    def installed_version(self) -> str | None:
        """Return the installed firmware version."""
        return _version(
            path_value(self.coordinator.data, ("device_state", "software_version"))
        )

    @property
    def latest_version(self) -> str | None:
        """Return the offered version only when the shadow marks it available."""
        if (
            strict_bool(
                path_value(
                    self.coordinator.data,
                    ("device_state", "update_available"),
                )
            )
            is True
        ):
            offered = _version(
                path_value(
                    self.coordinator.data,
                    ("device_state", "update_version"),
                )
            )
            if offered is not None:
                return offered
        return self.installed_version

    @property
    def in_progress(self) -> bool:
        """Return whether the device reports an active update."""
        value = path_value(
            self.coordinator.data,
            ("device_state", "update_status"),
        )
        return isinstance(value, str) and value.strip().upper() not in {
            "",
            "COMPLETE",
            "COMPLETED",
            "ERROR",
            "FAILED",
            "IDLE",
            "NONE",
            "SUCCEEDED",
            "SUCCESS",
        }

    @property
    def update_percentage(self) -> int | None:
        """Return a bounded update progress percentage."""
        value = bounded_number(
            path_value(
                self.coordinator.data,
                ("device_state", "update_progress"),
            ),
            minimum=0,
            maximum=100,
        )
        if value is None or not value.is_integer():
            return None
        return int(value)
