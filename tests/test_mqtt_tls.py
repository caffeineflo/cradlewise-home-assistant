import asyncio
from pathlib import Path

import pytest

import stream_local
from stream_local import CribStreamer, mqtt_server_ca_path


class FakeMqttClient:
    def __init__(self, **_kwargs):
        self.tls_options = None
        self.insecure_calls = 0
        self.reconnect_delays = None

    def tls_set(self, **kwargs):
        self.tls_options = kwargs

    def tls_insecure_set(self, _enabled):
        self.insecure_calls += 1

    def reconnect_delay_set(self, *, min_delay, max_delay):
        self.reconnect_delays = (min_delay, max_delay)

    @staticmethod
    def subscribe(_topic):
        return 0, 1


def build_streamer(tmp_path: Path, monkeypatch) -> tuple[CribStreamer, FakeMqttClient]:
    (tmp_path / "device_id").write_text("device-1")
    client = FakeMqttClient()
    monkeypatch.setattr("stream_local.mqtt.Client", lambda **_kwargs: client)
    streamer = CribStreamer("192.0.2.10", "cradle-1", tmp_path)
    streamer._setup_mqtt()
    return streamer, client


def build_running_streamer(
    tmp_path: Path, monkeypatch
) -> tuple[CribStreamer, FakeMqttClient]:
    (tmp_path / "server_ca.pem").write_text("current")
    streamer, client = build_streamer(tmp_path, monkeypatch)
    streamer._loop = asyncio.get_running_loop()
    streamer._fatal_future = streamer._loop.create_future()
    return streamer, client


def test_mqtt_prefers_pinned_greengrass_v2_ca(tmp_path: Path):
    (tmp_path / "ca.pem").write_text("legacy")
    pinned = tmp_path / "server_ca.pem"
    pinned.write_text("current")

    assert mqtt_server_ca_path(tmp_path) == pinned


def test_mqtt_uses_provisioned_ca_without_pinned_ca(tmp_path: Path):
    provisioned = tmp_path / "ca.pem"
    provisioned.write_text("legacy")

    assert mqtt_server_ca_path(tmp_path) == provisioned


def test_pinned_ca_keeps_hostname_verification_enabled(tmp_path: Path, monkeypatch):
    (tmp_path / "server_ca.pem").write_text("current")

    _streamer, client = build_streamer(tmp_path, monkeypatch)

    assert (Path(client.tls_options["ca_certs"]), client.insecure_calls) == (
        tmp_path / "server_ca.pem",
        0,
    )


def test_legacy_ca_disables_only_hostname_verification(tmp_path: Path, monkeypatch):
    (tmp_path / "ca.pem").write_text("legacy")

    _streamer, client = build_streamer(tmp_path, monkeypatch)

    assert (Path(client.tls_options["ca_certs"]), client.insecure_calls) == (
        tmp_path / "ca.pem",
        1,
    )


def test_mqtt_reconnect_backoff_is_bounded(tmp_path: Path, monkeypatch):
    (tmp_path / "server_ca.pem").write_text("current")

    _streamer, client = build_streamer(tmp_path, monkeypatch)

    assert client.reconnect_delays == (1, 10)


@pytest.mark.asyncio
async def test_transient_mqtt_disconnect_preserves_stream(tmp_path: Path, monkeypatch):
    streamer, client = build_running_streamer(tmp_path, monkeypatch)
    streamer._pc = object()

    try:
        streamer._on_disconnect(client, None, {}, 1, None)
        await asyncio.sleep(0)
        streamer._on_connect(client, None, {}, 0, None)
        await asyncio.sleep(0)

        assert not streamer._fatal_future.done()
    finally:
        if streamer._fatal_future.done() and not streamer._fatal_future.cancelled():
            streamer._fatal_future.exception()
        else:
            streamer._fatal_future.cancel()


@pytest.mark.asyncio
async def test_mqtt_disconnect_exceeding_grace_stops_stream(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(
        stream_local,
        "MQTT_RECONNECT_GRACE_SECONDS",
        0.01,
    )
    streamer, client = build_running_streamer(tmp_path, monkeypatch)

    streamer._on_disconnect(client, None, {}, 1, None)

    with pytest.raises(RuntimeError, match="did not reconnect within"):
        await asyncio.wait_for(streamer._fatal_future, timeout=0.1)


@pytest.mark.asyncio
async def test_shutdown_cancels_mqtt_reconnect_grace(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        stream_local,
        "MQTT_RECONNECT_GRACE_SECONDS",
        0.01,
    )
    streamer, client = build_running_streamer(tmp_path, monkeypatch)

    try:
        streamer._on_disconnect(client, None, {}, 1, None)
        await asyncio.sleep(0)
        streamer._shutting_down = True
        streamer._cancel_mqtt_reconnect_grace()
        await asyncio.sleep(0.02)

        assert not streamer._fatal_future.done()
    finally:
        if not streamer._fatal_future.done():
            streamer._fatal_future.cancel()
