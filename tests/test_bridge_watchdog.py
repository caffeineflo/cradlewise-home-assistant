import asyncio
import time

import pytest

from cradlewise_local.__main__ import (
    main,
    monitor_media_freshness,
    supervise_local_bridge,
)
from cradlewise_local.config import BridgeConfig
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


def test_media_watchdog_raises_when_first_frame_never_arrives(monkeypatch):
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
    store.mark_stream_started()
    now = time.time()
    monkeypatch.setattr("cradlewise_local.__main__.time.time", lambda: now + 5)

    async def no_wait(_delay):
        return None

    monkeypatch.setattr("cradlewise_local.__main__.asyncio.sleep", no_wait)

    async def run_watchdog():
        with pytest.raises(RuntimeError, match="first video frame"):
            await monitor_media_freshness(
                store, stale_timeout=90, initial_frame_timeout=1
            )

    asyncio.run(run_watchdog())


def test_media_watchdog_raises_on_failed_peer_connection(monkeypatch):
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
    store.set_webrtc_state("failed")

    async def no_wait(_delay):
        return None

    monkeypatch.setattr("cradlewise_local.__main__.asyncio.sleep", no_wait)

    async def run_watchdog():
        with pytest.raises(RuntimeError, match="WebRTC failed"):
            await monitor_media_freshness(store, stale_timeout=90)

    asyncio.run(run_watchdog())


def test_main_exits_process_on_fatal_bridge_error(monkeypatch):
    async def fail_bridge(args):
        raise RuntimeError("bridge failed")

    def fake_exit(code):
        raise SystemExit(code)

    monkeypatch.setattr(
        "sys.argv",
        [
            "cradlewise-local",
            "--cradle-id",
            "cradle-1",
            "--output-url",
            "rtsp://127.0.0.1:8554/cradlewise",
        ],
    )
    monkeypatch.setattr("cradlewise_local.__main__.async_main", fail_bridge)
    monkeypatch.setattr("cradlewise_local.__main__.os._exit", fake_exit)

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 1


def test_local_bridge_supervisor_retries_without_exiting(monkeypatch, tmp_path):
    certs_dir = tmp_path / "certs"
    certs_dir.mkdir()
    for name in ("ca.pem", "client_cert.pem", "client_key.pem", "device_id"):
        (certs_dir / name).write_text("test")
    config = BridgeConfig.from_values(
        cradle_id="cradle-1",
        crib_ip="192.0.2.10",
        certs_dir=certs_dir,
        output_url="rtsp://127.0.0.1:8554/cradlewise",
    )
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
    attempts = 0

    async def fail_bridge(_config, _sink, _store, _command_handler):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("crib unavailable")

    async def idle_watchdog(*_args, **_kwargs):
        await asyncio.Future()

    async def stop_after_second_retry(_delay):
        if attempts >= 2:
            raise asyncio.CancelledError

    monkeypatch.setattr("cradlewise_local.__main__.run_bridge", fail_bridge)
    monkeypatch.setattr(
        "cradlewise_local.__main__.monitor_media_freshness", idle_watchdog
    )
    monkeypatch.setattr(
        "cradlewise_local.__main__.asyncio.sleep", stop_after_second_retry
    )

    async def run_supervisor():
        with pytest.raises(asyncio.CancelledError):
            await supervise_local_bridge(config, store, command_handler=None)

    asyncio.run(run_supervisor())

    assert attempts == 2
