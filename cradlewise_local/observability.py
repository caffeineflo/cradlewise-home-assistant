"""Opt-in bridge observability without consumer-identifying telemetry."""

from __future__ import annotations

import importlib
import math
import re
import time
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Protocol

BRIDGE_API_VERSION = 1

try:
    BRIDGE_VERSION = version("cradlewise-local")
except PackageNotFoundError:
    BRIDGE_VERSION = "unknown"

_EMAIL_PATTERN = re.compile(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b")
_IPV4_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_URL_PATTERN = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s]+", re.I)
_UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.I,
)
_SENSITIVE_EVENT_KEYS = {
    "breadcrumbs",
    "headers",
    "request",
    "server_name",
    "user",
}


def _metric_value(value: Any) -> str | None:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and math.isfinite(value):
        return str(value)
    return None


def _age_seconds(timestamp: Any, now: float) -> float | None:
    if not isinstance(timestamp, int | float) or isinstance(timestamp, bool):
        return None
    return max(0.0, now - float(timestamp))


def _process_thread_count() -> int | None:
    try:
        return sum(1 for _entry in Path("/proc/self/task").iterdir())
    except OSError:
        return None


def _cgroup_pid_count() -> int | None:
    try:
        return int(Path("/sys/fs/cgroup/pids.current").read_text().strip())
    except (OSError, ValueError):
        return None


def render_prometheus_metrics(
    snapshot: dict[str, Any],
    *,
    now: float | None = None,
) -> bytes:
    """Render a label-free Prometheus payload containing operational data only."""
    current_time = time.time() if now is None else now
    bridge = snapshot.get("bridge", {})
    mqtt = snapshot.get("mqtt", {})
    webrtc = snapshot.get("webrtc", {})
    media = snapshot.get("media", {})
    sink = snapshot.get("sink", {})
    device_state = snapshot.get("device_state", {})
    analytics = snapshot.get("analytics", {})
    metrics = (
        (
            "cradlewise_bridge_healthy",
            "gauge",
            "Whether the bridge media path is healthy.",
            bridge.get("healthy"),
        ),
        (
            "cradlewise_bridge_uptime_seconds",
            "gauge",
            "Bridge process uptime in seconds.",
            bridge.get("uptime_seconds"),
        ),
        (
            "cradlewise_bridge_reconnect_attempts_total",
            "counter",
            "Local bridge reconnect attempts since process start.",
            bridge.get("reconnect_attempts"),
        ),
        (
            "cradlewise_bridge_process_threads",
            "gauge",
            "Native threads in the bridge process.",
            _process_thread_count(),
        ),
        (
            "cradlewise_bridge_cgroup_pids",
            "gauge",
            "Processes and threads in the bridge container cgroup.",
            _cgroup_pid_count(),
        ),
        (
            "cradlewise_bridge_mqtt_connected",
            "gauge",
            "Whether local MQTT is connected.",
            mqtt.get("connected"),
        ),
        (
            "cradlewise_bridge_webrtc_connected",
            "gauge",
            "Whether the WebRTC peer connection is connected.",
            webrtc.get("connection_state") == "connected",
        ),
        (
            "cradlewise_bridge_ice_connected",
            "gauge",
            "Whether the ICE connection is connected or completed.",
            webrtc.get("ice_connection_state") in {"connected", "completed"},
        ),
        (
            "cradlewise_bridge_video_frames_current_connection",
            "gauge",
            "Video frames received during the current connection attempt.",
            media.get("video_frames"),
        ),
        (
            "cradlewise_bridge_audio_frames_current_connection",
            "gauge",
            "Audio frames received during the current connection attempt.",
            media.get("audio_frames"),
        ),
        (
            "cradlewise_bridge_last_video_frame_age_seconds",
            "gauge",
            "Age of the most recently received video frame.",
            _age_seconds(media.get("last_video_frame_at"), current_time),
        ),
        (
            "cradlewise_bridge_last_audio_frame_age_seconds",
            "gauge",
            "Age of the most recently received audio frame.",
            _age_seconds(media.get("last_audio_frame_at"), current_time),
        ),
        (
            "cradlewise_bridge_sink_healthy",
            "gauge",
            "Whether the RTSP sink is healthy and receiving fresh video.",
            sink.get("healthy"),
        ),
        (
            "cradlewise_bridge_sink_dropped_video_frames_current_connection",
            "gauge",
            "Video frames dropped by the RTSP sink.",
            sink.get("dropped_video_frames"),
        ),
        (
            "cradlewise_bridge_device_state_available",
            "gauge",
            "Whether normalized device state is fresh.",
            device_state.get("available"),
        ),
        (
            "cradlewise_bridge_device_state_age_seconds",
            "gauge",
            "Age of the selected normalized device state.",
            device_state.get("age_seconds"),
        ),
        (
            "cradlewise_bridge_analytics_available",
            "gauge",
            "Whether optional sleep analytics are fresh.",
            analytics.get("available"),
        ),
        (
            "cradlewise_bridge_analytics_age_seconds",
            "gauge",
            "Age of optional sleep analytics.",
            analytics.get("age_seconds"),
        ),
    )
    lines = []
    for name, metric_type, help_text, value in metrics:
        rendered_value = _metric_value(value)
        if rendered_value is None:
            continue
        lines.extend(
            (
                f"# HELP {name} {help_text}",
                f"# TYPE {name} {metric_type}",
                f"{name} {rendered_value}",
            )
        )
    return ("\n".join(lines) + "\n").encode()


