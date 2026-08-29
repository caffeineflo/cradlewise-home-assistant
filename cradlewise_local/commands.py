"""Compatibility imports for bridge command handling."""

from cradlewise_client.commands import (
    CommandError,
    CommandUnavailable,
    CradlewiseCommandHandler,
    build_desired,
    shadow_payload,
)

BridgeCommandHandler = CradlewiseCommandHandler

__all__ = [
    "BridgeCommandHandler",
    "CommandError",
    "CommandUnavailable",
    "build_desired",
    "shadow_payload",
]
