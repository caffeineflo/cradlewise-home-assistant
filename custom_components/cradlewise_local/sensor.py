"""Sensors for the Cradlewise local bridge."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_CRADLE_ID, DOMAIN
from .status_helpers import path_value


@dataclass(frozen=True, kw_only=True)
class CradlewiseSensorDescription(SensorEntityDescription):
    """Description for a bridge status sensor."""

    path: tuple[str, ...]


SENSORS: tuple[CradlewiseSensorDescription, ...] = (
    CradlewiseSensorDescription(
        key="webrtc_connection_state",
        name="WebRTC Connection State",
        path=("webrtc", "connection_state"),
    ),
    CradlewiseSensorDescription(
        key="ice_connection_state",
        name="ICE Connection State",
        path=("webrtc", "ice_connection_state"),
    ),
    CradlewiseSensorDescription(
        key="video_frames",
        name="Video Frames",
        path=("media", "video_frames"),
    ),
    CradlewiseSensorDescription(
        key="audio_frames",
        name="Audio Frames",
        path=("media", "audio_frames"),
    ),
    CradlewiseSensorDescription(
        key="resolution",
        name="Resolution",
        path=("media", "resolution"),
    ),
    CradlewiseSensorDescription(
        key="uptime",
        name="Bridge Uptime",
        path=("bridge", "uptime_seconds"),
        native_unit_of_measurement=UnitOfTime.SECONDS,
    ),
    CradlewiseSensorDescription(
        key="cradle_state",
        name="Cradle State",
        path=("cradle_state", "state"),
    ),
    CradlewiseSensorDescription(
        key="cradle_op_mode",
        name="Cradle Op Mode",
        path=("cradle_state", "op_mode"),
    ),
    CradlewiseSensorDescription(
        key="wifi_strength",
        name="WiFi Strength",
        path=("cradle_state", "wifi_strength"),
        native_unit_of_measurement="dBm",
    ),
    CradlewiseSensorDescription(
        key="wifi_ssid",
        name="WiFi SSID",
        path=("cradle_state", "wifi_ssid"),
    ),
    CradlewiseSensorDescription(
        key="local_ip",
        name="Local IP",
        path=("cradle_state", "local_ip"),
    ),
    CradlewiseSensorDescription(
        key="device_state_source",
        name="Device State Source",
        path=("device_state", "source"),
    ),
    CradlewiseSensorDescription(
        key="device_state_updated_at",
        name="Device State Updated At",
        path=("device_state", "updated_at"),
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    CradlewiseSensorDescription(
        key="sleep_state",
        name="Sleep State",
        path=("device_state", "sleep_state"),
    ),
    CradlewiseSensorDescription(
        key="sleep_phase",
        name="Sleep Phase",
        path=("device_state", "sleep_phase"),
    ),
    CradlewiseSensorDescription(
        key="sleep_phase_raw",
        name="Sleep Phase Raw",
        path=("device_state", "sleep_phase_raw"),
    ),
    CradlewiseSensorDescription(
        key="sleep_event",
        name="Sleep Event",
        path=("device_state", "sleep_event"),
    ),
    CradlewiseSensorDescription(
        key="sleep_state_raw",
        name="Sleep State Raw",
        path=("device_state", "sleep_state_raw"),
    ),
    CradlewiseSensorDescription(
        key="sleep_state_internal",
        name="Sleep State Internal",
        path=("device_state", "sleep_state_internal"),
    ),
    CradlewiseSensorDescription(
        key="sleep_phase_event_start_time",
        name="Sleep Phase Event Start Time",
        path=("device_state", "sleep_phase_event_start_time"),
    ),
    CradlewiseSensorDescription(
        key="sleep_phase_duration_start_time",
        name="Sleep Phase Duration Start Time",
        path=("device_state", "sleep_phase_duration_start_time"),
    ),
    CradlewiseSensorDescription(
        key="sleep_phase_present_toggle_time",
        name="Sleep Phase Present Toggle Time",
        path=("device_state", "sleep_phase_present_toggle_time"),
    ),
    CradlewiseSensorDescription(
        key="cradle_mode",
        name="Cradle Mode",
        path=("device_state", "cradle_mode"),
    ),
    CradlewiseSensorDescription(
        key="bounce_mode",
        name="Bounce Mode",
        path=("device_state", "bounce_mode"),
    ),
    CradlewiseSensorDescription(
        key="bounce_setting",
        name="Bounce Setting",
        path=("device_state", "bounce_setting"),
    ),
    CradlewiseSensorDescription(
        key="bounce_amplitude",
        name="Bounce Amplitude",
        path=("device_state", "bounce_amplitude"),
    ),
    CradlewiseSensorDescription(
        key="bounce_level",
        name="Bounce Level",
        path=("device_state", "bounce_level"),
    ),
    CradlewiseSensorDescription(
        key="bounce_always_on_intensity",
        name="Bounce Always On Intensity",
        path=("device_state", "bounce_always_on_intensity"),
    ),
    CradlewiseSensorDescription(
        key="bounce_duration",
        name="Bounce Duration",
        path=("device_state", "bounce_duration"),
        native_unit_of_measurement=UnitOfTime.MINUTES,
    ),
    CradlewiseSensorDescription(
        key="bounce_duration_limit",
        name="Bounce Duration Limit",
        path=("device_state", "bounce_duration_limit"),
        native_unit_of_measurement=UnitOfTime.MINUTES,
    ),
    CradlewiseSensorDescription(
        key="bounce_time_remaining",
        name="Bounce Time Remaining",
        path=("device_state", "bounce_time_remaining"),
        native_unit_of_measurement=UnitOfTime.MINUTES,
    ),
    CradlewiseSensorDescription(
        key="bounce_tilt_state",
        name="Bounce Tilt State",
        path=("device_state", "bounce_tilt_state"),
    ),
    CradlewiseSensorDescription(
        key="bounce_movement_energy_threshold",
        name="Bounce Movement Energy Threshold",
        path=("device_state", "bounce_movement_energy_threshold"),
    ),
    CradlewiseSensorDescription(
        key="bounce_acc_frame_peaks_threshold",
        name="Bounce Acc Frame Peaks Threshold",
        path=("device_state", "bounce_acc_frame_peaks_threshold"),
    ),
    CradlewiseSensorDescription(
        key="responsivity_setting",
        name="Responsivity Setting",
        path=("device_state", "responsivity_setting"),
    ),
    CradlewiseSensorDescription(
        key="music_mood",
        name="Music Mood",
        path=("device_state", "music_mood"),
    ),
    CradlewiseSensorDescription(
        key="music_volume",
        name="Music Volume",
        path=("device_state", "music_volume"),
    ),
    CradlewiseSensorDescription(
        key="music_level",
        name="Sound Level",
        path=("device_state", "music_level"),
    ),
    CradlewiseSensorDescription(
        key="music_mode",
        name="Music Mode",
        path=("device_state", "music_mode"),
    ),
    CradlewiseSensorDescription(
        key="volume_profile",
        name="Volume Profile",
        path=("device_state", "volume_profile"),
    ),
    CradlewiseSensorDescription(
        key="sound_ambience",
        name="Sound Ambience",
        path=("device_state", "sound_ambience"),
    ),
    CradlewiseSensorDescription(
        key="sound_ambience_raw",
        name="Sound Ambience Raw",
        path=("device_state", "sound_ambience_raw"),
    ),
    CradlewiseSensorDescription(
        key="sound_color",
        name="Sound Color",
        path=("device_state", "sound_color"),
    ),
    CradlewiseSensorDescription(
        key="sound_color_raw",
        name="Sound Color Raw",
        path=("device_state", "sound_color_raw"),
    ),
    CradlewiseSensorDescription(
        key="sound_heartbeat_volume",
        name="Sound Heartbeat Volume",
        path=("device_state", "sound_heartbeat_volume"),
    ),
    CradlewiseSensorDescription(
        key="sound_breath_volume",
        name="Sound Breath Volume",
        path=("device_state", "sound_breath_volume"),
    ),
    CradlewiseSensorDescription(
        key="lullabies_action",
        name="Lullabies Action",
        path=("device_state", "lullabies_action"),
    ),
    CradlewiseSensorDescription(
        key="lullabies_current_song_id",
        name="Lullabies Current Song ID",
        path=("device_state", "lullabies_current_song_id"),
    ),
    CradlewiseSensorDescription(
        key="lullabies_desired_playlist_id",
        name="Lullabies Desired Playlist ID",
        path=("device_state", "lullabies_desired_playlist_id"),
    ),
    CradlewiseSensorDescription(
        key="lullabies_desired_song_id",
        name="Lullabies Desired Song ID",
        path=("device_state", "lullabies_desired_song_id"),
    ),
    CradlewiseSensorDescription(
        key="lullabies_elapsed_time",
        name="Lullabies Elapsed Time",
        path=("device_state", "lullabies_elapsed_time"),
        native_unit_of_measurement=UnitOfTime.SECONDS,
    ),
    CradlewiseSensorDescription(
        key="lullabies_loop",
        name="Lullabies Loop",
        path=("device_state", "lullabies_loop"),
    ),
    CradlewiseSensorDescription(
        key="lullabies_timer_duration",
        name="Lullabies Timer Duration",
        path=("device_state", "lullabies_timer_duration"),
        native_unit_of_measurement=UnitOfTime.MINUTES,
    ),
    CradlewiseSensorDescription(
        key="lullabies_volume",
        name="Lullabies Volume",
        path=("device_state", "lullabies_volume"),
    ),
    CradlewiseSensorDescription(
        key="music_duration",
        name="Music Duration",
        path=("device_state", "music_duration"),
        native_unit_of_measurement=UnitOfTime.MINUTES,
    ),
    CradlewiseSensorDescription(
        key="music_time_remaining",
        name="Music Time Remaining",
        path=("device_state", "music_time_remaining"),
        native_unit_of_measurement=UnitOfTime.MINUTES,
    ),
    CradlewiseSensorDescription(
        key="light_intensity",
        name="Light Intensity",
        path=("device_state", "light_intensity"),
    ),
    CradlewiseSensorDescription(
        key="battery_life",
        name="Battery Life",
        path=("device_state", "battery_life"),
    ),
    CradlewiseSensorDescription(
        key="ambient_temperature",
        name="Ambient Temperature",
        path=("device_state", "ambient_temperature"),
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    CradlewiseSensorDescription(
        key="device_uptime_service",
        name="Device Service Uptime",
        path=("device_state", "device_uptime_service"),
        native_unit_of_measurement=UnitOfTime.SECONDS,
    ),
    CradlewiseSensorDescription(
        key="device_uptime_total",
        name="Device Total Uptime",
        path=("device_state", "device_uptime_total"),
        native_unit_of_measurement=UnitOfTime.SECONDS,
    ),
    CradlewiseSensorDescription(
        key="operation_state",
        name="Operation State",
        path=("device_state", "operation_state"),
    ),
    CradlewiseSensorDescription(
        key="reported_state",
        name="Reported State",
        path=("device_state", "reported_state"),
    ),
    CradlewiseSensorDescription(
        key="deploy_state",
        name="Deploy State",
        path=("device_state", "deploy_state"),
    ),
    CradlewiseSensorDescription(
        key="sequence_id",
        name="Sequence ID",
        path=("device_state", "sequence_id"),
    ),
    CradlewiseSensorDescription(
        key="report_wrong_status",
        name="Report Wrong Status",
        path=("device_state", "report_wrong_status"),
    ),
    CradlewiseSensorDescription(
        key="calibrate_cradle",
        name="Calibrate Cradle",
        path=("device_state", "calibrate_cradle"),
    ),
    CradlewiseSensorDescription(
        key="calibrate_cradle_raw",
        name="Calibrate Cradle Raw",
        path=("device_state", "calibrate_cradle_raw"),
    ),
    CradlewiseSensorDescription(
        key="calibration_type",
        name="Calibration Type",
        path=("device_state", "calibration_type"),
    ),
    CradlewiseSensorDescription(
        key="calibration_type_raw",
        name="Calibration Type Raw",
        path=("device_state", "calibration_type_raw"),
    ),
    CradlewiseSensorDescription(
        key="calibration_stage",
        name="Calibration Stage",
        path=("device_state", "calibration_stage"),
    ),
    CradlewiseSensorDescription(
        key="calibration_status",
        name="Calibration Status",
        path=("device_state", "calibration_status"),
    ),
    CradlewiseSensorDescription(
        key="calibration_history_complete",
        name="Calibration History Complete",
        path=("device_state", "calibration_history_complete"),
    ),
    CradlewiseSensorDescription(
        key="calibration_history_gain_setup",
        name="Calibration History Gain Setup",
        path=("device_state", "calibration_history_gain_setup"),
    ),
    CradlewiseSensorDescription(
        key="calibration_history_mic_setup",
        name="Calibration History Mic Setup",
        path=("device_state", "calibration_history_mic_setup"),
    ),
    CradlewiseSensorDescription(
        key="calibration_history_noise_profile_setup",
        name="Calibration History Noise Profile Setup",
        path=("device_state", "calibration_history_noise_profile_setup"),
    ),
    CradlewiseSensorDescription(
        key="calibration_history_tof_calibration",
        name="Calibration History ToF Calibration",
        path=("device_state", "calibration_history_tof_calibration"),
    ),
    CradlewiseSensorDescription(
        key="calibration_history_weight_calibration",
        name="Calibration History Weight Calibration",
        path=("device_state", "calibration_history_weight_calibration"),
    ),
    CradlewiseSensorDescription(
        key="user_action_for_obstruction",
        name="User Action For Obstruction",
        path=("device_state", "user_action_for_obstruction"),
    ),
    CradlewiseSensorDescription(
        key="cradle_mode_to_calibrate",
        name="Cradle Mode To Calibrate",
        path=("device_state", "cradle_mode_to_calibrate"),
    ),
    CradlewiseSensorDescription(
        key="wifi_score",
        name="WiFi Score",
        path=("device_state", "wifi_score"),
    ),
    CradlewiseSensorDescription(
        key="wifi_score_snr",
        name="WiFi SNR Score",
        path=("device_state", "wifi_score_snr"),
    ),
    CradlewiseSensorDescription(
        key="wifi_score_speed",
        name="WiFi Speed Score",
        path=("device_state", "wifi_score_speed"),
    ),
    CradlewiseSensorDescription(
        key="wifi_score_loss",
        name="WiFi Loss Score",
        path=("device_state", "wifi_score_loss"),
    ),
    CradlewiseSensorDescription(
        key="wifi_score_jitter",
        name="WiFi Jitter Score",
        path=("device_state", "wifi_score_jitter"),
    ),
    CradlewiseSensorDescription(
        key="wifi_stats_strength",
        name="WiFi Stats Strength",
        path=("device_state", "wifi_stats_strength"),
    ),
    CradlewiseSensorDescription(
        key="wifi_stats_rssi0",
        name="WiFi Stats RSSI 0",
        path=("device_state", "wifi_stats_rssi0"),
        native_unit_of_measurement="dBm",
    ),
    CradlewiseSensorDescription(
        key="wifi_stats_rssi1",
        name="WiFi Stats RSSI 1",
        path=("device_state", "wifi_stats_rssi1"),
        native_unit_of_measurement="dBm",
    ),
    CradlewiseSensorDescription(
        key="wifi_stats_noise",
        name="WiFi Stats Noise",
        path=("device_state", "wifi_stats_noise"),
        native_unit_of_measurement="dBm",
    ),
    CradlewiseSensorDescription(
        key="wifi_stats_bitrate",
        name="WiFi Stats Bitrate",
        path=("device_state", "wifi_stats_bitrate"),
    ),
    CradlewiseSensorDescription(
        key="wifi_stats_ssid",
        name="WiFi Stats SSID",
        path=("device_state", "wifi_stats_ssid"),
    ),
    CradlewiseSensorDescription(
        key="wifi_stats_arp_success_count",
        name="WiFi Stats ARP Success Count",
        path=("device_state", "wifi_stats_arp_success_count"),
    ),
    CradlewiseSensorDescription(
        key="wifi_stats_beacon_loss_count",
        name="WiFi Stats Beacon Loss Count",
        path=("device_state", "wifi_stats_beacon_loss_count"),
    ),
    CradlewiseSensorDescription(
        key="software_version",
        name="Software Version",
        path=("device_state", "software_version"),
    ),
    CradlewiseSensorDescription(
        key="rootfs_version",
        name="RootFS Version",
        path=("device_state", "rootfs_version"),
    ),
    CradlewiseSensorDescription(
        key="shadow_version",
        name="Shadow Version",
        path=("device_state", "shadow_version"),
    ),
    CradlewiseSensorDescription(
        key="cradle_timezone",
        name="Cradle Timezone",
        path=("device_state", "cradle_timezone"),
    ),
    CradlewiseSensorDescription(
        key="baby_profile_last_updated_time",
        name="Baby Profile Last Updated Time",
        path=("device_state", "baby_profile_last_updated_time"),
    ),
    CradlewiseSensorDescription(
        key="update_status",
        name="Update Status",
        path=("device_state", "update_status"),
    ),
    CradlewiseSensorDescription(
        key="update_step",
        name="Update Step",
        path=("device_state", "update_step"),
    ),
    CradlewiseSensorDescription(
        key="update_version",
        name="Update Version",
        path=("device_state", "update_version"),
    ),
    CradlewiseSensorDescription(
        key="update_progress",
        name="Update Progress",
        path=("device_state", "update_progress"),
    ),
    CradlewiseSensorDescription(
        key="update_type",
        name="Update Type",
        path=("device_state", "update_type"),
    ),
    CradlewiseSensorDescription(
        key="update_error_reason",
        name="Update Error Reason",
        path=("device_state", "update_error_reason"),
    ),
    CradlewiseSensorDescription(
        key="control_bna_alert_control",
        name="Control BNA Alert Control",
        path=("device_state", "control_bna_alert_control"),
    ),
    CradlewiseSensorDescription(
        key="control_cry_sensitivity",
        name="Control Cry Sensitivity",
        path=("device_state", "control_cry_sensitivity"),
    ),
    CradlewiseSensorDescription(
        key="control_css_responsiveness",
        name="Control CSS Responsiveness",
        path=("device_state", "control_css_responsiveness"),
    ),
    CradlewiseSensorDescription(
        key="control_video_service_bit_mask",
        name="Control Video Service Bit Mask",
        path=("device_state", "control_video_service_bit_mask"),
    ),
    CradlewiseSensorDescription(
        key="breath_rate",
        name="Breath Rate",
        path=("device_state", "breath_rate"),
    ),
    CradlewiseSensorDescription(
        key="breath_final_rate",
        name="Breath Final Rate",
        path=("device_state", "breath_final_rate"),
    ),
    CradlewiseSensorDescription(
        key="breath_state",
        name="Breath State",
        path=("device_state", "breath_state"),
    ),
    CradlewiseSensorDescription(
        key="breath_reason",
        name="Breath Reason",
        path=("device_state", "breath_reason"),
    ),
    CradlewiseSensorDescription(
        key="keep_bounce_on_during_sleep_level",
        name="Keep Bounce On During Sleep Level",
        path=("device_state", "keep_bounce_on_during_sleep_level"),
    ),
    CradlewiseSensorDescription(
        key="keep_music_on_during_sleep_level",
        name="Keep Music On During Sleep Level",
        path=("device_state", "keep_music_on_during_sleep_level"),
    ),
    CradlewiseSensorDescription(
        key="auto_mode_lock_end_time",
        name="Auto Mode Lock End Time",
        path=("device_state", "auto_mode_lock_end_time"),
    ),
    CradlewiseSensorDescription(
        key="auto_mode_lock_duration",
        name="Auto Mode Lock Duration",
        path=("device_state", "auto_mode_lock_duration"),
        native_unit_of_measurement=UnitOfTime.MINUTES,
    ),
    CradlewiseSensorDescription(
        key="start_recipe_lock_end_time",
        name="Start Recipe Lock End Time",
        path=("device_state", "start_recipe_lock_end_time"),
    ),
    CradlewiseSensorDescription(
        key="start_recipe_lock_duration",
        name="Start Recipe Lock Duration",
        path=("device_state", "start_recipe_lock_duration"),
        native_unit_of_measurement=UnitOfTime.MINUTES,
    ),
    CradlewiseSensorDescription(
        key="start_recipe_bounce_level",
        name="Start Recipe Bounce Level",
        path=("device_state", "start_recipe_bounce_level"),
    ),
    CradlewiseSensorDescription(
        key="start_recipe_music_level",
        name="Start Recipe Music Level",
        path=("device_state", "start_recipe_music_level"),
    ),
    CradlewiseSensorDescription(
        key="max_bounce_limit",
        name="Max Bounce Limit",
        path=("device_state", "max_bounce_limit"),
    ),
    CradlewiseSensorDescription(
        key="max_volume_limit",
        name="Max Volume Limit",
        path=("device_state", "max_volume_limit"),
    ),
    CradlewiseSensorDescription(
        key="sleep_time",
        name="Sleep Time",
        path=("device_state", "sleep_time"),
    ),
    CradlewiseSensorDescription(
        key="wake_up_time",
        name="Wake Up Time",
        path=("device_state", "wake_up_time"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cradlewise status sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id].get("coordinator")
    if coordinator is None:
        return

    async_add_entities(
        CradlewiseStatusSensor(entry, coordinator, description)
        for description in SENSORS
    )


class CradlewiseStatusSensor(CoordinatorEntity, SensorEntity):
    """Sensor backed by the bridge status API."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator,
        description: CradlewiseSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._cradle_id = entry.data[CONF_CRADLE_ID]
        self._attr_name = description.name
        self._attr_unique_id = f"{self._cradle_id}_{description.key}"
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._cradle_id)},
            manufacturer="Cradlewise",
            name=entry.data.get(CONF_NAME, "Cradlewise Local"),
        )

    @property
    def native_value(self) -> Any:
        value = path_value(self.coordinator.data, self.entity_description.path)
        if (
            self.entity_description.device_class == SensorDeviceClass.TIMESTAMP
            and isinstance(value, int | float)
        ):
            return datetime.fromtimestamp(value, tz=UTC)
        return value
