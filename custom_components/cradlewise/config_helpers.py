"""Pure configuration helpers for Cradlewise."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import SplitResult, urlsplit, urlunsplit

STATE_ENDPOINT = "state"
COMMAND_ENDPOINT = "command"
SNAPSHOT_ENDPOINT = "snapshot.jpg"
INFO_ENDPOINT = "info"
HEALTH_ENDPOINT = "health"
LIVE_ENDPOINT = "live"
KNOWN_ENDPOINTS = {
    STATE_ENDPOINT,
    COMMAND_ENDPOINT,
    SNAPSHOT_ENDPOINT,
    INFO_ENDPOINT,
    HEALTH_ENDPOINT,
    LIVE_ENDPOINT,
}


def _parsed_url(value: str, schemes: set[str]) -> SplitResult | None:
    """Parse a URL that has an allowed scheme and a real host."""
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme not in schemes or parsed.hostname is None:
        return None
    if port is not None and not 1 <= port <= 65535:
        return None
    return parsed


def _replace_endpoint(value: str, endpoint: str) -> str:
    """Append or replace a known bridge endpoint without corrupting the URL."""
    parsed = urlsplit(value)
    parts = [part for part in parsed.path.split("/") if part]
    if parts and parts[-1] in KNOWN_ENDPOINTS:
        parts[-1] = endpoint
    else:
        parts.append(endpoint)
    path = "/" + "/".join(parts)
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ""))


def is_rtsp_url(value: str) -> bool:
    """Return true when value is an RTSP URL with a host."""
    return _parsed_url(value, {"rtsp", "rtsps"}) is not None


def is_http_url(value: str) -> bool:
    """Return true when value is an HTTP(S) URL with a host."""
    return _parsed_url(value, {"http", "https"}) is not None


def http_url_uses_tls(value: str) -> bool:
    """Return true when a validated HTTP URL uses TLS."""
    parsed = _parsed_url(value, {"http", "https"})
    return parsed is not None and parsed.scheme == "https"


def http_url_resolves_to_private_network(value: str) -> bool:
    """Return whether every resolved address is private, loopback, or link-local."""
    parsed = _parsed_url(value, {"http", "https"})
    if parsed is None or parsed.hostname is None:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = {
        ipaddress.ip_address(sockaddr[0])
        for _, _, _, _, sockaddr in socket.getaddrinfo(
            parsed.hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    }
    if not addresses:
        raise OSError(f"{parsed.hostname} did not resolve to an address")
    return all(
        address.is_private or address.is_loopback or address.is_link_local
        for address in addresses
    )


def snapshot_url_from_status_url(value: str) -> str:
    """Return the bridge snapshot URL next to a status endpoint."""
    return _replace_endpoint(value, SNAPSHOT_ENDPOINT)


def state_url_from_status_url(value: str) -> str:
    """Return the bridge state URL for a base or endpoint URL."""
    return _replace_endpoint(value, STATE_ENDPOINT)


def command_url_from_status_url(value: str) -> str:
    """Return the bridge command URL for a base or endpoint URL."""
    return _replace_endpoint(value, COMMAND_ENDPOINT)


def info_url_from_status_url(value: str) -> str:
    """Return the bridge information URL for a base or endpoint URL."""
    return _replace_endpoint(value, INFO_ENDPOINT)


def health_url_from_status_url(value: str) -> str:
    """Return the bridge semantic health URL for a base or endpoint URL."""
    return _replace_endpoint(value, HEALTH_ENDPOINT)


def bridge_base_url(value: str) -> str:
    """Return a configuration URL without a bridge endpoint or credentials."""
    parsed = urlsplit(value)
    parts = [part for part in parsed.path.split("/") if part]
    if parts and parts[-1] in KNOWN_ENDPOINTS:
        parts.pop()
    path = "/" + "/".join(parts) if parts else ""
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = f"{host}:{parsed.port}" if parsed.port is not None else host
    return urlunsplit((parsed.scheme, netloc, path, "", ""))


def same_url_origin(first: str, second: str) -> bool:
    """Return whether two validated HTTP URLs share an origin."""
    first_url = _parsed_url(first, {"http", "https"})
    second_url = _parsed_url(second, {"http", "https"})
    if first_url is None or second_url is None:
        return False

    def origin(parsed: SplitResult) -> tuple[str, str, int]:
        default_port = 443 if parsed.scheme == "https" else 80
        return parsed.scheme, parsed.hostname or "", parsed.port or default_port

    return origin(first_url) == origin(second_url)
