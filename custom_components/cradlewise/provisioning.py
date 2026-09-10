"""Keep ownership of executor-created registrations when a flow is cancelled."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TypeVar

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
_T = TypeVar("_T")


async def _drain_job(job: asyncio.Future[_T]) -> _T:
    """Finish owned work despite repeated cancellation of the parent flow."""
    while not job.done():
        try:
            await asyncio.shield(job)
        except asyncio.CancelledError:
            # The caller re-raises its original cancellation after rollback.
            continue
    return job.result()


async def async_registration_job(
    hass: HomeAssistant,
    job: asyncio.Future[_T],
    rollback: Callable[[_T], None],
) -> _T:
    """Wait for a registration job, or drain and roll it back on cancellation."""
    try:
        return await asyncio.shield(job)
    except asyncio.CancelledError:
        try:
            result = await _drain_job(job)
            await _drain_job(hass.async_add_executor_job(rollback, result))
        except Exception:
            _LOGGER.exception(
                "Cancelled Cradlewise provisioning did not finish cleanly; "
                "check the account for an unused device registration"
            )
        raise
