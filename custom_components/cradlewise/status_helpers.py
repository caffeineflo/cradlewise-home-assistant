"""Shared validation helpers for Cradlewise entities."""

from __future__ import annotations

import time
from math import isfinite
from typing import Any

from .config_helpers import command_url_from_status_url, state_url_from_status_url


def build_state_url(value: str) -> str:
    """Return the bridge `/state` URL for a user-entered status URL."""
    return state_url_from_status_url(value)


def build_command_url(value: str) -> str:
    """Return the bridge `/command` URL for a user-entered status URL."""
    return command_url_from_status_url(value)


def path_value(payload: dict[str, Any] | None, path: tuple[str, ...]) -> Any:
    """Read a nested value from a bridge status payload."""
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def strict_bool(value: Any) -> bool | None:
    """Parse only explicit boolean representations."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return None


def bounded_number(
    value: Any,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    """Return a finite in-range number while rejecting booleans and sentinels."""
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(parsed):
        return None
    if minimum is not None and parsed < minimum:
        return None
    if maximum is not None and parsed > maximum:
        return None
    return parsed


def nonnegative_int(value: Any) -> int | None:
    """Return a nonnegative integer, mapping protocol sentinels to unknown."""
    parsed = bounded_number(value, minimum=0)
    if parsed is None or not parsed.is_integer():
        return None
    return int(parsed)


def positive_int(value: Any) -> int | None:
    """Return a positive integer, mapping zero and negative sentinels to unknown."""
    parsed = bounded_number(value, minimum=1)
    if parsed is None or not parsed.is_integer():
        return None
    return int(parsed)


def timestamp_is_fresh(
    payload: dict[str, Any] | None,
    paths: tuple[tuple[str, ...], ...],
    max_age_seconds: int,
    now: float | None = None,
) -> bool:
    """Return true when any supplied timestamp is recent enough."""
    current_time = time.time() if now is None else now
    for path in paths:
        timestamp = bounded_number(path_value(payload, path))
        if timestamp is None:
            continue
        age = current_time - timestamp
        if -60 <= age <= max_age_seconds:
            return True
    return False


def device_state_is_available(
    payload: dict[str, Any] | None,
    fallback_max_age_seconds: int,
    now: float | None = None,
) -> bool:
    """Trust bridge source availability, with timestamp fallback for old bridges."""
    available = strict_bool(path_value(payload, ("device_state", "available")))
    stale = strict_bool(path_value(payload, ("device_state", "stale")))
    if available is not None:
        return available and stale is not True
    if stale is not None:
        return not stale
    return timestamp_is_fresh(
        payload,
        (("device_state", "updated_at"),),
        fallback_max_age_seconds,
        now,
    )
