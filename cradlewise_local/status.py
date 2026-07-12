"""Bridge status state and HTTP exposure."""

from __future__ import annotations

import copy
import hmac
import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .commands import CommandError, CommandUnavailable

log = logging.getLogger(__name__)

SLEEP_PHASE_MAP = {
    0: "away",
    1: "awake",
    2: "stirring",
    3: "stirring",
    4: "sleep",
    5: "awake",
    6: "stirring",
}

SLEEP_EVENT_MAP = {
    0: "away",
    1: "awake",
    2: "awake",
    3: "stirring",
    4: "sleep",
    5: "sleep",
}

SLEEP_STATE_MAP = {
    0: "Baby not present",
    2: "Active Awake",
    3: "Quite Awake",
    4: "Light sleep",
    5: "Deep sleep",
}

SOUND_AMBIENCE_MAP = {
    0: "light rain",
    1: "heavy rain",
    2: "waves",
    3: "fan",
}

SOUND_COLOR_MAP = {
    0: "white",
    1: "pink",
    2: "brown",
}

CALIBRATE_CRADLE_MAP = {
    0: "idle",
    1: "ongoing",
    2: "stopping",
}

CALIBRATION_TYPE_MAP = {
    0: "full",
    1: "partial",
}

DEVICE_STATE_KEYS = {
    "actuator",
    "appSettings",
    "autoModeLockDuration",
    "babyNeedsAttention",
    "babyNeedsHelp",
    "babyPresentPrev",
    "babyPresent",
    "babySleepPhase",
    "babySleepPhaseV2",
    "babySleepState",
    "bluetooth",
    "bounceMode",
    "bounceLevelAmplitudes",
    "bounceSetting",
    "calibrateCradle",
    "calibrationHistory",
    "calibrationType",
    "control",
    "cradleModeToCalibrate",
    "deviceStatus",
    "hasBabyEverBeenPlaced",
    "insideSleepSchedule",
    "insideSoothingWindow",
    "isCalibrationDone",
    "isCribHelping",
    "keepBounceOnDuringSleepIsOn",
    "keepMusicOnDuringSleepIsOn",
    "light",
    "loudSoundDetected",
    "lullabies",
    "maxBounceLimit",
    "maxSoundPreview",
    "maxVolumeLimit",
    "meta",
    "mode",
    "music",
    "musicMode",
    "responsivitySetting",
    "rockingNotEffective",
    "sleepTime",
    "wakeUpTime",
    "rawShadow",
    "baby_present",
    "baby_sleep_state",
    "babyMonitor",
    "calibrationStatus",
    "connectivity",
    "bounceLevel",
    "bounce_setting",
    "musicDuration",
    "musicLevel",
    "musicTimeRemaining",
    "operationState",
    "reportWrongStatus",
    "responsivity_setting",
    "sequenceId",
    "shadowSync",
    "soundSynth",
    "startRecipeLockDuration",
    "update",
    "upload3DDataEnable",
    "uploadRGBDataEnable",
    "volumeProfile",
}


def _now() -> float:
    return time.time()


def _nested(payload: dict[str, Any] | None, *keys: str) -> Any:
    value: Any = payload
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _first_value(payload: dict[str, Any] | None, *paths: tuple[str, ...]) -> Any:
    for path in paths:
        value = _nested(payload, *path)
        if value is not None:
            return value
    return None


def _first_value_or_default(
    payload: dict[str, Any] | None,
    default: Any,
    *paths: tuple[str, ...],
) -> Any:
    value = _first_value(payload, *paths)
    return default if value is None else value


def _bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        if value == 0:
            return False
        if value == 1:
            return True
        return None
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in {"1", "true", "yes", "on"}:
            return True
        if cleaned in {"0", "false", "no", "off"}:
            return False
    return None


def _int_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mapped_int_name(value: Any, mapping: dict[int, str]) -> str | None:
    raw = _int_or_none(value)
    if raw is None:
        return None
    return mapping.get(raw, f"unknown ({raw})")


