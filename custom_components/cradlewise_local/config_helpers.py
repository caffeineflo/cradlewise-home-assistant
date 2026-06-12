"""Pure helpers for Cradlewise config validation."""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse


def is_rtsp_url(value: str) -> bool:
    """Return true when value is an RTSP URL with a host."""
    parsed = urlparse(value)
    return parsed.scheme == "rtsp" and bool(parsed.netloc)


def is_http_url(value: str) -> bool:
    """Return true when value is an HTTP(S) URL with a host."""
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def snapshot_url_from_status_url(value: str) -> str:
    """Return the bridge snapshot URL next to a status endpoint."""
    parsed = urlparse(value)
    base_path = parsed.path.rstrip("/")
    if base_path.endswith("/state"):
        base_path = base_path.removesuffix("/state")
    snapshot_path = f"{base_path}/snapshot.jpg" if base_path else "/snapshot.jpg"
    return urlunparse((parsed.scheme, parsed.netloc, snapshot_path, "", "", ""))
