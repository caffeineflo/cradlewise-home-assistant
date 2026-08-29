"""State normalization and local-first provider arbitration."""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Any

SLEEP_PHASES = {
    0: "away",
    1: "awake",
    2: "stirring",
    3: "stirring",
    4: "sleep",
    5: "awake",
    6: "stirring",
}

SLEEP_STATES = {
    0: "Baby not present",
    2: "Active Awake",
    3: "Quite Awake",
    4: "Light sleep",
    5: "Deep sleep",
}

DEVICE_STATE_KEYS = {
    "actuator",
    "babyMonitor",
    "babyNeedsAttention",
    "babyNeedsHelp",
    "babyPresent",
    "babySleepPhase",
    "babySleepPhaseV2",
    "babySleepState",
    "bounceLevel",
    "control",
    "deviceStatus",
    "isCribHelping",
    "light",
    "loudSoundDetected",
    "maxBounceLimit",
    "maxVolumeLimit",
    "meta",
    "musicDuration",
    "musicLevel",
    "musicMode",
    "musicTimeRemaining",
    "obstructionToFDetected",
    "rawShadow",
    "rockingNotEffective",
    "soundSynth",
}


def _nested(payload: dict[str, Any] | None, *keys: str) -> Any:
    value: Any = payload
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _first(payload: dict[str, Any] | None, *paths: tuple[str, ...]) -> Any:
    for path in paths:
        value = _nested(payload, *path)
        if value is not None:
            return value
    return None


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in {"1", "true", "yes", "on"}:
            return True
        if cleaned in {"0", "false", "no", "off"}:
            return False
    return None