def _json_dict_or_none(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _wifi_stat(payload: dict[str, Any] | None, key: str) -> Any:
    stats = _json_dict_or_none(
        _first_value(
            payload,
            ("bluetooth", "wifiStats"),
            ("rawShadow", "bluetooth", "wifiStats"),
        )
    )
    if stats is None:
        return None
    return stats.get(key)


def _wifi_stat_path(payload: dict[str, Any] | None, *path: str) -> Any:
    stats = _json_dict_or_none(
        _first_value(
            payload,
            ("bluetooth", "wifiStats"),
            ("rawShadow", "bluetooth", "wifiStats"),
        )
    )
    if stats is None:
        return None
    return _nested(stats, *path)


def _wifi_stat_first(payload: dict[str, Any] | None, *paths: tuple[str, ...]) -> Any:
    for path in paths:
        value = _wifi_stat_path(payload, *path)
        if value is not None:
            return value
    return None


def _device_state_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    reported = _nested(payload, "state", "reported")
    if isinstance(reported, dict):
        return reported

    reported = payload.get("reported")
    if isinstance(reported, dict):
        return reported

    if DEVICE_STATE_KEYS.intersection(payload):
        return payload

    return None


def _merge_state(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Apply AWS shadow-style partial state without mutating either input."""
    merged = copy.deepcopy(base)
    for key, value in patch.items():
        if value is None:
            merged.pop(key, None)
        elif isinstance(value, dict):
            current = merged.get(key)
            nested_base = current if isinstance(current, dict) else {}
            merged[key] = _merge_state(nested_base, value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _sleep_phase_raw(payload: dict[str, Any] | None) -> int | None:
    phase_v2 = _first_value(
        payload,
        ("babySleepPhaseV2", "eventValue"),
        ("rawShadow", "babySleepPhaseV2", "eventValue"),
    )
    if phase_v2 is not None:
        return _int_or_none(phase_v2)
    return _int_or_none(
        _first_value(payload, ("babySleepPhase",), ("rawShadow", "babySleepPhase"))
    )


def _sleep_phase_name(payload: dict[str, Any] | None) -> str | None:
    raw = _sleep_phase_raw(payload)
    if raw is not None:
        return SLEEP_PHASE_MAP.get(raw, f"unknown ({raw})")
    value = _nested(payload, "babySleepPhase")
    return str(value) if value is not None else None


def _sleep_event_name(payload: dict[str, Any] | None) -> str | None:
    raw = _sleep_phase_raw(payload)
    if raw is not None:
        return SLEEP_EVENT_MAP.get(raw, f"unknown ({raw})")
    return None


def _sleep_state_name(payload: dict[str, Any] | None) -> str | None:
    value = _first_value(
        payload,
        ("babySleepState",),
        ("baby_sleep_state",),
        ("rawShadow", "babySleepState"),
    )
    raw = _int_or_none(value)
    if raw is not None:
        return SLEEP_STATE_MAP.get(raw, f"unknown ({raw})")
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _ambient_temperature_c(payload: dict[str, Any] | None) -> float | None:
    value = _float_or_none(
        _first_value(
            payload,
            ("ambientTempInCelsius",),
            ("rawShadow", "ambientTempInCelsius"),
        )
    )
    if value is not None:
        return value

    value = _float_or_none(
        _first_value(
            payload,
            ("deviceStatus", "ambientTemp"),
            ("rawShadow", "deviceStatus", "ambientTemp"),
        )
    )
    if value is None:
        return None
    if abs(value) > 200:
        return value / 1000
    return value


def _device_state_snapshot(payload: dict[str, Any] | None) -> dict[str, Any]:
    state = _device_state_payload(payload)
    inactive_default = False if state is not None else None
    light_intensity = _int_or_none(
        _first_value(
            state,
            ("light", "lightIntensity"),
            ("rawShadow", "light", "lightIntensity"),
        )
    )
    light_indicator_brightness = _int_or_none(
        _first_value(
            state,
            ("light", "indicatorBrightness"),
            ("rawShadow", "light", "indicatorBrightness"),
        )
    )
    snapshot = {
        "raw": state,
        "baby_present": _first_value(
            state,
            ("babyPresent",),
            ("baby_present",),
            ("rawShadow", "babyPresent"),
        ),
        "sleep_state": _sleep_state_name(state),
        "sleep_state_raw": _int_or_none(
            _first_value(state, ("rawShadow", "babySleepState"), ("babySleepState",))
        ),
        "sleep_state_internal": _int_or_none(
            _first_value(
                state,
                ("babySleepStateInternal",),
                ("rawShadow", "babySleepStateInternal"),
            )
        ),
        "sleep_state_being_determined": _first_value(
            state,
            ("babySleepStateBeingDetermined",),
            ("rawShadow", "babySleepStateBeingDetermined"),
        ),
        "sleep_phase": _sleep_phase_name(state),
        "sleep_phase_raw": _sleep_phase_raw(state),
        "sleep_event": _sleep_event_name(state),
        "sleep_phase_event_start_time": _first_value(
            state,
            ("babySleepPhaseV2", "eventStartTime"),
            ("rawShadow", "babySleepPhaseV2", "eventStartTime"),
        ),
        "sleep_phase_duration_start_time": _first_value(
            state,
            ("babySleepPhaseV2", "durationStartTime"),
            ("rawShadow", "babySleepPhaseV2", "durationStartTime"),
        ),
        "sleep_phase_present_toggle_time": _first_value(
            state,
            ("babySleepPhaseV2", "presentToggleTime"),
            ("rawShadow", "babySleepPhaseV2", "presentToggleTime"),
        ),
        "baby_presence_being_determined": _first_value(
            state,
            ("babyPresenceBeingDetermined",),
            ("rawShadow", "babyPresenceBeingDetermined"),
        ),
        "baby_needs_attention": _first_value_or_default(
            state,
            inactive_default,
            ("babyNeedsAttention",),
            ("rawShadow", "babyNeedsAttention"),
        ),
        "baby_needs_help": _first_value_or_default(
            state,
            inactive_default,
            ("babyNeedsHelp",),
            ("rawShadow", "babyNeedsHelp"),
        ),
        "crib_helping": _first_value_or_default(
            state,
            inactive_default,
            ("isCribHelping",),
            ("rawShadow", "isCribHelping"),
        ),
        "loud_sound_detected": _first_value_or_default(
            state,
            inactive_default,
            ("loudSoundDetected",),
            ("rawShadow", "loudSoundDetected"),
        ),
        "inside_sleep_schedule": _first_value_or_default(
            state,
            inactive_default,
            ("insideSleepSchedule",),
            ("rawShadow", "insideSleepSchedule"),
        ),
        "inside_soothing_window": _first_value_or_default(
            state,
            inactive_default,
            ("insideSoothingWindow",),
            ("rawShadow", "insideSoothingWindow"),
        ),
        "rocking_not_effective": _first_value_or_default(
            state,
            inactive_default,
            ("rockingNotEffective",),
            ("rawShadow", "rockingNotEffective"),
        ),
        "reported_state": _int_or_none(
            _first_value(state, ("state",), ("rawShadow", "state"))
        ),
        "deploy_state": _int_or_none(
            _first_value(state, ("deployState",), ("rawShadow", "deployState"))
        ),
        "sequence_id": _int_or_none(
            _first_value(state, ("sequenceId",), ("rawShadow", "sequenceId"))
        ),
        "report_wrong_status": _first_value(
            state, ("reportWrongStatus",), ("rawShadow", "reportWrongStatus")
        ),
        "operation_state": _first_value(
            state, ("operationState",), ("rawShadow", "operationState")
        ),
        "calibrate_cradle": _mapped_int_name(
            _first_value(state, ("calibrateCradle",), ("rawShadow", "calibrateCradle")),
            CALIBRATE_CRADLE_MAP,
        ),
        "calibrate_cradle_raw": _int_or_none(
            _first_value(state, ("calibrateCradle",), ("rawShadow", "calibrateCradle"))
        ),
        "calibration_type": _mapped_int_name(
            _first_value(state, ("calibrationType",), ("rawShadow", "calibrationType")),
            CALIBRATION_TYPE_MAP,
        ),
        "calibration_type_raw": _int_or_none(
            _first_value(state, ("calibrationType",), ("rawShadow", "calibrationType"))
        ),
        "calibration_stage": _first_value(
            state,
            ("calibrationStatus", "stage"),
            ("rawShadow", "calibrationStatus", "stage"),
        ),
        "calibration_status": _first_value(
            state,
            ("calibrationStatus", "status"),
            ("rawShadow", "calibrationStatus", "status"),
        ),
        "calibration_history_complete": _first_value(
            state,
            ("calibrationHistory", "complete"),
            ("rawShadow", "calibrationHistory", "complete"),
        ),
        "calibration_history_gain_setup": _first_value(
            state,
            ("calibrationHistory", "gainSetup"),
            ("rawShadow", "calibrationHistory", "gainSetup"),
        ),
        "calibration_history_mic_setup": _first_value(
            state,
            ("calibrationHistory", "micSetup"),
            ("rawShadow", "calibrationHistory", "micSetup"),
        ),
        "calibration_history_noise_profile_setup": _first_value(
            state,
            ("calibrationHistory", "noiseProfileSetup"),
            ("rawShadow", "calibrationHistory", "noiseProfileSetup"),
        ),
        "calibration_history_tof_calibration": _first_value(
            state,
            ("calibrationHistory", "tofCalibration"),
            ("rawShadow", "calibrationHistory", "tofCalibration"),
        ),
        "calibration_history_weight_calibration": _first_value(
            state,
            ("calibrationHistory", "weightCalibration"),
            ("rawShadow", "calibrationHistory", "weightCalibration"),
        ),
        "is_calibration_done": _first_value(
            state, ("isCalibrationDone",), ("rawShadow", "isCalibrationDone")
        ),
        "obstruction_detected": _first_value(
            state, ("obstructionToFDetected",), ("rawShadow", "obstructionToFDetected")
        ),
        "user_action_for_obstruction": _first_value(
            state,
            ("userActionForObstruction",),
            ("rawShadow", "userActionForObstruction"),
        ),
        "cradle_mode": _first_value(
            state,
            ("mode",),
            ("detectedCradleMode",),
            ("userSetCradleMode",),
            ("rawShadow", "detectedCradleMode"),
            ("rawShadow", "userSetCradleMode"),
        ),
        "cradle_mode_to_calibrate": _first_value(
            state,
            ("cradleModeToCalibrate",),
            ("rawShadow", "cradleModeToCalibrate"),
        ),
        "baby_present_previous": _first_value(
            state, ("babyPresentPrev",), ("rawShadow", "babyPresentPrev")
        ),
        "has_baby_ever_been_placed": _first_value(
            state,
            ("hasBabyEverBeenPlaced",),
            ("rawShadow", "hasBabyEverBeenPlaced"),
        ),
        "bounce_mode": _first_value(
            state, ("bounceMode",), ("rawShadow", "bounceMode")
        ),
        "bounce_setting": _first_value(
            state,
            ("bounceSetting",),
            ("bounce_setting",),
            ("rawShadow", "bounceSetting"),
        ),
        "bounce_disabled": _first_value(
            state,
            ("actuator", "disableBouncing"),
            ("rawShadow", "actuator", "disableBouncing"),
        ),
        "bounce_super_gentle": _first_value(
            state,
            ("actuator", "bounceSuperGentle"),
            ("rawShadow", "actuator", "bounceSuperGentle"),
        ),
        "bounce_always_on": _first_value(
            state,
            ("actuator", "bounceAlwaysOn"),
            ("rawShadow", "actuator", "bounceAlwaysOn"),
        ),
        "bounce_always_on_intensity": _int_or_none(
            _first_value(
                state,
                ("actuator", "bounceAlwaysOnIntensity"),
                ("rawShadow", "actuator", "bounceAlwaysOnIntensity"),
            )
        ),
        "bounce_duration": _int_or_none(
            _first_value(
                state, ("actuator", "duration"), ("rawShadow", "actuator", "duration")
            )
        ),
        "bounce_duration_limit": _int_or_none(
            _first_value(
                state,
                ("actuator", "durationLimit"),
                ("rawShadow", "actuator", "durationLimit"),
            )
        ),
        "bounce_time_remaining": _int_or_none(
            _first_value(
                state,
                ("actuator", "timeRemaining"),
                ("rawShadow", "actuator", "timeRemaining"),
            )
        ),
        "bounce_tap_detection_enabled": _first_value(
            state,
            ("actuator", "tapDetectionEnable"),
            ("rawShadow", "actuator", "tapDetectionEnable"),
        ),
        "bounce_push_gesture_enabled": _first_value(
            state,
            ("actuator", "pushGestureEnable"),
            ("rawShadow", "actuator", "pushGestureEnable"),
        ),
        "bounce_quiescent": _first_value(
            state,
            ("actuator", "quiescentBounce"),
            ("rawShadow", "actuator", "quiescentBounce"),
        ),
        "bounce_tilt_state": _int_or_none(
            _first_value(
                state, ("actuator", "tiltState"), ("rawShadow", "actuator", "tiltState")
            )
        ),
        "bounce_movement_energy_threshold": _int_or_none(
            _first_value(
                state,
                ("actuator", "movementEnergyThreshold"),
                ("rawShadow", "actuator", "movementEnergyThreshold"),
            )
        ),
        "bounce_acc_frame_peaks_threshold": _int_or_none(
            _first_value(
                state,
                ("actuator", "accFramePeaksThreshold"),
                ("rawShadow", "actuator", "accFramePeaksThreshold"),
            )
        ),
        "bounce_amplitude": _int_or_none(
            _first_value(
                state, ("actuator", "amplitude"), ("rawShadow", "actuator", "amplitude")
            )
        ),
        "bounce_level": _int_or_none(
            _first_value(state, ("bounceLevel",), ("rawShadow", "bounceLevel"))
        ),
        "bouncing": _first_value(
            state, ("actuator", "on"), ("rawShadow", "actuator", "on")
        ),
        "responsivity_setting": _first_value(
            state,
            ("responsivitySetting",),
            ("responsivity_setting",),
            ("rawShadow", "responsivitySetting"),
        ),
        "music_mode": _first_value(state, ("musicMode",), ("rawShadow", "musicMode")),
        "music_playing": _first_value(
            state,
            ("music", "play"),
            ("soundSynth", "play"),
            ("rawShadow", "soundSynth", "play"),
            ("rawShadow", "lullabies", "enableMusic"),
        ),
        "music_volume": _int_or_none(
            _first_value(
                state,
                ("music", "volume"),
                ("soundSynth", "volume"),
                ("rawShadow", "soundSynth", "volume"),
                ("rawShadow", "lullabies", "volume"),
            )
        ),
        "music_level": _int_or_none(
            _first_value(state, ("musicLevel",), ("rawShadow", "musicLevel"))
        ),
        "music_mood": _first_value(
            state,
            ("music", "mood"),
            ("soundSynth", "trackName"),
            ("rawShadow", "soundSynth", "trackName"),
        ),
        "volume_profile": _first_value_or_default(
            state,
            "normal" if state is not None else None,
            ("volumeProfile",),
            ("rawShadow", "volumeProfile"),
        ),
        "sound_ambience": _mapped_int_name(
            _first_value(
                state,
                ("soundSynth", "ambience"),
                ("rawShadow", "soundSynth", "ambience"),
            ),
            SOUND_AMBIENCE_MAP,
        ),
        "sound_ambience_raw": _int_or_none(
            _first_value(
                state,
                ("soundSynth", "ambience"),
                ("rawShadow", "soundSynth", "ambience"),
            )
        ),
        "sound_color": _mapped_int_name(
            _first_value(
                state, ("soundSynth", "color"), ("rawShadow", "soundSynth", "color")
            ),
            SOUND_COLOR_MAP,
        ),
        "sound_color_raw": _int_or_none(
            _first_value(
                state, ("soundSynth", "color"), ("rawShadow", "soundSynth", "color")
            )
        ),
        "sound_heartbeat_volume": _int_or_none(
            _first_value(
                state,
                ("soundSynth", "heartbeatVolume"),
                ("rawShadow", "soundSynth", "heartbeatVolume"),
            )
        ),
        "sound_breath_volume": _int_or_none(
            _first_value(
                state,
                ("soundSynth", "breathVolume"),
                ("rawShadow", "soundSynth", "breathVolume"),
            )
        ),
        "sound_spotify_service_enabled": _first_value(
            state,
            ("soundSynth", "spotifyServiceEnable"),
            ("rawShadow", "soundSynth", "spotifyServiceEnable"),
        ),
        "lullabies_action": _int_or_none(
            _first_value(
                state, ("lullabies", "action"), ("rawShadow", "lullabies", "action")
            )
        ),
        "lullabies_current_song_id": _first_value(
            state, ("lullabies", "curSongId"), ("rawShadow", "lullabies", "curSongId")
        ),
        "lullabies_desired_playlist_id": _first_value(
            state,
            ("lullabies", "desiredPlaylistId"),
            ("rawShadow", "lullabies", "desiredPlaylistId"),
        ),
        "lullabies_desired_song_id": _first_value(
            state,
            ("lullabies", "desiredSongId"),
            ("rawShadow", "lullabies", "desiredSongId"),
        ),
        "lullabies_elapsed_time": _int_or_none(
            _first_value(
                state,
                ("lullabies", "elapsedTime"),
                ("rawShadow", "lullabies", "elapsedTime"),
            )
        ),
        "lullabies_enabled": _first_value(
            state,
            ("lullabies", "enableMusic"),
            ("rawShadow", "lullabies", "enableMusic"),
        ),
        "lullabies_loop": _first_value(
            state, ("lullabies", "loop"), ("rawShadow", "lullabies", "loop")
        ),
        "lullabies_timer_duration": _int_or_none(
            _first_value(
                state,
                ("lullabies", "timerDuration"),
                ("rawShadow", "lullabies", "timerDuration"),
            )
        ),
        "lullabies_timer_on": _first_value(
            state, ("lullabies", "timerOn"), ("rawShadow", "lullabies", "timerOn")
        ),
        "lullabies_volume": _int_or_none(
            _first_value(
                state, ("lullabies", "volume"), ("rawShadow", "lullabies", "volume")
            )
        ),
        "music_duration": _int_or_none(
            _first_value(state, ("musicDuration",), ("rawShadow", "musicDuration"))
        ),
        "music_time_remaining": _int_or_none(
            _first_value(
                state, ("musicTimeRemaining",), ("rawShadow", "musicTimeRemaining")
            )
        ),
        "light_on": _first_value(
            state, ("light", "lightOn"), ("rawShadow", "light", "lightOn")
        ),
        "light_intensity": light_intensity,
        "light_indicator_brightness": light_indicator_brightness,
        "light_indicator_brightness_mode": _first_value(
            state,
            ("light", "indicatorBrightnessMode"),
            ("rawShadow", "light", "indicatorBrightnessMode"),
        ),
        "battery_life": _int_or_none(
            _first_value(
                state,
                ("deviceStatus", "batteryLife"),
                ("rawShadow", "deviceStatus", "batteryLife"),
            )
        ),
        "charging": _first_value(
            state,
            ("deviceStatus", "charging"),
            ("rawShadow", "deviceStatus", "charging"),
        ),
        "power_supply_removed": _first_value(
            state,
            ("deviceStatus", "supplyRemoved"),
            ("rawShadow", "deviceStatus", "supplyRemoved"),
        ),
        "ambient_temperature": _ambient_temperature_c(state),
        "device_uptime_service": _float_or_none(
            _first_value(
                state,
                ("deviceStatus", "uptimeService"),
                ("rawShadow", "deviceStatus", "uptimeService"),
            )
        ),
        "device_uptime_total": _float_or_none(
            _first_value(
                state,
                ("deviceStatus", "uptimeTotal"),
                ("rawShadow", "deviceStatus", "uptimeTotal"),
            )
        ),
        "wifi_score": _int_or_none(
            _first_value(
                state,
                ("connectivity", "wifiScore", "WiFi"),
                ("rawShadow", "connectivity", "wifiScore", "WiFi"),
            )
        ),
        "wifi_score_snr": _int_or_none(
            _first_value(
                state,
                ("connectivity", "wifiScore", "SNR"),
                ("rawShadow", "connectivity", "wifiScore", "SNR"),
            )
        ),
        "wifi_score_speed": _int_or_none(
            _first_value(
                state,
                ("connectivity", "wifiScore", "Speed"),
                ("rawShadow", "connectivity", "wifiScore", "Speed"),
            )
        ),
        "wifi_score_loss": _int_or_none(
            _first_value(
                state,
                ("connectivity", "wifiScore", "Loss"),
                ("rawShadow", "connectivity", "wifiScore", "Loss"),
            )
        ),
        "wifi_score_jitter": _int_or_none(
            _first_value(
                state,
                ("connectivity", "wifiScore", "Jitter"),
                ("rawShadow", "connectivity", "wifiScore", "Jitter"),
            )
        ),
        "wifi_stats_strength": _int_or_none(_wifi_stat(state, "strength")),
        "wifi_stats_rssi0": _int_or_none(_wifi_stat(state, "rssi0")),
        "wifi_stats_rssi1": _int_or_none(_wifi_stat(state, "rssi1")),
        "wifi_stats_noise": _int_or_none(_wifi_stat(state, "noise")),
        "wifi_stats_bitrate": _int_or_none(_wifi_stat(state, "bitrate")),
        "wifi_stats_ssid": _wifi_stat_first(
            state,
            ("ssid",),
            ("activeConnection", "ssid"),
        ),
        "wifi_stats_arp_success_count": _int_or_none(
            _wifi_stat(state, "ARPSuccessCount")
        ),
        "wifi_stats_beacon_loss_count": _int_or_none(
            _wifi_stat_first(state, ("BeaconLossCount",), ("beaconLossCount",))
        ),
        "software_version": _first_value(
            state,
            ("meta", "software_version"),
            ("rawShadow", "meta", "software_version"),
        ),
        "rootfs_version": _first_value(
            state, ("meta", "rootfs_version"), ("rawShadow", "meta", "rootfs_version")
        ),
        "shadow_version": _int_or_none(
            _first_value(
                state,
                ("meta", "shadow_version"),
                ("rawShadow", "meta", "shadow_version"),
            )
        ),
        "cradle_timezone": _first_value(
            state, ("meta", "timezone"), ("rawShadow", "meta", "timezone")
        ),
        "baby_profile_last_updated_time": _first_value(
            state,
            ("meta", "babyProfileLastUpdatedTime"),
            ("rawShadow", "meta", "babyProfileLastUpdatedTime"),
        ),
        "update_available": _first_value(
            state, ("update", "available"), ("rawShadow", "update", "available")
        ),
        "update_status": _first_value(
            state, ("update", "status"), ("rawShadow", "update", "status")
        ),
        "update_step": _first_value(
            state, ("update", "step"), ("rawShadow", "update", "step")
        ),
        "update_version": _first_value(
            state, ("update", "version"), ("rawShadow", "update", "version")
        ),
        "update_progress": _int_or_none(
            _first_value(
                state, ("update", "progress"), ("rawShadow", "update", "progress")
            )
        ),
        "update_type": _first_value(
            state, ("update", "type"), ("rawShadow", "update", "type")
        ),
        "update_error_reason": _first_value(
            state, ("update", "errReason"), ("rawShadow", "update", "errReason")
        ),
        "update_first": _first_value(
            state, ("update", "first"), ("rawShadow", "update", "first")
        ),
        "control_adaptive_soothing_enabled": _first_value(
            state,
            ("control", "adaptiveSoothingEnabled"),
            ("rawShadow", "control", "adaptiveSoothingEnabled"),
        ),
        "control_bna_alert_control": _int_or_none(
            _first_value(
                state,
                ("control", "bnaAlertControl"),
                ("rawShadow", "control", "bnaAlertControl"),
            )
        ),
        "control_breath_enabled": _first_value(
            state,
            ("control", "breathEnabled"),
            ("rawShadow", "control", "breathEnabled"),
        ),
        "control_cry_sensitivity": _int_or_none(
            _first_value(
                state,
                ("control", "crySensitivity"),
                ("rawShadow", "control", "crySensitivity"),
            )
        ),
        "control_css_responsiveness": _first_value(
            state,
            ("control", "cssResponsiveness"),
            ("rawShadow", "control", "cssResponsiveness"),
        ),
        "control_video_service_bit_mask": _int_or_none(
            _first_value(
                state,
                ("control", "videoServiceBitMask"),
                ("rawShadow", "control", "videoServiceBitMask"),
            )
        ),
        "breath_rate": _int_or_none(
            _first_value(
                state,
                ("babyMonitor", "breath", "rate"),
                ("rawShadow", "babyMonitor", "breath", "rate"),
            )
        ),
        "breath_final_rate": _int_or_none(
            _first_value(
                state,
                ("babyMonitor", "breath", "finalRate"),
                ("rawShadow", "babyMonitor", "breath", "finalRate"),
            )
        ),
        "breath_state": _int_or_none(
            _first_value(
                state,
                ("babyMonitor", "breath", "state"),
                ("rawShadow", "babyMonitor", "breath", "state"),
            )
        ),
        "breath_reason": _int_or_none(
            _first_value(
                state,
                ("babyMonitor", "breath", "reason"),
                ("rawShadow", "babyMonitor", "breath", "reason"),
            )
        ),
        "breath_trigger": _first_value(
            state,
            ("babyMonitor", "breathTrigger"),
            ("rawShadow", "babyMonitor", "breathTrigger"),
        ),
        "lower_breath_rate_alert": _first_value(
            state,
            ("babyMonitor", "lowerBreathRateAlert"),
            ("rawShadow", "babyMonitor", "lowerBreathRateAlert"),
        ),
        "keep_bounce_on_during_sleep": _first_value(
            state,
            ("keepBounceOnDuringSleep",),
            ("rawShadow", "keepBounceOnDuringSleep"),
        ),
        "keep_bounce_on_during_sleep_level": _int_or_none(
            _first_value(
                state,
                ("keepBounceOnDuringSleepLevel",),
                ("rawShadow", "keepBounceOnDuringSleepLevel"),
            )
        ),
        "keep_music_on_during_sleep": _first_value(
            state,
            ("keepMusicOnDuringSleep",),
            ("rawShadow", "keepMusicOnDuringSleep"),
        ),
        "keep_music_on_during_sleep_level": _int_or_none(
            _first_value(
                state,
                ("keepMusicOnDuringSleepLevel",),
                ("rawShadow", "keepMusicOnDuringSleepLevel"),
            )
        ),
        "auto_mode_lock_on": _first_value(
            state, ("autoModeLockOn",), ("rawShadow", "autoModeLockOn")
        ),
        "auto_mode_lock_duration": _int_or_none(
            _first_value(
                state, ("autoModeLockDuration",), ("rawShadow", "autoModeLockDuration")
            )
        ),
        "auto_mode_lock_end_time": _first_value(
            state, ("autoModeLockEndTime",), ("rawShadow", "autoModeLockEndTime")
        ),
        "start_recipe_on": _first_value(
            state, ("startRecipeOn",), ("rawShadow", "startRecipeOn")
        ),
        "start_recipe_enabled": _first_value(
            state, ("startRecipeEnabled",), ("rawShadow", "startRecipeEnabled")
        ),
        "start_recipe_lock_end_time": _first_value(
            state,
            ("startRecipeLockEndTime",),
            ("rawShadow", "startRecipeLockEndTime"),
        ),
        "start_recipe_lock_duration": _int_or_none(
            _first_value(
                state,
                ("startRecipeLockDuration",),
                ("rawShadow", "startRecipeLockDuration"),
            )
        ),
        "start_recipe_bounce_level": _int_or_none(
            _first_value(
                state,
                ("startRecipeBounceLevel",),
                ("rawShadow", "startRecipeBounceLevel"),
            )
        ),
        "start_recipe_music_level": _int_or_none(
            _first_value(
                state,
                ("startRecipeMusicLevel",),
                ("rawShadow", "startRecipeMusicLevel"),
            )
        ),
        "app_flip_video": _first_value(
            state,
            ("appSettings", "flipVideo"),
            ("rawShadow", "appSettings", "flipVideo"),
        ),
        "max_bounce_limit": _int_or_none(
            _first_value(state, ("maxBounceLimit",), ("rawShadow", "maxBounceLimit"))
        ),
        "max_volume_limit": _int_or_none(
            _first_value(state, ("maxVolumeLimit",), ("rawShadow", "maxVolumeLimit"))
        ),
        "max_sound_preview": _first_value(
            state, ("maxSoundPreview",), ("rawShadow", "maxSoundPreview")
        ),
        "keep_bounce_on_during_sleep_is_on": _first_value(
            state,
            ("keepBounceOnDuringSleepIsOn",),
            ("rawShadow", "keepBounceOnDuringSleepIsOn"),
        ),
        "keep_music_on_during_sleep_is_on": _first_value(
            state,
            ("keepMusicOnDuringSleepIsOn",),
            ("rawShadow", "keepMusicOnDuringSleepIsOn"),
        ),
        "enable_acc_movement_detection": _first_value(
            state,
            ("enableAccMovementDetection",),
            ("rawShadow", "enableAccMovementDetection"),
        ),
        "enable_coeff_sensor_update": _first_value(
            state,
            ("enableCoeffSensorUpdate",),
            ("rawShadow", "enableCoeffSensorUpdate"),
        ),
        "upload_3d_data_enabled": _first_value(
            state, ("upload3DDataEnable",), ("rawShadow", "upload3DDataEnable")
        ),
        "upload_rgb_data_enabled": _first_value(
            state, ("uploadRGBDataEnable",), ("rawShadow", "uploadRGBDataEnable")
        ),
        "significant_change_in_weight_enabled": _first_value(
            state,
            ("significantChangeInWeightEnable",),
            ("rawShadow", "significantChangeInWeightEnable"),
        ),
        "weight_detection_enabled": _first_value(
            state, ("weightDetectionEnable",), ("rawShadow", "weightDetectionEnable")
        ),
        "restart_ggc_requested": _first_value(
            state,
            ("shadowSync", "restartGGCRequest"),
            ("rawShadow", "shadowSync", "restartGGCRequest"),
        ),
        "sleep_time": _first_value(state, ("sleepTime",), ("rawShadow", "sleepTime")),
        "wake_up_time": _first_value(
            state, ("wakeUpTime",), ("rawShadow", "wakeUpTime")
        ),
    }
    boolean_fields = {
        "app_flip_video",
        "auto_mode_lock_on",
        "baby_needs_attention",
        "baby_needs_help",
        "baby_presence_being_determined",
        "baby_present",
        "baby_present_previous",
        "bounce_always_on",
        "bounce_disabled",
        "bounce_push_gesture_enabled",
        "bounce_quiescent",
        "bounce_super_gentle",
        "bounce_tap_detection_enabled",
        "bouncing",
        "breath_trigger",
        "charging",
        "control_adaptive_soothing_enabled",
        "control_breath_enabled",
        "crib_helping",
        "enable_acc_movement_detection",
        "enable_coeff_sensor_update",
        "has_baby_ever_been_placed",
        "inside_sleep_schedule",
        "inside_soothing_window",
        "is_calibration_done",
        "keep_bounce_on_during_sleep",
        "keep_bounce_on_during_sleep_is_on",
        "keep_music_on_during_sleep",
        "keep_music_on_during_sleep_is_on",
        "light_on",
        "loud_sound_detected",
        "lower_breath_rate_alert",
        "lullabies_enabled",
        "lullabies_timer_on",
        "max_sound_preview",
        "music_playing",
        "obstruction_detected",
        "power_supply_removed",
        "restart_ggc_requested",
        "rocking_not_effective",
        "significant_change_in_weight_enabled",
        "sleep_state_being_determined",
        "sound_spotify_service_enabled",
        "start_recipe_enabled",
        "start_recipe_on",
        "update_available",
        "upload_3d_data_enabled",
        "upload_rgb_data_enabled",
        "weight_detection_enabled",
    }
    for field_name in boolean_fields:
        snapshot[field_name] = _bool_or_none(snapshot[field_name])
    if snapshot["light_on"] is None and light_intensity is not None:
        snapshot["light_on"] = light_intensity > 0
    return snapshot


@dataclass
class BridgeStatusStore:
    """Thread-safe bridge status snapshot."""

    cradle_id: str
    crib_ip: str
    cloud_state_stale_after: int = 90
    local_state_stale_after: int = 300
    started_at: float = field(default_factory=_now)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _mqtt_connected: bool = False
    _webrtc_connection_state: str = "new"
    _ice_connection_state: str = "new"
    _video_width: int | None = None
    _video_height: int | None = None
    _video_frames: int = 0
    _audio_track: bool = False
    _audio_frames: int = 0
    _last_video_frame_at: float | None = None
    _last_audio_frame_at: float | None = None
    _last_mqtt_message_at: float | None = None
    _stream_started_at: float | None = None
    _last_cradle_state_at: float | None = None
    _last_snapshot_jpeg: bytes | None = None
    _last_snapshot_at: float | None = None
    _last_beacon_at: float | None = None
    _sink_started: bool = False
    _sink_healthy: bool = False
    _sink_error: str | None = None
    _sink_last_video_write_at: float | None = None
    _sink_last_audio_write_at: float | None = None
    _sink_awaiting_h264_sync: bool = False
    _sink_dropped_video_frames: int = 0
    _cradle_state: dict[str, Any] | None = None
    _device_states: dict[str, dict[str, Any]] = field(default_factory=dict)
    _device_state_updated_at: dict[str, float] = field(default_factory=dict)
    _device_state_errors: dict[str, str | None] = field(default_factory=dict)
    _beacon: dict[str, Any] | None = None

    def set_mqtt_connected(self, connected: bool) -> None:
        with self._lock:
            self._mqtt_connected = connected

    def mark_mqtt_message(self) -> None:
        with self._lock:
            self._last_mqtt_message_at = _now()

    def mark_stream_started(self) -> None:
        with self._lock:
            self._stream_started_at = _now()

    def set_webrtc_state(self, state: str) -> None:
        with self._lock:
            self._webrtc_connection_state = state

    def set_ice_state(self, state: str) -> None:
        with self._lock:
            self._ice_connection_state = state

    def set_video_resolution(self, width: int, height: int) -> None:
        with self._lock:
            self._video_width = width
            self._video_height = height

    def increment_video_frames(self) -> None:
        with self._lock:
            self._video_frames += 1
            self._last_video_frame_at = _now()

    def update_snapshot(self, jpeg: bytes) -> None:
        with self._lock:
            self._last_snapshot_jpeg = jpeg
            self._last_snapshot_at = _now()

    def snapshot_jpeg(self, max_age_seconds: float | None = None) -> bytes | None:
        with self._lock:
            if (
                max_age_seconds is not None
                and self._last_snapshot_at is not None
                and _now() - self._last_snapshot_at > max_age_seconds
            ):
                return None
            return self._last_snapshot_jpeg

    def snapshot_is_stale(self, max_age_seconds: float) -> bool:
        with self._lock:
            return (
                self._last_snapshot_at is not None
                and _now() - self._last_snapshot_at > max_age_seconds
            )

    def update_sink_health(self, health: dict[str, Any]) -> None:
        with self._lock:
            self._sink_started = bool(health.get("started"))
            self._sink_healthy = bool(health.get("healthy"))
            error = health.get("error")
            self._sink_error = str(error) if error else None
            self._sink_last_video_write_at = _float_or_none(
                health.get("last_video_write_at")
            )
            self._sink_last_audio_write_at = _float_or_none(
                health.get("last_audio_write_at")
            )
            self._sink_awaiting_h264_sync = bool(health.get("awaiting_h264_sync"))
            self._sink_dropped_video_frames = int(
                health.get("dropped_video_frames") or 0
            )

    def mark_audio_track(self) -> None:
        with self._lock:
            self._audio_track = True

    def increment_audio_frames(self) -> None:
        with self._lock:
            self._audio_frames += 1
            self._last_audio_frame_at = _now()

    def update_cradle_state(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._cradle_state = copy.deepcopy(payload)
            self._last_cradle_state_at = _now()
            state = _device_state_payload(payload)
            if state is not None:
                self._merge_device_state_locked(
                    state, "local_mqtt", self._last_cradle_state_at
                )

    def update_device_state(self, payload: dict[str, Any], source: str) -> None:
        state = _device_state_payload(payload)
        if state is None:
            return
        with self._lock:
            self._merge_device_state_locked(state, source, _now())

    def _merge_device_state_locked(
        self, state: dict[str, Any], source: str, updated_at: float
    ) -> None:
        current = self._device_states.get(source, {})
        self._device_states[source] = _merge_state(current, state)
        self._device_state_updated_at[source] = updated_at
        self._device_state_errors[source] = None

    def mark_device_state_error(self, source: str, error: str) -> None:
        with self._lock:
            self._device_state_errors[source] = error

    def _source_stale_locked(self, source: str, now: float) -> bool:
        updated_at = self._device_state_updated_at.get(source)
        if updated_at is None:
            return True
        if source.startswith("local_") and self._mqtt_connected:
            return False
        timeout = (
            self.cloud_state_stale_after
            if source == "cloud"
            else self.local_state_stale_after
        )
        return now - updated_at > timeout

    def _merged_device_state_locked(
        self, now: float
    ) -> tuple[dict[str, Any] | None, str | None, float | None, dict[str, Any]]:
        priority = {"cloud": 0, "local_mqtt": 1, "local_shadow": 2}
        all_sources = set(self._device_states) | set(self._device_state_errors)
        sources = sorted(
            all_sources,
            key=lambda source: (priority.get(source, 1), source),
        )
        source_meta = {}
        for source in sources:
            updated_at = self._device_state_updated_at.get(source)
            source_meta[source] = {
                "updated_at": updated_at,
                "age_seconds": (
                    max(0.0, now - updated_at) if updated_at is not None else None
                ),
                "stale": self._source_stale_locked(source, now),
                "error": self._device_state_errors.get(source),
            }
        fresh_sources = [
            source
            for source in sources
            if source in self._device_states and not source_meta[source]["stale"]
        ]
        selected_sources = fresh_sources or [
            source for source in sources if source in self._device_states
        ]
        if not selected_sources:
            return None, None, None, source_meta

        merged: dict[str, Any] = {}
        for source in selected_sources:
            merged = _merge_state(merged, self._device_states[source])
        selected_source = selected_sources[-1]
        return (
            merged,
            selected_source,
            self._device_state_updated_at[selected_source],
            source_meta,
        )

    def update_beacon(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._beacon = copy.deepcopy(payload)
            self._last_beacon_at = _now()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            now = _now()
            cradle_state = copy.deepcopy(self._cradle_state)
            beacon = copy.deepcopy(self._beacon)
            device_state, device_source, device_updated_at, source_meta = (
                self._merged_device_state_locked(now)
            )
            resolution = None
            if self._video_width and self._video_height:
                resolution = f"{self._video_width}x{self._video_height}"

            recent_video = (
                self._last_video_frame_at is not None
                and now - self._last_video_frame_at < 30
            )
            recent_sink_video = (
                self._sink_last_video_write_at is not None
                and now - self._sink_last_video_write_at < 30
            )
            sink_healthy = self._sink_healthy and recent_sink_video
            sink_ready = not self._sink_started or sink_healthy
            peer_healthy = self._webrtc_connection_state not in {
                "failed",
                "closed",
                "disconnected",
            } and self._ice_connection_state not in {
                "failed",
                "closed",
                "disconnected",
            }
            healthy = (
                self._mqtt_connected
                and self._video_frames > 0
                and recent_video
                and sink_ready
                and peer_healthy
            )
            device_snapshot = _device_state_snapshot(device_state)
            device_available = bool(device_state) and any(
                not metadata["stale"] for metadata in source_meta.values()
            )

            return {
                "bridge": {
                    "cradle_id": self.cradle_id,
                    "crib_ip": self.crib_ip,
                    "healthy": healthy,
                    "uptime_seconds": int(now - self.started_at),
                },
                "mqtt": {
                    "connected": self._mqtt_connected,
                    "last_message_at": self._last_mqtt_message_at,
                },
                "webrtc": {
                    "connection_state": self._webrtc_connection_state,
                    "ice_connection_state": self._ice_connection_state,
                },
                "media": {
                    "video_frames": self._video_frames,
                    "audio_frames": self._audio_frames,
                    "audio_track": self._audio_track,
                    "width": self._video_width,
                    "height": self._video_height,
                    "resolution": resolution,
                    "last_video_frame_at": self._last_video_frame_at,
                    "last_audio_frame_at": self._last_audio_frame_at,
                    "last_snapshot_at": self._last_snapshot_at,
                    "stream_started_at": self._stream_started_at,
                },
                "sink": {
                    "started": self._sink_started,
                    "healthy": sink_healthy,
                    "process_healthy": self._sink_healthy,
                    "error": self._sink_error,
                    "last_video_write_at": self._sink_last_video_write_at,
                    "last_audio_write_at": self._sink_last_audio_write_at,
                    "awaiting_h264_sync": self._sink_awaiting_h264_sync,
                    "dropped_video_frames": self._sink_dropped_video_frames,
                },
                "cradle_state": {
                    "raw": cradle_state,
                    "updated_at": self._last_cradle_state_at,
                    "state": _nested(cradle_state, "state", "state"),
                    "expected_resume_time": _nested(
                        cradle_state, "state", "expectedResumeTime"
                    ),
                    "op_mode": _nested(cradle_state, "state", "info", "opMode"),
                    "status": _nested(cradle_state, "state", "info", "status"),
                    "wifi_ssid": _first_value(
                        cradle_state,
                        ("info", "connectivity", "ssid"),
                    )
                    or device_snapshot["wifi_stats_ssid"],
                    "wifi_strength": _first_value(
                        cradle_state,
                        ("info", "connectivity", "strength"),
                    )
                    or device_snapshot["wifi_stats_rssi0"],
                    "wifi_frequency": _nested(
                        cradle_state, "info", "connectivity", "frequency"
                    ),
                    "local_ip": _nested(cradle_state, "info", "connectivity", "localIP")
                    or self.crib_ip,
                },
                "beacon": {
                    "raw": beacon,
                    "updated_at": self._last_beacon_at,
                },
                "device_state": {
                    **device_snapshot,
                    "updated_at": device_updated_at,
                    "source": device_source,
                    "available": device_available,
                    "stale": bool(device_state) and not device_available,
                    "sources": source_meta,
                },
            }

    def to_json_bytes(self) -> bytes:
        return json.dumps(self.snapshot(), sort_keys=True).encode()


CommandHandler = Callable[[dict[str, Any]], dict[str, Any]]


class BridgeStatusHttpServer:
    """Small stdlib HTTP server for bridge status snapshots."""

    def __init__(
        self,
        store: BridgeStatusStore,
        host: str,
        port: int,
        command_handler: CommandHandler | None = None,
        bearer_token: str | None = None,
        snapshot_max_age_seconds: float = 15,
    ) -> None:
        self.store = store
        self.host = host
        self.port = port
        self.command_handler = command_handler
        self.bearer_token = bearer_token
        self.snapshot_max_age_seconds = snapshot_max_age_seconds
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._httpd is not None:
            return
        store = self.store
        command_handler = self.command_handler
        bearer_token = self.bearer_token
        snapshot_max_age_seconds = self.snapshot_max_age_seconds

        class Handler(BaseHTTPRequestHandler):
            def setup(self) -> None:
                super().setup()
                self.connection.settimeout(5)

            def _authorized(self) -> bool:
                if bearer_token is None:
                    return True
                authorization = self.headers.get("Authorization", "")
                scheme, _, supplied_token = authorization.partition(" ")
                return scheme.lower() == "bearer" and hmac.compare_digest(
                    supplied_token, bearer_token
                )

            def _require_authorization(self) -> bool:
                if self._authorized():
                    return True
                self.send_response(HTTPStatus.UNAUTHORIZED)
                self.send_header("WWW-Authenticate", "Bearer")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return False

            def do_GET(self) -> None:
                if self.path == "/health":
                    healthy = store.snapshot()["bridge"]["healthy"]
                    body = json.dumps({"healthy": healthy}).encode()
                    self.send_response(
                        HTTPStatus.OK if healthy else HTTPStatus.SERVICE_UNAVAILABLE
                    )
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return

                if self.path not in {"/state", "/snapshot.jpg"}:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                if not self._require_authorization():
                    return

                if self.path == "/state":
                    body = store.to_json_bytes()
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                else:
                    if store.snapshot_is_stale(snapshot_max_age_seconds):
                        self.send_error(
                            HTTPStatus.SERVICE_UNAVAILABLE, "snapshot is stale"
                        )
                        return
                    body = store.snapshot_jpeg(snapshot_max_age_seconds)
                    if body is None:
                        self.send_error(HTTPStatus.NOT_FOUND)
                        return
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return

            def do_POST(self) -> None:
                if self.path != "/command":
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                if bearer_token is None or command_handler is None:
                    self.send_error(HTTPStatus.SERVICE_UNAVAILABLE)
                    return
                if not self._require_authorization():
                    return

                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    self.send_error(HTTPStatus.BAD_REQUEST, "invalid Content-Length")
                    return
                if length <= 0 or length > 4096:
                    self.send_error(HTTPStatus.BAD_REQUEST, "invalid request body")
                    return

                try:
                    request_body = self.rfile.read(length)
                    payload = json.loads(request_body)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    self.send_error(HTTPStatus.BAD_REQUEST, "invalid JSON")
                    return
                if not isinstance(payload, dict):
                    self.send_error(HTTPStatus.BAD_REQUEST, "request must be an object")
                    return

                try:
                    response = command_handler(payload)
                except CommandError as exc:
                    self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                    return
                except CommandUnavailable as exc:
                    self.send_error(HTTPStatus.SERVICE_UNAVAILABLE, str(exc))
                    return

                log.info("Accepted bridge command %s (queued)", payload["command"])
                body = json.dumps(response, sort_keys=True).encode()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return None

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="cradlewise-status-http",
            daemon=True,
        )
        self._thread.start()

    def close(self) -> None:
        if self._httpd is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread:
            self._thread.join(timeout=5)
        self._httpd = None
        self._thread = None
