"""Media-free local Cradlewise MQTT client."""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from paho.mqtt import client as mqtt
from paho.mqtt.client import MQTT_ERR_SUCCESS, CallbackAPIVersion

MQTT_PORT = 8883
MQTT_SERVER_CA_FILE = "server_ca.pem"

_LOGGER = logging.getLogger(__name__)


class LocalConnectionError(RuntimeError):
    """Raised when the local MQTT connection cannot be established or used."""


@dataclass(frozen=True)
class LocalCredentials:
    """Files and client identity required by the crib's local MQTT broker."""

    ca_path: Path
    client_cert_path: Path
    client_key_path: Path
    device_id: str

    @classmethod
    def from_directory(cls, directory: str | Path) -> LocalCredentials:
        """Load and validate a provisioned certificate directory."""
        path = Path(directory)
        pinned_ca = path / MQTT_SERVER_CA_FILE
        ca_path = pinned_ca if pinned_ca.is_file() else path / "ca.pem"
        required = (ca_path, path / "client_cert.pem", path / "client_key.pem")
        missing = [item.name for item in required if not item.is_file()]
        device_id_path = path / "device_id"
        if not device_id_path.is_file():
            missing.append(device_id_path.name)
        if missing:
            raise LocalConnectionError(
                f"missing local credential files in {path}: {', '.join(missing)}"
            )

        device_id = device_id_path.read_text(encoding="utf-8").strip()
        if not device_id:
            raise LocalConnectionError(f"local device ID is blank: {device_id_path}")
        return cls(
            ca_path=ca_path,
            client_cert_path=path / "client_cert.pem",
            client_key_path=path / "client_key.pem",
            device_id=device_id,
        )

    @property
    def uses_pinned_server_ca(self) -> bool:
        """Return whether the broker CA supports hostname verification."""
        return self.ca_path.name == MQTT_SERVER_CA_FILE


@dataclass(frozen=True)
class LocalCradleUpdate:
    """One decoded state update received from the crib."""

    kind: str
    payload: dict[str, Any]


UpdateCallback = Callable[[LocalCradleUpdate], None]
ConnectionCallback = Callable[[bool], None]
MqttClientFactory = Callable[..., mqtt.Client]


def _reason_code_failed(reason_code: Any) -> bool:
    failure = getattr(reason_code, "is_failure", None)
    if failure is not None:
        return bool(failure() if callable(failure) else failure)
    try:
        return int(reason_code) >= 128
    except (TypeError, ValueError):
        return True


