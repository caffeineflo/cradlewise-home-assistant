"""Privacy-safe diagnostics for Cradlewise."""

from __future__ import annotations

import math
import re
from typing import Any

from homeassistant.core import HomeAssistant

from . import CradlewiseConfigEntry
from .const import (
    CONF_BRIDGE_API_VERSION,
    CONF_BRIDGE_STATUS_URL,
    CONF_BRIDGE_VERSION,
    CONF_CONNECTION_MODE,
    CONNECTION_MODES,
)
from .status_helpers import path_value, strict_bool


def _number(value: Any) -> int | float | None:
    """Export only finite operational counters and timestamps."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value if value >= 0 else None


def _choice(value: Any, choices: set[str]) -> str | None:
    return value if isinstance(value, str) and value in choices else None


def _version(value: Any) -> str | None:
    """Do not copy arbitrary device/config text into diagnostic exports."""
    if isinstance(value, str) and re.fullmatch(r"\d+(?:\.\d+){1,3}", value):
        return value
    return None


def _provider_diagnostics(data: dict[str, Any] | None) -> dict[str, Any]:
    sources = path_value(data, ("providers", "sources"))
    if not isinstance(sources, dict):
        return {}
    diagnostics = {}
    for source in ("local", "cloud"):
        metadata = sources.get(source)
        if not isinstance(metadata, dict):
            continue
        diagnostics[source] = {
            "connected": strict_bool(metadata.get("connected")),
            "updated_at": _number(metadata.get("updated_at")),
            "age_seconds": _number(metadata.get("age_seconds")),
            "stale": strict_bool(metadata.get("stale")),
        }
        diagnostics[source]["has_error"] = bool(metadata.get("error"))
    return diagnostics


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: CradlewiseConfigEntry,
) -> dict[str, Any]:
    """Return useful status without raw nursery state or credentials."""
    runtime_data = getattr(entry, "runtime_data", None)
    coordinator = runtime_data.coordinator if runtime_data is not None else None
    data = coordinator.data if coordinator is not None else None
    config = {**entry.data, **entry.options}
    return {
        "config_entry": {
            CONF_CONNECTION_MODE: _choice(
                config.get(CONF_CONNECTION_MODE), CONNECTION_MODES
            ),
        },
        "options": {
            "media_companion_configured": bool(config.get(CONF_BRIDGE_STATUS_URL))
        },
        "coordinator": {
            "loaded": coordinator is not None,
            "last_update_success": (
                coordinator.last_update_success if coordinator is not None else False
            ),
            "command_available": (
                coordinator.command_available if coordinator is not None else False
            ),
            "active_provider": _choice(
                path_value(data, ("providers", "active")), {"local", "cloud"}
            ),
            "providers": _provider_diagnostics(data),
        },
        "bridge": {
            "api_version": _number(config.get(CONF_BRIDGE_API_VERSION)),
            "version": _version(config.get(CONF_BRIDGE_VERSION)),
            "healthy": strict_bool(path_value(data, ("bridge", "healthy"))),
            "uptime_seconds": _number(path_value(data, ("bridge", "uptime_seconds"))),
            "reconnect_attempts": _number(
                path_value(data, ("bridge", "reconnect_attempts"))
            ),
            "mqtt_connected": strict_bool(path_value(data, ("mqtt", "connected"))),
            "webrtc_connection_state": _choice(
                path_value(data, ("webrtc", "connection_state")),
                {"new", "connecting", "connected", "disconnected", "failed", "closed"},
            ),
            "ice_connection_state": _choice(
                path_value(data, ("webrtc", "ice_connection_state")),
                {
                    "new",
                    "checking",
                    "connected",
                    "completed",
                    "disconnected",
                    "failed",
                    "closed",
                },
            ),
            "video_track": strict_bool(path_value(data, ("media", "video_track"))),
            "audio_track": strict_bool(path_value(data, ("media", "audio_track"))),
            "video_frames": _number(path_value(data, ("media", "video_frames"))),
            "audio_frames": _number(path_value(data, ("media", "audio_frames"))),
            "dropped_video_frames": _number(
                path_value(data, ("sink", "dropped_video_frames"))
            ),
        },
        "device_state": {
            "source": _choice(
                path_value(data, ("device_state", "source")), {"local", "cloud"}
            ),
            "updated_at": _number(path_value(data, ("device_state", "updated_at"))),
            "age_seconds": _number(path_value(data, ("device_state", "age_seconds"))),
            "software_version": _version(
                path_value(data, ("device_state", "software_version"))
            ),
        },
    }
