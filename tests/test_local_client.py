from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from cradlewise_client.local import (
    LocalConnectionError,
    LocalCradleClient,
    LocalCredentials,
)
from paho.mqtt.client import MQTT_ERR_SUCCESS


class FakeMqttClient:
    def __init__(self, **kwargs):
        self.init_kwargs = kwargs
        self.tls_options = None
        self.tls_thread_id = None
        self.insecure = False
        self.connected_to = None
        self.subscriptions = None
        self.published = []
        self.loop_started = False
        self.loop_stopped = False
        self.on_connect = None
        self.on_disconnect = None
        self.on_message = None
        self.on_subscribe = None
        self.subscribe_reason_codes = [0] * 6
        self.publish_result = MQTT_ERR_SUCCESS

    def tls_set(self, **kwargs):
        self.tls_options = kwargs
        self.tls_thread_id = threading.get_ident()

    def tls_insecure_set(self, enabled):
        self.insecure = enabled

    def reconnect_delay_set(self, **_kwargs):
        return None

    def connect(self, host, port, keepalive):
        self.connected_to = (host, port, keepalive)
        self.on_connect(self, None, {}, 0, None)
        return MQTT_ERR_SUCCESS

    def loop_start(self):
        self.loop_started = True
        self.on_subscribe(self, None, 7, self.subscribe_reason_codes, None)

    def loop_stop(self):
        self.loop_stopped = True

    def disconnect(self):
        self.on_disconnect(self, None, {}, 0, None)
        return MQTT_ERR_SUCCESS

    def subscribe(self, topics):
        self.subscriptions = topics
        return MQTT_ERR_SUCCESS, 7

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, payload, qos, retain))
        return SimpleNamespace(rc=self.publish_result)


@pytest.fixture
def credentials(tmp_path: Path) -> LocalCredentials:
    for name in ("ca.pem", "client_cert.pem", "client_key.pem"):
        (tmp_path / name).write_text(name, encoding="utf-8")
    (tmp_path / "device_id").write_text("device-1", encoding="utf-8")
    return LocalCredentials.from_directory(tmp_path)


@pytest.fixture
def client_parts(credentials: LocalCredentials):
    mqtt_client = FakeMqttClient()
    updates = []
    connection_states = []
    client = LocalCradleClient(
        host="192.0.2.10",
        cradle_id="cradle-1",
        credentials=credentials,
        update_callback=updates.append,
        connection_callback=connection_states.append,
        mqtt_client_factory=lambda **kwargs: _configure_fake_client(
            mqtt_client, kwargs
        ),
    )
    return client, mqtt_client, updates, connection_states


def _configure_fake_client(mqtt_client, kwargs):
    mqtt_client.init_kwargs = kwargs
    return mqtt_client


async def test_start_connects_with_device_identity(client_parts):
    client, mqtt_client, _updates, _connection_states = client_parts

    await client.async_start()

    assert (mqtt_client.init_kwargs["client_id"], client.started) == (
        "device-1",
        True,
    )
    await client.async_stop()
    assert client.started is False


async def test_start_configures_tls_outside_event_loop(client_parts):
    client, mqtt_client, _updates, _connection_states = client_parts

    await client.async_start()

    assert mqtt_client.tls_thread_id != threading.get_ident()
    await client.async_stop()


async def test_start_subscribes_only_to_state_topics(client_parts):
    client, mqtt_client, _updates, _connection_states = client_parts

    await client.async_start()

    assert [topic for topic, _qos in mqtt_client.subscriptions] == [
        "/cradle-1/beacon",
        "/cradle/cradle-1/cradle_state",
        "$aws/things/cradle-1/shadow/get/accepted",
        "$aws/things/cradle-1/shadow/get/rejected",
        "$aws/things/cradle-1/shadow/update/accepted",
        "$aws/things/cradle-1/shadow/update/rejected",
    ]
    await client.async_stop()


async def test_subscription_ack_requests_current_shadow(client_parts):
    client, mqtt_client, _updates, _connection_states = client_parts
    await client.async_start()

    assert mqtt_client.published == [
        ("$aws/things/cradle-1/shadow/get", "{}", 0, False)
    ]
    await client.async_stop()


@pytest.mark.parametrize(
    ("reason_codes", "publish_result", "message"),
    [
        ([128] * 6, MQTT_ERR_SUCCESS, "subscription was rejected"),
        ([0] * 6, 1, "shadow request failed"),
    ],
)
async def test_start_cleans_up_when_state_initialization_fails(
    client_parts,
    reason_codes,
    publish_result,
    message,
):
    client, mqtt_client, _updates, _connection_states = client_parts
    mqtt_client.subscribe_reason_codes = reason_codes
    mqtt_client.publish_result = publish_result

    with pytest.raises(LocalConnectionError, match=message):
        await client.async_start()

    assert client.started is False


async def test_runtime_subscription_failure_stops_client_for_retry(client_parts):
    client, mqtt_client, _updates, _connection_states = client_parts
    await client.async_start()
    stopped = asyncio.Event()
    original_stop = client.async_stop

    async def stop_and_signal():
        await original_stop()
        stopped.set()

    client.async_stop = stop_and_signal
    mqtt_client.on_connect(mqtt_client, None, {}, 0, None)
    mqtt_client.on_subscribe(mqtt_client, None, 7, [128] * 6, None)

    await asyncio.wait_for(stopped.wait(), timeout=1)

    assert client.started is False


async def test_state_message_is_dispatched_on_event_loop(client_parts):
    client, mqtt_client, updates, _connection_states = client_parts
    await client.async_start()

    mqtt_client.on_message(
        mqtt_client,
        None,
        SimpleNamespace(
            topic="$aws/things/cradle-1/shadow/get/accepted",
            payload=b'{"state":{"reported":{"babyPresent":false}}}',
        ),
    )
    await asyncio.sleep(0)

    assert updates[0].kind == "device_state"
    await client.async_stop()


async def test_publish_shadow_does_not_retry_command(client_parts):
    client, mqtt_client, _updates, _connection_states = client_parts
    await client.async_start()
    mqtt_client.published.clear()
    payload = {"state": {"desired": {"bounceLevel": 2}}}

    client.publish_shadow(payload)

    assert mqtt_client.published == [
        (
            "$aws/things/cradle-1/shadow/update",
            json.dumps(payload, separators=(",", ":")),
            0,
            False,
        )
    ]
    await client.async_stop()


async def test_stop_reports_disconnected_once(client_parts):
    client, _mqtt_client, _updates, connection_states = client_parts
    await client.async_start()

    await client.async_stop()

    assert connection_states == [True, False]


def test_credentials_prefer_pinned_server_ca(tmp_path: Path):
    for name in ("ca.pem", "server_ca.pem", "client_cert.pem", "client_key.pem"):
        (tmp_path / name).write_text(name, encoding="utf-8")
    (tmp_path / "device_id").write_text("device-1", encoding="utf-8")

    credentials = LocalCredentials.from_directory(tmp_path)

    assert credentials.ca_path == tmp_path / "server_ca.pem"


def test_credentials_reject_missing_device_id(tmp_path: Path):
    for name in ("ca.pem", "client_cert.pem", "client_key.pem"):
        (tmp_path / name).write_text(name, encoding="utf-8")

    with pytest.raises(LocalConnectionError, match="device_id"):
        LocalCredentials.from_directory(tmp_path)
