"""Sensors for the Cradlewise local bridge."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CradlewiseConfigEntry
from .coordinator import CradlewiseStatusCoordinator
from .entity import (
    CRADLE_STATE_FRESHNESS,
    DEVICE_STATE_FRESHNESS,
    CradlewiseCoordinatorEntity,
)
from .status_helpers import bounded_number, nonnegative_int, path_value, positive_int


def _identity(value: Any) -> Any:
    return value


def _nonempty_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _timestamp(value: Any) -> datetime | None:
    parsed = bounded_number(value, minimum=0)
    if parsed is None:
        return None
    return datetime.fromtimestamp(parsed, tz=UTC)


def _temperature(value: Any) -> float | None:
    return bounded_number(value, minimum=-50, maximum=80)


def _signal_strength(value: Any) -> int | None:
    parsed = bounded_number(value, minimum=-200, maximum=0)
    if parsed is None or not parsed.is_integer():
        return None
    return int(parsed)


def _breath_state(value: Any) -> str | None:
    parsed = nonnegative_int(value)
    return {
        0: "idle",
        1: "measuring",
        2: "valid",
        3: "invalid",
        4: "not_measuring",
    }.get(parsed)


@dataclass(frozen=True, kw_only=True)
class CradlewiseSensorDescription(SensorEntityDescription):
    """Description for a bridge status sensor."""

    path: tuple[str, ...]
    value_fn: Callable[[Any], Any] = _identity
    freshness_paths: tuple[tuple[str, ...], ...] = DEVICE_STATE_FRESHNESS


def _diagnostic(
    *,
    key: str,
    path: tuple[str, ...],
    value_fn: Callable[[Any], Any] = _identity,
    freshness_paths: tuple[tuple[str, ...], ...] = DEVICE_STATE_FRESHNESS,
    **kwargs: Any,
) -> CradlewiseSensorDescription:
    return CradlewiseSensorDescription(
        key=key,
        translation_key=key,
        path=path,
        value_fn=value_fn,
        freshness_paths=freshness_paths,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        **kwargs,
    )


SENSORS: tuple[CradlewiseSensorDescription, ...] = (
    _diagnostic(
        key="webrtc_connection_state",
        path=("webrtc", "connection_state"),
        value_fn=_nonempty_string,
        freshness_paths=(),
    ),
    _diagnostic(
        key="ice_connection_state",
        path=("webrtc", "ice_connection_state"),
        value_fn=_nonempty_string,
        freshness_paths=(),
    ),
    _diagnostic(
        key="wifi_strength",
        path=("cradle_state", "wifi_strength"),
        value_fn=_signal_strength,
        freshness_paths=CRADLE_STATE_FRESHNESS,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    _diagnostic(
        key="wifi_ssid",
        path=("cradle_state", "wifi_ssid"),
        value_fn=_nonempty_string,
        freshness_paths=CRADLE_STATE_FRESHNESS,
    ),
    _diagnostic(
        key="device_state_source",
        path=("device_state", "source"),
        value_fn=_nonempty_string,
        freshness_paths=(),
    ),
    _diagnostic(
        key="device_state_updated_at",
        path=("device_state", "updated_at"),
        value_fn=_timestamp,
        freshness_paths=(),
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    CradlewiseSensorDescription(
        key="sleep_state",
        translation_key="sleep_state",
        path=("device_state", "sleep_state"),
        value_fn=_nonempty_string,
    ),
    CradlewiseSensorDescription(
        key="sleep_phase",
        translation_key="sleep_phase",
        path=("device_state", "sleep_phase"),
        value_fn=_nonempty_string,
    ),
    _diagnostic(
        key="sleep_phase_raw",
        path=("device_state", "sleep_phase_raw"),
        value_fn=nonnegative_int,
    ),
    _diagnostic(
        key="sleep_state_raw",
        path=("device_state", "sleep_state_raw"),
        value_fn=nonnegative_int,
    ),
    _diagnostic(
        key="sleep_state_internal",
        path=("device_state", "sleep_state_internal"),
        value_fn=nonnegative_int,
    ),
    _diagnostic(
        key="sleep_phase_event_start_time",
        path=("device_state", "sleep_phase_event_start_time"),
        value_fn=_nonempty_string,
    ),
    _diagnostic(
        key="sleep_phase_duration_start_time",
        path=("device_state", "sleep_phase_duration_start_time"),
        value_fn=_nonempty_string,
    ),
    _diagnostic(
        key="sleep_phase_present_toggle_time",
        path=("device_state", "sleep_phase_present_toggle_time"),
        value_fn=_nonempty_string,
    ),
    _diagnostic(
        key="cradle_mode",
        path=("device_state", "cradle_mode"),
        value_fn=_nonempty_string,
    ),
    _diagnostic(
        key="bounce_duration_limit",
        path=("device_state", "bounce_duration_limit"),
        value_fn=nonnegative_int,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
    ),
    CradlewiseSensorDescription(
        key="bounce_time_remaining",
        translation_key="bounce_time_remaining",
        path=("device_state", "bounce_time_remaining"),
        value_fn=nonnegative_int,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
    ),
    _diagnostic(
        key="bounce_tilt_state",
        path=("device_state", "bounce_tilt_state"),
        value_fn=nonnegative_int,
    ),
    CradlewiseSensorDescription(
        key="music_mood",
        translation_key="music_mood",
        path=("device_state", "music_mood"),
        value_fn=_nonempty_string,
    ),
    _diagnostic(
        key="sound_ambience",
        path=("device_state", "sound_ambience"),
        value_fn=_nonempty_string,
    ),
    _diagnostic(
        key="sound_color",
        path=("device_state", "sound_color"),
        value_fn=_nonempty_string,
    ),
    _diagnostic(
        key="sound_heartbeat_volume",
        path=("device_state", "sound_heartbeat_volume"),
        value_fn=nonnegative_int,
    ),
    _diagnostic(
        key="sound_breath_volume",
        path=("device_state", "sound_breath_volume"),
        value_fn=nonnegative_int,
    ),
    _diagnostic(
        key="lullabies_current_song_id",
        path=("device_state", "lullabies_current_song_id"),
        value_fn=_nonempty_string,
    ),
    _diagnostic(
        key="lullabies_desired_playlist_id",
        path=("device_state", "lullabies_desired_playlist_id"),
        value_fn=_nonempty_string,
    ),
    _diagnostic(
        key="lullabies_desired_song_id",
        path=("device_state", "lullabies_desired_song_id"),
        value_fn=_nonempty_string,
    ),
    _diagnostic(
        key="lullabies_elapsed_time",
        path=("device_state", "lullabies_elapsed_time"),
        value_fn=nonnegative_int,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
    ),
    _diagnostic(
        key="lullabies_loop",
        path=("device_state", "lullabies_loop"),
        value_fn=_nonempty_string,
    ),
    _diagnostic(
        key="lullabies_timer_duration",
        path=("device_state", "lullabies_timer_duration"),
        value_fn=nonnegative_int,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
    ),
    CradlewiseSensorDescription(
        key="music_time_remaining",
        translation_key="music_time_remaining",
        path=("device_state", "music_time_remaining"),
        value_fn=nonnegative_int,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        device_class=SensorDeviceClass.DURATION,
    ),
    CradlewiseSensorDescription(
        key="ambient_temperature",
        translation_key="ambient_temperature",
        path=("device_state", "ambient_temperature"),
        value_fn=_temperature,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    _diagnostic(
        key="operation_state",
        path=("device_state", "operation_state"),
        value_fn=nonnegative_int,
    ),
    _diagnostic(
        key="deploy_state",
        path=("device_state", "deploy_state"),
        value_fn=nonnegative_int,
    ),
    _diagnostic(
        key="calibrate_cradle",
        path=("device_state", "calibrate_cradle"),
        value_fn=_nonempty_string,
    ),
    _diagnostic(
        key="calibration_type",
        path=("device_state", "calibration_type"),
        value_fn=_nonempty_string,
    ),
    _diagnostic(
        key="calibration_stage",
        path=("device_state", "calibration_stage"),
        value_fn=_nonempty_string,
    ),
    _diagnostic(
        key="calibration_status",
        path=("device_state", "calibration_status"),
        value_fn=_nonempty_string,
    ),
    _diagnostic(
        key="user_action_for_obstruction",
        path=("device_state", "user_action_for_obstruction"),
        value_fn=_nonempty_string,
    ),
    _diagnostic(
        key="wifi_score",
        path=("device_state", "wifi_score"),
        value_fn=nonnegative_int,
    ),
    _diagnostic(
        key="rootfs_version",
        path=("device_state", "rootfs_version"),
        value_fn=_nonempty_string,
    ),
    _diagnostic(
        key="shadow_version",
        path=("device_state", "shadow_version"),
        value_fn=nonnegative_int,
    ),
    _diagnostic(
        key="cradle_timezone",
        path=("device_state", "cradle_timezone"),
        value_fn=_nonempty_string,
    ),
    CradlewiseSensorDescription(
        key="breath_rate",
        translation_key="breath_rate",
        path=("device_state", "breath_rate"),
        value_fn=positive_int,
        native_unit_of_measurement="breaths/min",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    _diagnostic(
        key="breath_state",
        path=("device_state", "breath_state"),
        value_fn=_breath_state,
    ),
    _diagnostic(
        key="breath_reason",
        path=("device_state", "breath_reason"),
        value_fn=nonnegative_int,
    ),
    _diagnostic(
        key="auto_mode_lock_end_time",
        path=("device_state", "auto_mode_lock_end_time"),
        value_fn=_nonempty_string,
    ),
    _diagnostic(
        key="start_recipe_lock_end_time",
        path=("device_state", "start_recipe_lock_end_time"),
        value_fn=_nonempty_string,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CradlewiseConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cradlewise status sensors."""
    coordinator = entry.runtime_data.coordinator
    if coordinator is None:
        return
    async_add_entities(
        CradlewiseStatusSensor(entry, coordinator, description)
        for description in SENSORS
    )


class CradlewiseStatusSensor(CradlewiseCoordinatorEntity, SensorEntity):
    """Sensor backed by the bridge status API."""

    entity_description: CradlewiseSensorDescription

    def __init__(
        self,
        entry: CradlewiseConfigEntry,
        coordinator: CradlewiseStatusCoordinator,
        description: CradlewiseSensorDescription,
    ) -> None:
        super().__init__(entry, coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        """Return availability with freshness for device-backed state."""
        return (
            super().available
            and (
                not self.entity_description.freshness_paths
                or self._fresh(self.entity_description.freshness_paths)
            )
            and self.native_value is not None
        )

    @property
    def native_value(self) -> Any:
        value = path_value(self.coordinator.data, self.entity_description.path)
        return self.entity_description.value_fn(value)
