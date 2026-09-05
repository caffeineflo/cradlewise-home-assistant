import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

import stream_local
from stream_local import CribStreamer, mqtt_server_ca_path


class FakeMqttClient:
    def __init__(self, **_kwargs):
        self.tls_options = None
        self.insecure_calls = 0
        self.reconnect_delays = None
        self.disconnect_calls = 0
        self.loop_stop_calls = 0
        self.subscribe_calls = 0
        self.publish_calls = 0
        self.connect_callback_on_disconnect = False
        self.disconnect_error = None

    def tls_set(self, **kwargs):
        self.tls_options = kwargs

    def tls_insecure_set(self, _enabled):
        self.insecure_calls += 1

    def reconnect_delay_set(self, *, min_delay, max_delay):
        self.reconnect_delays = (min_delay, max_delay)

    def subscribe(self, _topic):
        self.subscribe_calls += 1
        return 0, 1

    def publish(self, _topic, _data):
        self.publish_calls += 1
        return SimpleNamespace(rc=0)

    @staticmethod
    def connect(_host, _port, keepalive):
        return 0

    @staticmethod
    def loop_start():
        return 0

    def disconnect(self):
        self.disconnect_calls += 1
        if self.connect_callback_on_disconnect:
            self.on_connect(self, None, {}, 0, None)
        if self.disconnect_error is not None:
            raise self.disconnect_error

    def loop_stop(self):
        self.loop_stop_calls += 1


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


@pytest.mark.asyncio
async def test_mqtt_loop_stops_when_peer_cleanup_fails(tmp_path: Path, monkeypatch):
    (tmp_path / "server_ca.pem").write_text("current")
    streamer, client = build_streamer(tmp_path, monkeypatch)

    async def finish_messages():
        return None

    class FailingPeer:
        @staticmethod
        async def close():
            raise RuntimeError("peer cleanup failed")

    streamer._process_messages = finish_messages
    streamer._pc = FailingPeer()

    with pytest.raises(
        RuntimeError, match="WebRTC peer connection cleanup failed: peer cleanup failed"
    ):
        await streamer.run()

    assert (client.disconnect_calls, client.loop_stop_calls) == (1, 1)


@pytest.mark.asyncio
async def test_primary_failure_survives_peer_cleanup_failure(
    tmp_path: Path, monkeypatch, caplog
):
    (tmp_path / "server_ca.pem").write_text("current")
    streamer, _client = build_streamer(tmp_path, monkeypatch)

    async def fail_messages():
        raise RuntimeError("stream failed")

    class FailingPeer:
        @staticmethod
        async def close():
            raise RuntimeError("peer cleanup failed")

    streamer._process_messages = fail_messages
    streamer._pc = FailingPeer()

    with pytest.raises(RuntimeError, match="stream failed"):
        await streamer.run()

    assert "WebRTC peer connection cleanup failed: peer cleanup failed" in caplog.text


@pytest.mark.asyncio
async def test_shutdown_ignores_late_mqtt_connect_callback(tmp_path: Path, monkeypatch):
    (tmp_path / "server_ca.pem").write_text("current")
    streamer, client = build_streamer(tmp_path, monkeypatch)

    async def finish_messages():
        return None

    client.connect_callback_on_disconnect = True
    streamer._process_messages = finish_messages

    await streamer.run()

    assert (client.subscribe_calls, client.publish_calls, client.loop_stop_calls) == (
        0,
        0,
        1,
    )


@pytest.mark.asyncio
async def test_mqtt_disconnect_failure_does_not_skip_remaining_cleanup(
    tmp_path: Path, monkeypatch
):
    (tmp_path / "server_ca.pem").write_text("current")
    streamer, client = build_streamer(tmp_path, monkeypatch)

    async def finish_messages():
        return None

    class RecordingPeer:
        def __init__(self):
            self.close_calls = 0

        async def close(self):
            self.close_calls += 1

    class RecordingProcess:
        def __init__(self):
            self.terminate_calls = 0

        def terminate(self):
            self.terminate_calls += 1

    peer = RecordingPeer()
    process = RecordingProcess()
    client.disconnect_error = RuntimeError("disconnect failed")
    streamer._process_messages = finish_messages
    streamer._pc = peer
    streamer._ffplay = process

    with pytest.raises(
        RuntimeError, match="MQTT disconnect cleanup failed: disconnect failed"
    ):
        await streamer.run()

    assert (
        client.loop_stop_calls,
        peer.close_calls,
        process.terminate_calls,
    ) == (1, 1, 1)


@pytest.mark.asyncio
async def test_repeated_runs_do_not_retain_mqtt_loop_threads(
    tmp_path: Path, monkeypatch
):
    (tmp_path / "server_ca.pem").write_text("current")
    (tmp_path / "device_id").write_text("device-1")
    clients = []

    class ThreadedMqttClient(FakeMqttClient):
        def __init__(self):
            super().__init__()
            self.stop_event = threading.Event()
            self.thread = None

        def loop_start(self):
            self.thread = threading.Thread(
                target=self.stop_event.wait,
                name="paho-mqtt-client-lifecycle-test",
            )
            self.thread.start()
            return 0

        def loop_stop(self):
            super().loop_stop()
            self.stop_event.set()
            self.thread.join()

    def client_factory(**_kwargs):
        client = ThreadedMqttClient()
        clients.append(client)
        return client

    monkeypatch.setattr("stream_local.mqtt.Client", client_factory)

    async def finish_messages():
        return None

    for _ in range(25):
        streamer = CribStreamer("192.0.2.10", "cradle-1", tmp_path)
        streamer._process_messages = finish_messages
        await streamer.run()

    assert all(not client.thread.is_alive() for client in clients)
