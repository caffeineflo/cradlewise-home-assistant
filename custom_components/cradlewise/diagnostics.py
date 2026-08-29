"""Privacy-safe diagnostics for Cradlewise."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import CradlewiseConfigEntry
from .const import (
    CONF_BEARER_TOKEN,
    CONF_BRIDGE_API_VERSION,
    CONF_BRIDGE_STATUS_URL,
    CONF_BRIDGE_VERSION,
    CONF_CLIENT_CERTIFICATE,
    CONF_CLIENT_PRIVATE_KEY,
    CONF_CRADLE_ID,
    CONF_DEVICE_ID,
    CONF_EMAIL,
    CONF_GROUP_CA_CERTIFICATE,
    CONF_PASSWORD,
    CONF_SERVER_CA_CERTIFICATE,
    CONF_SNAPSHOT_URL,
    CONF_STREAM_URL,
)
from .status_helpers import path_value

TO_REDACT = {
    CONF_BEARER_TOKEN,
    CONF_BRIDGE_STATUS_URL,
    CONF_CLIENT_CERTIFICATE,
    CONF_CLIENT_PRIVATE_KEY,
    CONF_CRADLE_ID,
    CONF_DEVICE_ID,
    CONF_EMAIL,
    CONF_GROUP_CA_CERTIFICATE,
    CONF_PASSWORD,
    CONF_SERVER_CA_CERTIFICATE,
    CONF_SNAPSHOT_URL,
    CONF_STREAM_URL,
}


def _provider_diagnostics(data: dict[str, Any] | None) -> dict[str, Any]:
    sources = path_value(data, ("providers", "sources"))
    if not isinstance(sources, dict):
        return {}
    diagnostics = {}
    for source, metadata in sources.items():
        if not isinstance(metadata, dict):
            continue
        diagnostics[source] = {
            key: metadata.get(key)
            for key in ("connected", "updated_at", "age_seconds", "stale")
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
        "config_entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": async_redact_data(dict(entry.options), TO_REDACT),
        "coordinator": {
            "loaded": coordinator is not None,
            "last_update_success": (
                coordinator.last_update_success if coordinator is not None else False
            ),
            "command_available": (
                coordinator.command_available if coordinator is not None else False
            ),
            "active_provider": path_value(data, ("providers", "active")),
            "providers": _provider_diagnostics(data),
        },
        "bridge": {
            "api_version": config.get(CONF_BRIDGE_API_VERSION),
            "version": config.get(CONF_BRIDGE_VERSION),
            "healthy": path_value(data, ("bridge", "healthy")),
            "uptime_seconds": path_value(data, ("bridge", "uptime_seconds")),
            "reconnect_attempts": path_value(data, ("bridge", "reconnect_attempts")),
            "mqtt_connected": path_value(data, ("mqtt", "connected")),
            "webrtc_connection_state": path_value(data, ("webrtc", "connection_state")),
            "ice_connection_state": path_value(
                data, ("webrtc", "ice_connection_state")
            ),
            "video_track": path_value(data, ("media", "video_track")),
            "audio_track": path_value(data, ("media", "audio_track")),
            "video_frames": path_value(data, ("media", "video_frames")),
            "audio_frames": path_value(data, ("media", "audio_frames")),
            "dropped_video_frames": path_value(data, ("sink", "dropped_video_frames")),
        },
        "device_state": {
            "source": path_value(data, ("device_state", "source")),
            "updated_at": path_value(data, ("device_state", "updated_at")),
            "age_seconds": path_value(data, ("device_state", "age_seconds")),
            "software_version": path_value(data, ("device_state", "software_version")),
        },
    }
