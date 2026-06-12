"""Pure helpers for bridge status data."""

from __future__ import annotations

from typing import Any


def build_state_url(value: str) -> str:
    """Return the bridge `/state` URL for a user-entered status URL."""
    stripped = value.rstrip("/")
    if stripped.endswith("/state"):
        return stripped
    return f"{stripped}/state"


def build_command_url(value: str) -> str:
    """Return the bridge `/command` URL for a user-entered status URL."""
    stripped = value.rstrip("/")
    if stripped.endswith("/state"):
        return f"{stripped[: -len('/state')]}/command"
    if stripped.endswith("/command"):
        return stripped
    return f"{stripped}/command"


def path_value(payload: dict[str, Any] | None, path: tuple[str, ...]) -> Any:
    """Read a nested value from a bridge status payload."""
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value