def _int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_reported_state(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """Extract an AWS shadow report or accept a direct cloud state object."""
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


def merge_state(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Apply an AWS shadow-style partial update without mutating either input."""
    merged = copy.deepcopy(base)
    for key, value in patch.items():
        if value is None:
            merged.pop(key, None)
        elif isinstance(value, dict):
            current = merged.get(key)
            nested_base = current if isinstance(current, dict) else {}
            merged[key] = merge_state(nested_base, value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _sleep_phase(state: dict[str, Any] | None) -> str | None:
    raw = _int(
        _first(
            state,
            ("babySleepPhaseV2", "eventValue"),
            ("rawShadow", "babySleepPhaseV2", "eventValue"),
            ("babySleepPhase",),
            ("rawShadow", "babySleepPhase"),
        )
    )
    return SLEEP_PHASES.get(raw, f"unknown ({raw})") if raw is not None else None


def _sleep_state(state: dict[str, Any] | None) -> str | None:
    value = _first(
        state,
        ("babySleepState",),
        ("baby_sleep_state",),
        ("rawShadow", "babySleepState"),
    )
    raw = _int(value)
    if raw is not None:
        return SLEEP_STATES.get(raw, f"unknown ({raw})")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _ambient_temperature(state: dict[str, Any] | None) -> float | None:
    value = _float(
        _first(
            state,
            ("ambientTempInCelsius",),
            ("rawShadow", "ambientTempInCelsius"),
        )
    )
    if value is not None:
        return value
    value = _float(
        _first(
            state,
            ("deviceStatus", "ambientTemp"),
            ("rawShadow", "deviceStatus", "ambientTemp"),
        )
    )
    if value is not None and abs(value) > 200:
        return value / 1000
    return value


def normalize_device_state(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize the stable state and control surface used by consumers."""
    state = extract_reported_state(payload)
    inactive = False if state is not None else None
    light_intensity = _int(
        _first(
            state,
            ("light", "lightIntensity"),
            ("rawShadow", "light", "lightIntensity"),
        )
    )
    result = {
        "baby_present": _bool(
            _first(state, ("babyPresent",), ("rawShadow", "babyPresent"))
        ),
        "baby_needs_attention": _bool(
            _first(
                state,
                ("babyNeedsAttention",),
                ("rawShadow", "babyNeedsAttention"),
            )
        ),
        "baby_needs_help": _bool(
            _first(state, ("babyNeedsHelp",), ("rawShadow", "babyNeedsHelp"))
        ),
        "crib_helping": _bool(
            _first(state, ("isCribHelping",), ("rawShadow", "isCribHelping"))
        ),
        "loud_sound_detected": _bool(
            _first(
                state,
                ("loudSoundDetected",),
                ("rawShadow", "loudSoundDetected"),
            )
        ),
        "rocking_not_effective": _bool(
            _first(
                state,
                ("rockingNotEffective",),
                ("rawShadow", "rockingNotEffective"),
            )
        ),
        "obstruction_detected": _bool(
            _first(
                state,
                ("obstructionToFDetected",),
                ("rawShadow", "obstructionToFDetected"),
            )
        ),
        "lower_breath_rate_alert": _bool(
            _first(
                state,
                ("babyMonitor", "lowerBreathRateAlert"),
                ("rawShadow", "babyMonitor", "lowerBreathRateAlert"),
            )
        ),
        "sleep_state": _sleep_state(state),
        "sleep_phase": _sleep_phase(state),
        "bouncing": _bool(
            _first(state, ("actuator", "on"), ("rawShadow", "actuator", "on"))
        ),
        "bounce_mode": _int(
            _first(state, ("bounceMode",), ("rawShadow", "bounceMode"))
        ),
        "bounce_level": _int(
            _first(state, ("bounceLevel",), ("rawShadow", "bounceLevel"))
        ),
        "bounce_amplitude": _int(
            _first(
                state,
                ("actuator", "amplitude"),
                ("rawShadow", "actuator", "amplitude"),
            )
        ),
        "bounce_duration": _int(
            _first(
                state,
                ("actuator", "duration"),
                ("rawShadow", "actuator", "duration"),
            )
        ),
        "bounce_duration_limit": _int(
            _first(
                state,
                ("actuator", "durationLimit"),
                ("rawShadow", "actuator", "durationLimit"),
            )
        ),
        "bounce_time_remaining": _int(
            _first(
                state,
                ("actuator", "timeRemaining"),
                ("rawShadow", "actuator", "timeRemaining"),
            )
        ),
        "music_playing": _bool(
            _first(
                state,
                ("music", "play"),
                ("soundSynth", "play"),
                ("rawShadow", "soundSynth", "play"),
            )
        ),
        "music_mode": _int(_first(state, ("musicMode",), ("rawShadow", "musicMode"))),
        "music_level": _int(
            _first(state, ("musicLevel",), ("rawShadow", "musicLevel"))
        ),
        "music_volume": _int(
            _first(
                state,
                ("music", "volume"),
                ("soundSynth", "volume"),
                ("rawShadow", "soundSynth", "volume"),
            )
        ),
        "music_mood": _first(
            state,
            ("music", "mood"),
            ("soundSynth", "trackName"),
            ("rawShadow", "soundSynth", "trackName"),
        ),
        "music_duration": _int(
            _first(state, ("musicDuration",), ("rawShadow", "musicDuration"))
        ),
        "music_time_remaining": _int(
            _first(
                state,
                ("musicTimeRemaining",),
                ("rawShadow", "musicTimeRemaining"),
            )
        ),
        "light_on": _bool(
            _first(state, ("light", "lightOn"), ("rawShadow", "light", "lightOn"))
        ),
        "ambient_temperature": _ambient_temperature(state),
        "breath_rate": _int(
            _first(
                state,
                ("babyMonitor", "breath", "rate"),
                ("rawShadow", "babyMonitor", "breath", "rate"),
            )
        ),
        "adaptive_soothing_enabled": _bool(
            _first(
                state,
                ("control", "adaptiveSoothingEnabled"),
                ("rawShadow", "control", "adaptiveSoothingEnabled"),
            )
        ),
        "sound_ambience_raw": _int(
            _first(
                state,
                ("soundSynth", "ambience"),
                ("rawShadow", "soundSynth", "ambience"),
            )
        ),
        "sound_color_raw": _int(
            _first(
                state,
                ("soundSynth", "color"),
                ("rawShadow", "soundSynth", "color"),
            )
        ),
        "sound_heartbeat_volume": _int(
            _first(
                state,
                ("soundSynth", "heartbeatVolume"),
                ("rawShadow", "soundSynth", "heartbeatVolume"),
            )
        ),
        "sound_breath_volume": _int(
            _first(
                state,
                ("soundSynth", "breathVolume"),
                ("rawShadow", "soundSynth", "breathVolume"),
            )
        ),
        "max_bounce_limit": _int(
            _first(state, ("maxBounceLimit",), ("rawShadow", "maxBounceLimit"))
        ),
        "max_volume_limit": _int(
            _first(state, ("maxVolumeLimit",), ("rawShadow", "maxVolumeLimit"))
        ),
        "software_version": _first(
            state,
            ("meta", "software_version"),
            ("rawShadow", "meta", "software_version"),
        ),
    }
    for key in (
        "baby_needs_attention",
        "baby_needs_help",
        "crib_helping",
        "loud_sound_detected",
        "rocking_not_effective",
    ):
        if result[key] is None:
            result[key] = inactive
    if result["light_on"] is None and light_intensity is not None:
        result["light_on"] = light_intensity > 0
    return result


@dataclass
class _ProviderState:
    raw: dict[str, Any] = field(default_factory=dict)
    normalized: dict[str, Any] = field(default_factory=dict)
    updated_at: float | None = None
    connected: bool = False
    error: str | None = None


@dataclass
class CradlewiseStateStore:
    """Merge provider updates into one local-first consumer snapshot."""

    cradle_id: str
    local_stale_after: int = 30
    cloud_stale_after: int = 90
    _providers: dict[str, _ProviderState] = field(default_factory=dict)
    _cradle_state: dict[str, Any] | None = None
    _cradle_state_updated_at: float | None = None

    def set_connected(self, source: str, connected: bool) -> None:
        """Record provider connectivity without discarding its last state."""
        self._provider(source).connected = connected

    def update_device_state(
        self,
        payload: dict[str, Any],
        source: str,
        *,
        updated_at: float | None = None,
    ) -> None:
        """Merge one full or partial state update for a provider."""
        state = extract_reported_state(payload)
        if state is None:
            return
        provider = self._provider(source)
        provider.raw = merge_state(provider.raw, state)
        provider.updated_at = time.time() if updated_at is None else updated_at
        provider.error = None

    def update_normalized_device_state(
        self,
        payload: dict[str, Any],
        source: str,
        *,
        updated_at: float | None = None,
    ) -> None:
        """Merge a normalized state update from a compatible bridge."""
        provider = self._provider(source)
        provider.normalized = merge_state(provider.normalized, payload)
        provider.updated_at = time.time() if updated_at is None else updated_at
        provider.error = None

    def update_cradle_state(
        self,
        payload: dict[str, Any],
        *,
        updated_at: float | None = None,
    ) -> None:
        """Store local connectivity state and any embedded device report."""
        timestamp = time.time() if updated_at is None else updated_at
        self._cradle_state = copy.deepcopy(payload)
        self._cradle_state_updated_at = timestamp
        if extract_reported_state(payload) is not None:
            self.update_device_state(payload, "local", updated_at=timestamp)

    def mark_error(self, source: str, error: str) -> None:
        """Record a provider error without discarding its last known values."""
        self._provider(source).error = error

    def snapshot(self, *, now: float | None = None) -> dict[str, Any]:
        """Return a canonical snapshot with local-first freshness semantics."""
        timestamp = time.time() if now is None else now
        metadata = {
            source: self._metadata(source, provider, timestamp)
            for source, provider in sorted(self._providers.items())
        }
        fresh = [
            source
            for source in ("cloud", "local")
            if source in self._providers
            and (self._providers[source].raw or self._providers[source].normalized)
            and not metadata[source]["stale"]
        ]
        selected = fresh or [
            source
            for source in ("cloud", "local")
            if source in self._providers
            and (self._providers[source].raw or self._providers[source].normalized)
        ]
        merged: dict[str, Any] = {}
        for source in selected:
            merged = merge_state(merged, self._providers[source].raw)
        active_source = selected[-1] if selected else None
        updated_at = (
            self._providers[active_source].updated_at if active_source else None
        )
        device_state = normalize_device_state(merged)
        for source in selected:
            device_state = merge_state(
                device_state,
                self._providers[source].normalized,
            )
        available = bool(fresh)
        cradle_state = copy.deepcopy(self._cradle_state)
        local_provider = self._providers.get("local")
        local_connected = local_provider.connected if local_provider else False
        any_connected = any(provider.connected for provider in self._providers.values())

        return {
            "bridge": {
                "cradle_id": self.cradle_id,
                "healthy": any_connected and available,
                "provider_healthy": any_connected and available,
            },
            "mqtt": {"connected": local_connected},
            "providers": {
                "active": active_source,
                "sources": metadata,
            },
            "cradle_state": {
                "raw": cradle_state,
                "updated_at": self._cradle_state_updated_at,
                "wifi_ssid": _first(
                    cradle_state,
                    ("info", "connectivity", "ssid"),
                    ("wifi_ssid",),
                ),
                "wifi_strength": _nested(
                    cradle_state, "info", "connectivity", "strength"
                )
                or _nested(cradle_state, "wifi_strength"),
                "local_ip": _first(
                    cradle_state,
                    ("info", "connectivity", "localIP"),
                    ("local_ip",),
                ),
            },
            "device_state": {
                **device_state,
                "updated_at": updated_at,
                "age_seconds": (
                    max(0.0, timestamp - updated_at) if updated_at is not None else None
                ),
                "source": active_source,
                "available": available,
                "stale": bool(selected) and not available,
                "sources": metadata,
            },
        }

    def _provider(self, source: str) -> _ProviderState:
        if source not in self._providers:
            self._providers[source] = _ProviderState()
        return self._providers[source]

    def _metadata(
        self,
        source: str,
        provider: _ProviderState,
        now: float,
    ) -> dict[str, Any]:
        updated_at = provider.updated_at
        timeout = (
            self.cloud_stale_after if source == "cloud" else self.local_stale_after
        )
        stale = updated_at is None or (
            not provider.connected and now - updated_at > timeout
        )
        return {
            "connected": provider.connected,
            "updated_at": updated_at,
            "age_seconds": (
                max(0.0, now - updated_at) if updated_at is not None else None
            ),
            "stale": stale,
            "error": provider.error,
        }
