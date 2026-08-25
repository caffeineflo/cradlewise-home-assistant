"""Diagnostics support for the Cradlewise Local integration."""

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
    CONF_CRADLE_ID,
    CONF_SNAPSHOT_URL,
    CONF_STREAM_URL,
)
from .status_helpers import path_value

TO_REDACT = {
    CONF_BEARER_TOKEN,
    CONF_BRIDGE_STATUS_URL,
    CONF_CRADLE_ID,
    CONF_SNAPSHOT_URL,
    CONF_STREAM_URL,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: CradlewiseConfigEntry,
) -> dict[str, Any]:
    """Return useful status without raw nursery state or credentials."""
    coordinator = entry.runtime_data.coordinator
    data = coordinator.data if coordinator is not None else None
    return {
        "config_entry": async_redact_data(dict(entry.data), TO_REDACT),
        "coordinator": {
            "configured": coordinator is not None,
            "last_update_success": (
                coordinator.last_update_success if coordinator is not None else None
            ),
        },
        "bridge": {
            "api_version": entry.data.get(CONF_BRIDGE_API_VERSION),
            "version": entry.data.get(CONF_BRIDGE_VERSION),
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
            "update_available": path_value(data, ("device_state", "update_available")),
            "update_status": path_value(data, ("device_state", "update_status")),
            "update_version": path_value(data, ("device_state", "update_version")),
            "update_progress": path_value(data, ("device_state", "update_progress")),
        },
    }