class LocalCradleClient:
    """Own one local mTLS MQTT connection without starting a media session."""

    def __init__(
        self,
        *,
        host: str,
        cradle_id: str,
        credentials: LocalCredentials,
        update_callback: UpdateCallback,
        connection_callback: ConnectionCallback,
        mqtt_client_factory: MqttClientFactory = mqtt.Client,
    ) -> None:
        if not host.strip():
            raise LocalConnectionError("local MQTT host must not be blank")
        if not cradle_id.strip():
            raise LocalConnectionError("cradle ID must not be blank")

        self.host = host.strip()
        self.cradle_id = cradle_id.strip()
        self.credentials = credentials
        self._update_callback = update_callback
        self._connection_callback = connection_callback
        self._mqtt_client_factory = mqtt_client_factory
        self._mqtt: mqtt.Client | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._connected_future: asyncio.Future[None] | None = None
        self._connected = False
        self._stopping = False
        self._mqtt_loop_started = False
        self._publish_lock = threading.Lock()
        self._state_subscription_mids: set[int] = set()

        self.beacon_topic = f"/{self.cradle_id}/beacon"
        self.cradle_state_topic = f"/cradle/{self.cradle_id}/cradle_state"
        self.shadow_get_topic = f"$aws/things/{self.cradle_id}/shadow/get"
        self.shadow_get_accepted_topic = f"{self.shadow_get_topic}/accepted"
        self.shadow_get_rejected_topic = f"{self.shadow_get_topic}/rejected"
        self.shadow_update_topic = f"$aws/things/{self.cradle_id}/shadow/update"
        self.shadow_update_accepted_topic = f"{self.shadow_update_topic}/accepted"
        self.shadow_update_rejected_topic = f"{self.shadow_update_topic}/rejected"

    @property
    def connected(self) -> bool:
        """Return whether the broker has acknowledged the MQTT connection."""
        return self._connected

    @property
    def started(self) -> bool:
        """Return whether the Paho network loop owns an active client."""
        return self._mqtt is not None

    async def async_start(self, timeout: float = 10) -> None:
        """Connect and wait until the state subscription is ready."""
        if self._mqtt is not None:
            raise LocalConnectionError("local MQTT client is already started")

        self._loop = asyncio.get_running_loop()
        self._connected_future = self._loop.create_future()
        self._stopping = False
        client = self._mqtt_client_factory(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=self.credentials.device_id,
            clean_session=False,
            protocol=mqtt.MQTTv311,
        )
        await asyncio.to_thread(self._configure_tls, client)
        client.reconnect_delay_set(min_delay=1, max_delay=30)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client.on_subscribe = self._on_subscribe
        self._mqtt = client

        try:
            result = await asyncio.to_thread(
                client.connect,
                self.host,
                MQTT_PORT,
                15,
            )
            if result != MQTT_ERR_SUCCESS:
                raise LocalConnectionError(
                    f"local MQTT connect failed before CONNACK with rc={result}"
                )
            client.loop_start()
            self._mqtt_loop_started = True
            await asyncio.wait_for(self._connected_future, timeout=timeout)
        except BaseException:
            await self.async_stop()
            raise

    def _configure_tls(self, client: mqtt.Client) -> None:
        """Configure local broker TLS, including legacy CA compatibility."""
        client.tls_set(
            ca_certs=str(self.credentials.ca_path),
            certfile=str(self.credentials.client_cert_path),
            keyfile=str(self.credentials.client_key_path),
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )
        if not self.credentials.uses_pinned_server_ca:
            client.tls_insecure_set(True)

    async def async_stop(self) -> None:
        """Disconnect and stop the Paho network thread."""
        client = self._mqtt
        if client is None:
            return

        self._stopping = True
        self._mqtt = None
        try:
            await asyncio.to_thread(client.disconnect)
        finally:
            if self._mqtt_loop_started:
                await asyncio.to_thread(client.loop_stop)
            self._mqtt_loop_started = False
            self._set_connected(False)
            if self._connected_future is not None:
                self._connected_future.cancel()
            self._connected_future = None
            self._loop = None
            self._state_subscription_mids.clear()

    def publish_shadow(self, payload: dict[str, Any]) -> None:
        """Publish an APK-shaped desired shadow update without retrying it."""
        client = self._mqtt
        if client is None or not self._connected:
            raise LocalConnectionError("local MQTT publisher is not connected")
        data = json.dumps(payload, separators=(",", ":"))
        with self._publish_lock:
            result = client.publish(
                self.shadow_update_topic,
                data,
                qos=0,
                retain=False,
            )
        if result.rc != MQTT_ERR_SUCCESS:
            raise LocalConnectionError(
                f"local MQTT shadow publish failed with rc={result.rc}"
            )

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code != 0:
            self._dispatch_connection_error(
                LocalConnectionError(f"local MQTT CONNACK failed: {reason_code}")
            )
            return

        result, mid = client.subscribe(
            [
                (self.beacon_topic, 0),
                (self.cradle_state_topic, 0),
                (self.shadow_get_accepted_topic, 0),
                (self.shadow_get_rejected_topic, 0),
                (self.shadow_update_accepted_topic, 0),
                (self.shadow_update_rejected_topic, 0),
            ]
        )
        if result != MQTT_ERR_SUCCESS:
            self._dispatch_connection_error(
                LocalConnectionError(
                    f"local MQTT state subscription failed with rc={result}"
                )
            )
            return
        self._state_subscription_mids.add(mid)

    def _on_disconnect(
        self,
        client,
        userdata,
        disconnect_flags,
        reason_code,
        properties,
    ) -> None:
        self._dispatch_disconnected()
        if reason_code != 0 and not self._stopping:
            _LOGGER.warning("Local Cradlewise MQTT disconnected: %s", reason_code)

    def _on_subscribe(
        self,
        client,
        userdata,
        mid,
        reason_code_list,
        properties,
    ) -> None:
        if mid not in self._state_subscription_mids:
            return
        self._state_subscription_mids.discard(mid)
        if any(_reason_code_failed(code) for code in reason_code_list):
            self._dispatch_connection_error(
                LocalConnectionError("local MQTT state subscription was rejected")
            )
            return
        result = client.publish(self.shadow_get_topic, "{}", qos=0, retain=False)
        if result.rc != MQTT_ERR_SUCCESS:
            self._dispatch_connection_error(
                LocalConnectionError(
                    f"local MQTT shadow request failed with rc={result.rc}"
                )
            )
            return
        self._dispatch_connected()

    def _on_message(self, client, userdata, message) -> None:
        topic = message.topic
        kinds = {
            self.beacon_topic: "beacon",
            self.cradle_state_topic: "cradle_state",
            self.shadow_get_accepted_topic: "device_state",
            self.shadow_update_accepted_topic: "device_state",
        }
        kind = kinds.get(topic)
        if kind is None:
            if topic in {
                self.shadow_get_rejected_topic,
                self.shadow_update_rejected_topic,
            }:
                _LOGGER.warning("Local Cradlewise shadow request was rejected")
            return
        try:
            payload = json.loads(message.payload)
        except (json.JSONDecodeError, UnicodeDecodeError):
            _LOGGER.warning(
                "Ignored invalid JSON from local Cradlewise topic %s", topic
            )
            return
        if not isinstance(payload, dict):
            _LOGGER.warning(
                "Ignored non-object state from local Cradlewise topic %s", topic
            )
            return
        self._dispatch_update(LocalCradleUpdate(kind=kind, payload=payload))

    def _dispatch_connected(self) -> None:
        loop = self._loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(self._handle_connected)

    def _dispatch_disconnected(self) -> None:
        loop = self._loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(self._set_connected, False)

    def _dispatch_connection_error(self, error: LocalConnectionError) -> None:
        loop = self._loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(self._handle_connection_error, error)

    def _dispatch_update(self, update: LocalCradleUpdate) -> None:
        loop = self._loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(self._update_callback, update)

    def _handle_connected(self) -> None:
        self._set_connected(True)
        if self._connected_future is not None and not self._connected_future.done():
            self._connected_future.set_result(None)

    def _handle_connection_error(self, error: LocalConnectionError) -> None:
        self._set_connected(False)
        if self._connected_future is not None and not self._connected_future.done():
            self._connected_future.set_exception(error)
            return
        _LOGGER.error("Local Cradlewise MQTT error: %s", error)
        asyncio.create_task(self.async_stop())

    def _set_connected(self, connected: bool) -> None:
        if self._connected == connected:
            return
        self._connected = connected
        self._connection_callback(connected)
