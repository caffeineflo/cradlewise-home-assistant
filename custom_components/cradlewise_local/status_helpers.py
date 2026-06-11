"""Pure helpers for bridge status data."""

from __future__ import annotations

from typing import Any


def build_state_url(value: str) -> str:
    """Return the bridge `/state` URL for a user-entered status URL."""
    stripped = value.rstrip("/")
    if stripped.endswith("/state"):
        return stripped
    return f"{stripped}/state"


def path_value(payload: dict[str, Any] | None, path: tuple[str, ...]) -> Any:
    """Read a nested value from a bridge status payload."""
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value
