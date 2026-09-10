"""Optional Cradlewise cloud state polling for the local bridge."""

from __future__ import annotations

import asyncio
import logging

from cradlewise_client.cloud import CloudAccountClient as CradlewiseCloudStateClient
from cradlewise_client.cloud import CloudApiError as CloudStateError

from .config import BridgeConfig
from .status import BridgeStatusStore

log = logging.getLogger(__name__)


async def poll_cloud_state(
    config: BridgeConfig,
    status_store: BridgeStatusStore,
) -> None:
    """Poll cloud state until cancelled and merge it into bridge status."""
    if not config.cloud_state_enabled:
        return

    if config.cloud_email is None or config.cloud_password is None:
        raise CloudStateError("Cloud state polling requires email and password")
    client = CradlewiseCloudStateClient(
        email=config.cloud_email,
        password=config.cloud_password,
    )
    log.info(
        "Cloud state polling enabled for cradle %s every %d seconds",
        config.cradle_id,
        config.cloud_state_poll_interval,
    )

    while True:
        try:
            status = await asyncio.to_thread(
                client.get_cradle_online_status, config.cradle_id
            )
            status_store.update_cradle_state(status, source="cloud")
            payload = await asyncio.to_thread(client.get_cradle_state, config.cradle_id)
            status_store.update_device_state(payload, source="cloud")
            log.debug("Cloud device state updated")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            status_store.mark_device_state_error("cloud", str(exc))
            log.warning("Cloud state poll failed: %s", exc)

        await asyncio.sleep(config.cloud_state_poll_interval)
