"""Pure helpers for Cradlewise config validation."""

from __future__ import annotations

from urllib.parse import urlparse


def is_rtsp_url(value: str) -> bool:
    """Return true when value is an RTSP URL with a host."""
    parsed = urlparse(value)
    return parsed.scheme == "rtsp" and bool(parsed.netloc)


def is_http_url(value: str) -> bool:
    """Return true when value is an HTTP(S) URL with a host."""
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
