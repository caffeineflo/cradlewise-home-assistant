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

VOLUME_PROFILES = {"gentle", "normal", "max"}
CRY_SENSITIVITY_VALUES = {0, 1, 2, 4, 6}


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


def _mode(value: Any) -> int:
    if value in ("auto", "Auto", 0):
        return 0
    if value in ("manual", "Manual", 1):
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
        return {"actuator": {"duration": _int_between(value, 0, 1440)}}
    if command == "bounce_setting":
        return {"bounceSetting": _int_between(value, 0, 10)}
    if command == "responsivity_setting":
        return {"responsivitySetting": _int_between(value, 0, 10)}
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
        return {"music": {"play": _bool(value)}}
    if command == "music_mode":
        return {"musicMode": _mode(value)}
    if command == "music_volume":
        return {"music": {"volume": _int_between(value, 0, 100)}}
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
        return {"keepBounceOnDuringSleepLevel": _int_between(value, 0, 5)}
    if command == "auto_mode_lock_on":
        return {"autoModeLockOn": _bool(value)}
    if command == "auto_mode_lock_duration":
        return {"autoModeLockDuration": _int_between(value, 0, 1440)}
    if command == "music_duration":
        return {"musicDuration": _int_between(value, 0, 1440)}
    if command == "max_bounce_limit":
        return {"maxBounceLimit": _int_between(value, 0, 100)}
    if command == "max_volume_limit":
        return {"maxVolumeLimit": _int_between(value, 0, 100)}
    if command == "start_recipe_enabled":
        return {"startRecipeEnabled": _bool(value)}
    if command == "start_recipe_music_level":
        return {"startRecipeMusicLevel": _int_between(value, 0, 5)}
    if command == "start_recipe_bounce_level":
        return {"startRecipeBounceLevel": _int_between(value, 0, 5)}
    if command == "start_recipe_lock_duration":
        return {"startRecipeLockDuration": _int_between(value, 0, 1440)}
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

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._publisher: PublishDesired | None = None

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
        desired = build_desired(command, payload.get("value"))

        with self._lock:
            publisher = self._publisher
        if publisher is None:
            raise CommandUnavailable("MQTT publisher is not ready")

        try:
            publisher(shadow_payload(desired))
        except RuntimeError as exc:
            raise CommandUnavailable(str(exc)) from exc
        return {"ok": True, "command": command, "desired": desired}
