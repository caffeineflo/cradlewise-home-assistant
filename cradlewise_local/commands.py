"""Validated Cradlewise desired-state commands."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any


class CommandError(ValueError):
    """Raised when a requested command is not valid."""


class CommandUnavailable(RuntimeError):
    """Raised when the bridge cannot currently publish commands."""


PublishDesired = Callable[[dict[str, Any]], dict[str, Any]]
StateProvider = Callable[[], dict[str, Any]]

VOLUME_PROFILES = {"gentle", "normal", "max"}
CRY_SENSITIVITY_VALUES = {0, 1, 2, 4, 6}
MUSIC_DURATION_VALUES = {-1, 60, 180}
RESPONSIVITY_VALUES = {2, 4, 6, 8, 10}
START_RECIPE_LOCK_DURATION_VALUES = {10, 20, 30}


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raise CommandError("value must be a boolean")


def _int_between(value: Any, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CommandError("value must be an integer")
    if value < minimum or value > maximum:
        raise CommandError(f"value must be between {minimum} and {maximum}")
    return value


def _int_one_of(value: Any, allowed: set[int]) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CommandError("value must be an integer")
    if value not in allowed:
        choices = ", ".join(str(choice) for choice in sorted(allowed))
        raise CommandError(f"value must be one of {choices}")
    return value


def _mode(value: Any) -> int:
    if isinstance(value, bool):
        raise CommandError("value must be auto/manual or 0/1")
    if isinstance(value, str):
        value = value.strip().lower()
    if value in ("auto", 0):
        return 0
    if value in ("manual", 1):
        return 1
    raise CommandError("value must be auto/manual or 0/1")


def _profile(value: Any) -> str:
    if not isinstance(value, str):
        raise CommandError("value must be a string")
    normalized = value.strip().lower()
    if normalized not in VOLUME_PROFILES:
        raise CommandError("value must be gentle, normal, or max")
    return normalized


def _cry_sensitivity(value: Any) -> int:
    raw = _int_between(value, 0, 6)
    if raw not in CRY_SENSITIVITY_VALUES:
        raise CommandError("value must be one of 0, 1, 2, 4, or 6")
    return raw


def build_desired(command: str, value: Any) -> dict[str, Any]:
    """Build an Android-app-compatible desired shadow fragment."""
    if command == "actuator_on":
        return {"actuator": {"on": _bool(value)}}
    if command == "bounce_mode":
        return {"bounceMode": _mode(value)}
    if command == "bounce_amplitude":
        return {"actuator": {"amplitude": _int_between(value, 0, 100)}}
    if command == "bounce_duration":
        return {"actuator": {"duration": _int_between(value, 1, 60)}}
    if command == "bounce_setting":
        return {"bounceSetting": _int_between(value, 0, 10)}
    if command == "responsivity_setting":
        return {"responsivitySetting": _int_one_of(value, RESPONSIVITY_VALUES)}
    if command == "disable_bounce":
        return {"actuator": {"disableBouncing": _bool(value)}}
    if command == "super_gentle_bounce":
        return {"actuator": {"bounceSuperGentle": _bool(value)}}
    if command == "always_on_bounce":
        return {"actuator": {"bounceAlwaysOn": _bool(value)}}
    if command == "always_on_bounce_intensity":
        return {"actuator": {"bounceAlwaysOnIntensity": _int_between(value, 0, 100)}}
    if command == "tap_detection_enabled":
        return {"actuator": {"tapDetectionEnable": _bool(value)}}
    if command == "push_gesture_enabled":
        return {"actuator": {"pushGestureEnable": _bool(value)}}
    if command == "bounce_level":
        return {"bounceLevel": _int_between(value, 0, 5)}
    if command == "music_playing":
        return {"soundSynth": {"play": _bool(value)}}
    if command == "music_mode":
        return {"musicMode": _mode(value)}
    if command == "music_volume":
        return {"soundSynth": {"volume": _int_between(value, 0, 100)}}
    if command == "music_level":
        return {"musicLevel": _int_between(value, 0, 5)}
    if command == "volume_profile":
        return {"volumeProfile": _profile(value)}
    if command == "light_indicator_brightness":
        return {"light": {"indicatorBrightness": _int_between(value, 0, 100)}}
    if command == "light_indicator_mode":
        return {"light": {"indicatorBrightnessMode": _mode(value)}}
    if command == "keep_music_on_during_sleep":
        return {"keepMusicOnDuringSleep": _bool(value)}
    if command == "keep_music_on_during_sleep_level":
        return {"keepMusicOnDuringSleepLevel": _int_between(value, 0, 5)}
    if command == "keep_bounce_on_during_sleep":
        return {"keepBounceOnDuringSleep": _bool(value)}
    if command == "keep_bounce_on_during_sleep_level":
        return {"keepBounceOnDuringSleepLevel": _int_one_of(value, {0, 1})}
    if command == "auto_mode_lock_on":
        return {"autoModeLockOn": _bool(value)}
    if command == "auto_mode_lock_duration":
        return {"autoModeLockDuration": _int_between(value, 1, 60)}
    if command == "music_duration":
        return {"musicDuration": _int_one_of(value, MUSIC_DURATION_VALUES)}
    if command == "max_bounce_limit":
        return {"maxBounceLimit": _int_between(value, 0, 100)}
    if command == "max_volume_limit":
        return {"maxVolumeLimit": _int_between(value, 0, 100)}
    if command == "start_recipe_enabled":
        return {"startRecipeEnabled": _bool(value)}
    if command == "start_recipe_music_level":
        return {"startRecipeMusicLevel": _int_between(value, -1, 4)}
    if command == "start_recipe_bounce_level":
        return {"startRecipeBounceLevel": _int_between(value, -1, 4)}
    if command == "start_recipe_lock_duration":
        return {
            "startRecipeLockDuration": _int_one_of(
                value, START_RECIPE_LOCK_DURATION_VALUES
            )
        }
    if command == "adaptive_soothing_enabled":
        return {"control": {"adaptiveSoothingEnabled": _bool(value)}}
    if command == "cry_sensitivity":
        return {"control": {"crySensitivity": _cry_sensitivity(value)}}

    raise CommandError(f"unsupported command: {command}")


def shadow_payload(desired: dict[str, Any]) -> dict[str, Any]:
    """Wrap a desired fragment the same way the Android app does."""
    return {"state": {"desired": desired}}


class BridgeCommandHandler:
    """Thread-safe HTTP command adapter around the active MQTT publisher."""

    def __init__(self, state_provider: StateProvider | None = None) -> None:
        self._lock = threading.Lock()
        self._publisher: PublishDesired | None = None
        self._state_provider = state_provider

    def set_publisher(self, publisher: PublishDesired) -> None:
        with self._lock:
            self._publisher = publisher

    def clear_publisher(self) -> None:
        with self._lock:
            self._publisher = None

    def handle_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        command = payload.get("command")
        if not isinstance(command, str) or not command:
            raise CommandError("command must be a non-empty string")
        value = payload.get("value")
        desired = build_desired(command, value)
        state = self._current_device_state()
        self._validate_live_limit(command, value, state)
        desired = self._build_runtime_desired(command, value, desired, state)

        with self._lock:
            publisher = self._publisher
        if publisher is None:
            raise CommandUnavailable("MQTT publisher is not ready")

        try:
            publisher(shadow_payload(desired))
        except RuntimeError as exc:
            raise CommandUnavailable(str(exc)) from exc
        return {
            "ok": True,
            "status": "queued",
            "command": command,
            "desired": desired,
        }

    def _current_device_state(self) -> dict[str, Any] | None:
        if self._state_provider is None:
            return None
        state = self._state_provider().get("device_state")
        return state if isinstance(state, dict) else None

    def _validate_live_limit(
        self, command: str, value: Any, state: dict[str, Any] | None
    ) -> None:
        if state is None or isinstance(value, bool):
            return
        limits = {
            "bounce_amplitude": ("max_bounce_limit", "bounce amplitude"),
            "bounce_duration": ("bounce_duration_limit", "bounce duration"),
            "music_volume": ("max_volume_limit", "music volume"),
        }
        limit_spec = limits.get(command)
        if limit_spec is None:
            return
        limit_key, label = limit_spec
        limit = state.get(limit_key)
        if not isinstance(limit, int):
            raise CommandUnavailable(f"{label} limit is not available yet")
        if isinstance(value, int) and value > limit:
            raise CommandError(f"{label} must not exceed the device limit of {limit}")

    @staticmethod
    def _build_runtime_desired(
        command: str,
        value: Any,
        desired: dict[str, Any],
        state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if state is None or command not in {"music_playing", "music_volume"}:
            return desired

        sound_synth = {
            "play": value if command == "music_playing" else state.get("music_playing"),
            "ambience": state.get("sound_ambience_raw"),
            "color": state.get("sound_color_raw"),
            "heartbeatVolume": state.get("sound_heartbeat_volume"),
            "breathVolume": state.get("sound_breath_volume"),
            "volume": value if command == "music_volume" else state.get("music_volume"),
            "trackName": state.get("music_mood"),
        }
        if any(field_value is None for field_value in sound_synth.values()):
            raise CommandUnavailable("sound synthesizer state is not available yet")
        if not isinstance(sound_synth["play"], bool):
            raise CommandUnavailable("sound synthesizer play state is invalid")
        if sound_synth["ambience"] not in {0, 1, 2, 3}:
            raise CommandUnavailable("sound synthesizer ambience state is invalid")
        if sound_synth["color"] not in {0, 1, 2}:
            raise CommandUnavailable("sound synthesizer color state is invalid")
        for field_name in ("heartbeatVolume", "breathVolume", "volume"):
            field_value = sound_synth[field_name]
            if (
                isinstance(field_value, bool)
                or not isinstance(field_value, int)
                or not 0 <= field_value <= 100
            ):
                raise CommandUnavailable(
                    f"sound synthesizer {field_name} state is invalid"
                )
        if not isinstance(sound_synth["trackName"], str):
            raise CommandUnavailable("sound synthesizer track state is invalid")
        return {"soundSynth": sound_synth}