def _redact_string(value: str) -> str:
    value = _URL_PATTERN.sub("[redacted-url]", value)
    value = _EMAIL_PATTERN.sub("[redacted-email]", value)
    value = _IPV4_PATTERN.sub("[redacted-ip]", value)
    return _UUID_PATTERN.sub("[redacted-id]", value)


def _redact_event_value(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, list):
        return [_redact_event_value(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _redact_event_value(item)
            for key, item in value.items()
            if str(key).lower() not in _SENSITIVE_EVENT_KEYS
        }
    return value


def _before_send(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    return _redact_event_value(event)


class ErrorReporter(Protocol):
    """Small reporting boundary used by the process entry point."""

    enabled: bool

    def capture_exception(self, exc: BaseException) -> None:
        """Capture one unexpected fatal exception."""

    def flush(self) -> None:
        """Flush pending events before process exit."""


@dataclass(frozen=True)
class DisabledErrorReporter:
    """No-op reporter used unless a consumer explicitly configures a DSN."""

    enabled: bool = False

    def capture_exception(self, exc: BaseException) -> None:
        return None

    def flush(self) -> None:
        return None


@dataclass(frozen=True)
class SentryErrorReporter:
    """Thin wrapper around a consumer-selected Sentry-compatible destination."""

    sdk: Any
    enabled: bool = True

    def capture_exception(self, exc: BaseException) -> None:
        self.sdk.capture_exception(exc)

    def flush(self) -> None:
        self.sdk.flush(timeout=2.0)


def _load_sentry_sdk() -> Any:
    return importlib.import_module("sentry_sdk")


def initialize_error_reporting(
    dsn: str | None,
    environment: str,
) -> ErrorReporter:
    """Initialize explicit, exception-only Sentry-compatible reporting."""
    if not dsn:
        return DisabledErrorReporter()
    try:
        sdk = _load_sentry_sdk()
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "error reporting requires the cradlewise-local observability extra"
        ) from exc

    sdk.init(
        dsn=dsn,
        environment=environment,
        release=f"cradlewise-local@{BRIDGE_VERSION}",
        send_default_pii=False,
        traces_sample_rate=0.0,
        profiles_sample_rate=0.0,
        include_local_variables=False,
        include_source_context=False,
        max_breadcrumbs=0,
        server_name="cradlewise-bridge",
        default_integrations=False,
        auto_enabling_integrations=False,
        before_send=_before_send,
    )
    return SentryErrorReporter(sdk)
