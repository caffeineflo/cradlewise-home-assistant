"""Binary sensors for the Cradlewise local bridge."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
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
class CradlewiseBinarySensorDescription(BinarySensorEntityDescription):
    """Description for a bridge binary sensor."""

    path: tuple[str, ...]


BINARY_SENSORS: tuple[CradlewiseBinarySensorDescription, ...] = (
    CradlewiseBinarySensorDescription(
        key="bridge_healthy",
        name="Bridge Healthy",
        path=("bridge", "healthy"),
    ),
    CradlewiseBinarySensorDescription(
        key="mqtt_connected",
        name="MQTT Connected",
        path=("mqtt", "connected"),
    ),
    CradlewiseBinarySensorDescription(
        key="audio_track",
        name="Audio Track",
        path=("media", "audio_track"),
    ),
    CradlewiseBinarySensorDescription(
        key="baby_present",
        name="Baby Present",
        path=("device_state", "baby_present"),
        device_class=BinarySensorDeviceClass.OCCUPANCY,
    ),
    CradlewiseBinarySensorDescription(
        key="baby_present_previous",
        name="Baby Present Previous",
        path=("device_state", "baby_present_previous"),
        device_class=BinarySensorDeviceClass.OCCUPANCY,
    ),
    CradlewiseBinarySensorDescription(
        key="has_baby_ever_been_placed",
        name="Has Baby Ever Been Placed",
        path=("device_state", "has_baby_ever_been_placed"),
    ),
    CradlewiseBinarySensorDescription(
        key="baby_presence_being_determined",
        name="Baby Presence Being Determined",
        path=("device_state", "baby_presence_being_determined"),
    ),
    CradlewiseBinarySensorDescription(
        key="sleep_state_being_determined",
        name="Sleep State Being Determined",
        path=("device_state", "sleep_state_being_determined"),
    ),
    CradlewiseBinarySensorDescription(
        key="baby_needs_attention",
        name="Baby Needs Attention",
        path=("device_state", "baby_needs_attention"),
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    CradlewiseBinarySensorDescription(
        key="baby_needs_help",
        name="Baby Needs Help",
        path=("device_state", "baby_needs_help"),
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    CradlewiseBinarySensorDescription(
        key="crib_helping",
        name="Crib Helping",
        path=("device_state", "crib_helping"),
    ),
    CradlewiseBinarySensorDescription(
        key="bouncing",
        name="Bouncing",
        path=("device_state", "bouncing"),
    ),
    CradlewiseBinarySensorDescription(
        key="bounce_disabled",
        name="Bounce Disabled",
        path=("device_state", "bounce_disabled"),
    ),
    CradlewiseBinarySensorDescription(
        key="bounce_super_gentle",
        name="Bounce Super Gentle",
        path=("device_state", "bounce_super_gentle"),
    ),
    CradlewiseBinarySensorDescription(
        key="bounce_always_on",
        name="Bounce Always On",
        path=("device_state", "bounce_always_on"),
    ),
    CradlewiseBinarySensorDescription(
        key="bounce_tap_detection_enabled",
        name="Bounce Tap Detection Enabled",
        path=("device_state", "bounce_tap_detection_enabled"),
    ),
    CradlewiseBinarySensorDescription(
        key="bounce_push_gesture_enabled",
        name="Bounce Push Gesture Enabled",
        path=("device_state", "bounce_push_gesture_enabled"),
    ),
    CradlewiseBinarySensorDescription(
        key="bounce_quiescent",
        name="Bounce Quiescent",
        path=("device_state", "bounce_quiescent"),
    ),
    CradlewiseBinarySensorDescription(
        key="music_playing",
        name="Music Playing",
        path=("device_state", "music_playing"),
    ),
    CradlewiseBinarySensorDescription(
        key="sound_spotify_service_enabled",
        name="Sound Spotify Service Enabled",
        path=("device_state", "sound_spotify_service_enabled"),
    ),
    CradlewiseBinarySensorDescription(
        key="lullabies_enabled",
        name="Lullabies Enabled",
        path=("device_state", "lullabies_enabled"),
    ),
    CradlewiseBinarySensorDescription(
        key="lullabies_timer_on",
        name="Lullabies Timer",
        path=("device_state", "lullabies_timer_on"),
    ),
    CradlewiseBinarySensorDescription(
        key="light_on",
        name="Night Light",
        path=("device_state", "light_on"),
    ),
    CradlewiseBinarySensorDescription(
        key="loud_sound_detected",
        name="Loud Sound Detected",
        path=("device_state", "loud_sound_detected"),
        device_class=BinarySensorDeviceClass.SOUND,
    ),
    CradlewiseBinarySensorDescription(
        key="inside_sleep_schedule",
        name="In Sleep Schedule",
        path=("device_state", "inside_sleep_schedule"),
    ),
    CradlewiseBinarySensorDescription(
        key="inside_soothing_window",
        name="In Soothing Window",
        path=("device_state", "inside_soothing_window"),
    ),
    CradlewiseBinarySensorDescription(
        key="rocking_not_effective",
        name="Rocking Not Effective",
        path=("device_state", "rocking_not_effective"),
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    CradlewiseBinarySensorDescription(
        key="obstruction_detected",
        name="Obstruction Detected",
        path=("device_state", "obstruction_detected"),
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    CradlewiseBinarySensorDescription(
        key="breath_trigger",
        name="Breath Trigger",
        path=("device_state", "breath_trigger"),
    ),
    CradlewiseBinarySensorDescription(
        key="lower_breath_rate_alert",
        name="Lower Breath Rate Alert",
        path=("device_state", "lower_breath_rate_alert"),
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    CradlewiseBinarySensorDescription(
        key="keep_bounce_on_during_sleep",
        name="Keep Bounce On During Sleep",
        path=("device_state", "keep_bounce_on_during_sleep"),
    ),
    CradlewiseBinarySensorDescription(
        key="keep_music_on_during_sleep",
        name="Keep Music On During Sleep",
        path=("device_state", "keep_music_on_during_sleep"),
    ),
    CradlewiseBinarySensorDescription(
        key="auto_mode_lock_on",
        name="Auto Mode Lock",
        path=("device_state", "auto_mode_lock_on"),
    ),
    CradlewiseBinarySensorDescription(
        key="update_available",
        name="Update Available",
        path=("device_state", "update_available"),
    ),
    CradlewiseBinarySensorDescription(
        key="update_first",
        name="Update First",
        path=("device_state", "update_first"),
    ),
    CradlewiseBinarySensorDescription(
        key="is_calibration_done",
        name="Calibration Done",
        path=("device_state", "is_calibration_done"),
    ),
    CradlewiseBinarySensorDescription(
        key="app_flip_video",
        name="App Flip Video",
        path=("device_state", "app_flip_video"),
    ),
    CradlewiseBinarySensorDescription(
        key="max_sound_preview",
        name="Max Sound Preview",
        path=("device_state", "max_sound_preview"),
    ),
    CradlewiseBinarySensorDescription(
        key="control_adaptive_soothing_enabled",
        name="Control Adaptive Soothing Enabled",
        path=("device_state", "control_adaptive_soothing_enabled"),
    ),
    CradlewiseBinarySensorDescription(
        key="control_breath_enabled",
        name="Control Breath Enabled",
        path=("device_state", "control_breath_enabled"),
    ),
    CradlewiseBinarySensorDescription(
        key="start_recipe_on",
        name="Start Recipe",
        path=("device_state", "start_recipe_on"),
    ),
    CradlewiseBinarySensorDescription(
        key="start_recipe_enabled",
        name="Start Recipe Enabled",
        path=("device_state", "start_recipe_enabled"),
    ),
    CradlewiseBinarySensorDescription(
        key="keep_bounce_on_during_sleep_is_on",
        name="Keep Bounce On During Sleep Is On",
        path=("device_state", "keep_bounce_on_during_sleep_is_on"),
    ),
    CradlewiseBinarySensorDescription(
        key="keep_music_on_during_sleep_is_on",
        name="Keep Music On During Sleep Is On",
        path=("device_state", "keep_music_on_during_sleep_is_on"),
    ),
    CradlewiseBinarySensorDescription(
        key="enable_acc_movement_detection",
        name="Enable ACC Movement Detection",
        path=("device_state", "enable_acc_movement_detection"),
    ),
    CradlewiseBinarySensorDescription(
        key="enable_coeff_sensor_update",
        name="Enable Coeff Sensor Update",
        path=("device_state", "enable_coeff_sensor_update"),
    ),
    CradlewiseBinarySensorDescription(
        key="upload_3d_data_enabled",
        name="Upload 3D Data Enabled",
        path=("device_state", "upload_3d_data_enabled"),
    ),
    CradlewiseBinarySensorDescription(
        key="upload_rgb_data_enabled",
        name="Upload RGB Data Enabled",
        path=("device_state", "upload_rgb_data_enabled"),
    ),
    CradlewiseBinarySensorDescription(
        key="significant_change_in_weight_enabled",
        name="Significant Change In Weight Enabled",
        path=("device_state", "significant_change_in_weight_enabled"),
    ),
    CradlewiseBinarySensorDescription(
        key="weight_detection_enabled",
        name="Weight Detection Enabled",
        path=("device_state", "weight_detection_enabled"),
    ),
    CradlewiseBinarySensorDescription(
        key="restart_ggc_requested",
        name="Restart GGC Requested",
        path=("device_state", "restart_ggc_requested"),
    ),
    CradlewiseBinarySensorDescription(
        key="charging",
        name="Charging",
        path=("device_state", "charging"),
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
    ),
    CradlewiseBinarySensorDescription(
        key="power_supply_removed",
        name="Power Supply Removed",
        path=("device_state", "power_supply_removed"),
        device_class=BinarySensorDeviceClass.PLUG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cradlewise status binary sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id].get("coordinator")
    if coordinator is None:
        return

    async_add_entities(
        CradlewiseStatusBinarySensor(entry, coordinator, description)
        for description in BINARY_SENSORS
    )


class CradlewiseStatusBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor backed by the bridge status API."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator,
        description: CradlewiseBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
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
