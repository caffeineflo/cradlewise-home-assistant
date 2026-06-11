"""Bridge status state and HTTP exposure."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

SLEEP_PHASE_MAP = {
    0: "away",
    1: "awake",
    2: "stirring",
    4: "sleep",
}

DEVICE_STATE_KEYS = {
    "actuator",
    "babyNeedsAttention",
    "babyNeedsHelp",
    "babyPresent",
    "babySleepPhase",
    "babySleepPhaseV2",
    "babySleepState",
    "bounceMode",
    "bounceSetting",
    "deviceStatus",
    "insideSleepSchedule",
    "insideSoothingWindow",
    "isCribHelping",
    "light",
    "loudSoundDetected",
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
    "bounce_setting",
    "responsivity_setting",
    "soundSynth",
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


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
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


def _device_state_snapshot(payload: dict[str, Any] | None) -> dict[str, Any]:
    state = _device_state_payload(payload)
    light_intensity = _int_or_none(
        _first_value(
            state,
            ("light", "lightIntensity"),
            ("rawShadow", "light", "lightIntensity"),
            ("rawShadow", "light", "indicatorBrightness"),
        )
    )
    return {
        "raw": state,
        "baby_present": _first_value(
            state,
            ("babyPresent",),
            ("baby_present",),
            ("rawShadow", "babyPresent"),
        ),
        "sleep_state": _first_value(
            state,
            ("babySleepState",),
            ("baby_sleep_state",),
            ("rawShadow", "babySleepState"),
        ),
        "sleep_phase": _sleep_phase_name(state),
        "baby_needs_attention": _first_value(
            state, ("babyNeedsAttention",), ("rawShadow", "babyNeedsAttention")
        ),
        "baby_needs_help": _first_value(
            state, ("babyNeedsHelp",), ("rawShadow", "babyNeedsHelp")
        ),
        "crib_helping": _first_value(
            state, ("isCribHelping",), ("rawShadow", "isCribHelping")
        ),
        "loud_sound_detected": _first_value(
            state, ("loudSoundDetected",), ("rawShadow", "loudSoundDetected")
        ),
        "inside_sleep_schedule": _first_value(
            state, ("insideSleepSchedule",), ("rawShadow", "insideSleepSchedule")
        ),
        "inside_soothing_window": _first_value(
            state, ("insideSoothingWindow",), ("rawShadow", "insideSoothingWindow")
        ),
        "rocking_not_effective": _first_value(
            state, ("rockingNotEffective",), ("rawShadow", "rockingNotEffective")
        ),
        "cradle_mode": _first_value(
            state,
            ("mode",),
            ("detectedCradleMode",),
            ("userSetCradleMode",),
            ("rawShadow", "detectedCradleMode"),
            ("rawShadow", "userSetCradleMode"),
        ),
        "bounce_mode": _first_value(
            state, ("bounceMode",), ("rawShadow", "bounceMode")
        ),
        "bounce_setting": _first_value(
            state, ("bounceSetting",), ("bounce_setting",), ("rawShadow", "bounceSetting")
        ),
        "bounce_amplitude": _int_or_none(
            _first_value(state, ("actuator", "amplitude"), ("rawShadow", "actuator", "amplitude"))
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
        "music_mood": _first_value(
            state,
            ("music", "mood"),
            ("soundSynth", "trackName"),
            ("rawShadow", "soundSynth", "trackName"),
        ),
        "light_on": _first_value(
            state, ("light", "lightOn"), ("rawShadow", "light", "lightOn")
        ),
        "light_intensity": light_intensity,
        "battery_life": _int_or_none(
            _first_value(
                state,
                ("deviceStatus", "batteryLife"),
                ("rawShadow", "deviceStatus", "batteryLife"),
            )
        ),
        "charging": _first_value(
            state, ("deviceStatus", "charging"), ("rawShadow", "deviceStatus", "charging")
        ),
        "power_supply_removed": _first_value(
            state,
            ("deviceStatus", "supplyRemoved"),
            ("rawShadow", "deviceStatus", "supplyRemoved"),
        ),
        "sleep_time": _first_value(state, ("sleepTime",), ("rawShadow", "sleepTime")),
        "wake_up_time": _first_value(state, ("wakeUpTime",), ("rawShadow", "wakeUpTime")),
    }


@dataclass
class BridgeStatusStore:
    """Thread-safe bridge status snapshot."""

    cradle_id: str
    crib_ip: str
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
    _last_cradle_state_at: float | None = None
    _last_device_state_at: float | None = None
    _last_device_state_source: str | None = None
    _last_beacon_at: float | None = None
    _cradle_state: dict[str, Any] | None = None
    _device_state: dict[str, Any] | None = None
    _beacon: dict[str, Any] | None = None

    def set_mqtt_connected(self, connected: bool) -> None:
        with self._lock:
            self._mqtt_connected = connected

    def mark_mqtt_message(self) -> None:
        with self._lock:
            self._last_mqtt_message_at = _now()

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

    def mark_audio_track(self) -> None:
        with self._lock:
            self._audio_track = True

    def increment_audio_frames(self) -> None:
        with self._lock:
            self._audio_frames += 1
            self._last_audio_frame_at = _now()

    def update_cradle_state(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._cradle_state = payload
            self._last_cradle_state_at = _now()
            if _device_state_payload(payload) is not None:
                self._device_state = payload
                self._last_device_state_at = self._last_cradle_state_at
                self._last_device_state_source = "local_mqtt"

    def update_device_state(self, payload: dict[str, Any], source: str) -> None:
        with self._lock:
            self._device_state = payload
            self._last_device_state_at = _now()
            self._last_device_state_source = source

    def update_beacon(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._beacon = payload
            self._last_beacon_at = _now()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            cradle_state = self._cradle_state
            device_state = self._device_state
            beacon = self._beacon
            resolution = None
            if self._video_width and self._video_height:
                resolution = f"{self._video_width}x{self._video_height}"

            recent_video = (
                self._last_video_frame_at is not None
                and _now() - self._last_video_frame_at < 30
            )
            healthy = self._mqtt_connected and self._video_frames > 0 and recent_video
            return {
                "bridge": {
                    "cradle_id": self.cradle_id,
                    "crib_ip": self.crib_ip,
                    "healthy": healthy,
                    "uptime_seconds": int(_now() - self.started_at),
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
                    "wifi_ssid": _nested(
                        cradle_state, "info", "connectivity", "ssid"
                    ),
                    "wifi_strength": _nested(
                        cradle_state, "info", "connectivity", "strength"
                    ),
                    "wifi_frequency": _nested(
                        cradle_state, "info", "connectivity", "frequency"
                    ),
                    "local_ip": _nested(
                        cradle_state, "info", "connectivity", "localIP"
                    ),
                },
                "beacon": {
                    "raw": beacon,
                    "updated_at": self._last_beacon_at,
                },
                "device_state": {
                    **_device_state_snapshot(device_state or cradle_state),
                    "updated_at": self._last_device_state_at,
                    "source": self._last_device_state_source,
                },
            }

    def to_json_bytes(self) -> bytes:
        return json.dumps(self.snapshot(), sort_keys=True).encode()


class BridgeStatusHttpServer:
    """Small stdlib HTTP server for bridge status snapshots."""

    def __init__(self, store: BridgeStatusStore, host: str, port: int) -> None:
        self.store = store
        self.host = host
        self.port = port
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._httpd is not None:
            return
        store = self.store

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path == "/health":
                    body = json.dumps({"healthy": store.snapshot()["bridge"]["healthy"]})
                elif self.path == "/state":
                    body = store.to_json_bytes()
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                else:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return

                encoded = body.encode()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, format: str, *args: object) -> None:
                return None

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
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
