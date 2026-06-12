import asyncio
import time

import pytest

from cradlewise_local.__main__ import monitor_media_freshness
from cradlewise_local.status import BridgeStatusStore


def test_media_watchdog_raises_when_video_frames_go_stale(monkeypatch):
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
    store.increment_video_frames()

    now = time.time()
    monkeypatch.setattr("cradlewise_local.__main__.time.time", lambda: now + 5)

    async def run_watchdog():
        with pytest.raises(RuntimeError, match="video stream stale"):
            await monitor_media_freshness(store, stale_timeout=1)

    asyncio.run(run_watchdog())
