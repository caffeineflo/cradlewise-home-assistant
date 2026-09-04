"""Provider coordinator for Cradlewise."""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import time
from datetime import timedelta
from functools import partial
from pathlib import Path
from typing import Any

import aiohttp
from cradlewise_client.certificates import (
    BrokerCertificateError,
    materialize_credentials,
    pin_server_ca,
)
from cradlewise_client.cloud import (
    CloudAccountClient,
    CloudApiError,
    CloudAuthenticationError,
    ProvisionedCredentials,
)
from cradlewise_client.commands import (
    CommandError,
    CommandUnavailable,
    CradlewiseCommandHandler,
    build_desired,
)
from cradlewise_client.local import (
    LocalConnectionError,
    LocalCradleClient,
    LocalCradleUpdate,
    LocalCredentials,
)
from cradlewise_client.remote import REMOTE_MQTT_ENDPOINT, RemoteCradleClient
from cradlewise_client.state import CradlewiseStateStore
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .config_helpers import health_url_from_status_url
from .const import (
    CONF_BEARER_TOKEN,
    CONF_BRIDGE_STATUS_URL,
    CONF_CLIENT_CERTIFICATE,
    CONF_CLIENT_PRIVATE_KEY,
    CONF_CONNECTION_MODE,
    CONF_CRADLE_ID,
    CONF_DEVICE_ID,
    CONF_EMAIL,
    CONF_GROUP_CA_CERTIFICATE,
    CONF_LOCAL_HOST,
    CONF_PASSWORD,
    CONF_SERVER_CA_CERTIFICATE,
    CONNECTION_MODE_AUTOMATIC,
    CONNECTION_MODE_CLOUD,
    CONNECTION_MODE_LOCAL,
    DOMAIN,
    SUPPORTED_BRIDGE_API_VERSION,
)
from .status_helpers import build_command_url, build_state_url, strict_bool

_LOGGER = logging.getLogger(__name__)

CLOUD_POLL_CONNECTED_SECONDS = 300
CLOUD_POLL_DISCONNECTED_SECONDS = 60
MQTT_RETRY_SECONDS = 60


class BridgeApiError(HomeAssistantError):
    """Base error for bridge validation and requests."""


class BridgeAuthenticationError(BridgeApiError):
    """Raised when the bridge rejects the bearer token."""


class BridgeIdentityError(BridgeApiError):
    """Raised when the endpoint belongs to another cradle."""


class BridgeVersionError(BridgeApiError):
    """Raised when the bridge API version is not supported."""


def request_headers(bearer_token: str | None) -> dict[str, str] | None:
    """Build bridge request headers without retaining an empty credential."""
    if not bearer_token:
        return None
    return {"Authorization": f"Bearer {bearer_token}"}


async def async_fetch_bridge_state(
    session: aiohttp.ClientSession,
    state_url: str,
    bearer_token: str | None,
    expected_cradle_id: str,
) -> dict[str, Any]:
    """Fetch and validate one bridge state response."""
    async with session.get(
        state_url,
        headers=request_headers(bearer_token),
        timeout=aiohttp.ClientTimeout(total=10),
    ) as response:
        if response.status == 401:
            await response.read()
            raise BridgeAuthenticationError("Bridge authentication failed")
        if response.status != 200:
            await response.read()
            raise BridgeApiError(f"Bridge returned HTTP {response.status}")
        try:
            data = await response.json(content_type=None)
        except (ValueError, aiohttp.ContentTypeError) as exc:
            raise BridgeApiError("Bridge returned invalid JSON") from exc

    if not isinstance(data, dict):
        raise BridgeApiError("Bridge returned non-object JSON")
    bridge = data.get("bridge")
    if not isinstance(bridge, dict) or not isinstance(bridge.get("cradle_id"), str):
        raise BridgeApiError("Bridge response is missing bridge.cradle_id")
    if bridge["cradle_id"] != expected_cradle_id:
        raise BridgeIdentityError(
            "Bridge cradle ID does not match the configured cradle"
        )
    return data


async def async_fetch_bridge_info(
    session: aiohttp.ClientSession,
    info_url: str,
    bearer_token: str | None,
) -> dict[str, Any]:
    """Fetch and validate the bridge's consumer-facing API contract."""
    async with session.get(
        info_url,
        headers=request_headers(bearer_token),
        timeout=aiohttp.ClientTimeout(total=10),
    ) as response:
        if response.status == 401:
            await response.read()
            raise BridgeAuthenticationError("Bridge authentication failed")
        if response.status != 200:
            await response.read()
            raise BridgeApiError(f"Bridge returned HTTP {response.status}")
        try:
            data = await response.json(content_type=None)
        except (ValueError, aiohttp.ContentTypeError) as exc:
            raise BridgeApiError("Bridge returned invalid JSON") from exc

    if not isinstance(data, dict):
        raise BridgeApiError("Bridge returned non-object JSON")
    api_version = data.get("api_version")
    if api_version != SUPPORTED_BRIDGE_API_VERSION:
        raise BridgeVersionError(f"Bridge API version {api_version!r} is not supported")
    device = data.get("device")
    if not isinstance(device, dict) or not isinstance(device.get("id"), str):
        raise BridgeApiError("Bridge response is missing device.id")
    stream = data.get("stream")
    if not isinstance(stream, dict) or not isinstance(stream.get("url"), str):
        raise BridgeApiError("Bridge response is missing stream.url")
    if not device["id"].strip() or not stream["url"].strip():
        raise BridgeApiError("Bridge response contains blank device or stream data")
    return data


async def async_fetch_bridge_health(
    session: aiohttp.ClientSession,
    health_url: str,
    bearer_token: str | None,
) -> bool:
    """Fetch the companion's media health without reading device state."""
    async with session.get(
        health_url,
        headers=request_headers(bearer_token),
        timeout=aiohttp.ClientTimeout(total=10),
    ) as response:
        status = response.status
        if status == 401:
            await response.read()
            raise BridgeAuthenticationError("Bridge authentication failed")
        if status not in {200, 503}:
            await response.read()
            raise BridgeApiError(f"Bridge returned HTTP {status}")
        try:
            data = await response.json(content_type=None)
        except (ValueError, aiohttp.ContentTypeError) as exc:
            raise BridgeApiError("Bridge returned invalid health JSON") from exc

    if not isinstance(data, dict) or not isinstance(data.get("healthy"), bool):
        raise BridgeApiError("Bridge health response is missing healthy")
    healthy = data["healthy"]
    if healthy != (status == 200):
        raise BridgeApiError("Bridge health status and payload disagree")
    return healthy


class CradlewiseCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Merge direct local, cloud, and optional media companion state."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry[Any]) -> None:
        config = {**entry.data, **entry.options}
        bridge_url = config.get(CONF_BRIDGE_STATUS_URL)
        mode = config.get(CONF_CONNECTION_MODE, CONNECTION_MODE_LOCAL)
        uses_bridge_state = bool(bridge_url) and mode != CONNECTION_MODE_CLOUD
        monitors_bridge = bool(bridge_url)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=15 if monitors_bridge else 30),
        )
        self._entry = entry
        self._config = config
        self._session = async_get_clientsession(hass)
        self._cradle_id = entry.data[CONF_CRADLE_ID]
        self._mode = mode
        self._state = CradlewiseStateStore(self._cradle_id)
        self._command_handler = CradlewiseCommandHandler(self._state.snapshot)
        self._local_client: LocalCradleClient | None = None
        self._cloud_client: RemoteCradleClient | None = None
        self._cloud_account: CloudAccountClient | None = None
        self._credentials: LocalCredentials | None = None
        self._credential_directory: Path | None = None
        self._bridge_snapshot: dict[str, Any] | None = None
        self._bridge_command_available = False
        self._last_cloud_poll: float | None = None
        self._last_start_attempt: dict[str, float] = {}
        self._bearer_token = config.get(CONF_BEARER_TOKEN)
        self._state_url = build_state_url(bridge_url) if uses_bridge_state else None
        self._command_url = build_command_url(bridge_url) if uses_bridge_state else None
        self._health_url = (
            health_url_from_status_url(bridge_url)
            if monitors_bridge and not uses_bridge_state
            else None
        )

    @property
    def bearer_token(self) -> str | None:
        """Return the optional media companion bearer token."""
        return self._bearer_token

    @property
    def command_available(self) -> bool:
        """Return whether one unambiguous command provider is connected."""
        return bool(
            self._bridge_command_available
            or self._local_client is not None
            and self._local_client.connected
            or self._cloud_client is not None
            and self._cloud_client.connected
        )

    async def async_start(self) -> None:
        """Start the configured push providers."""
        credentials = await self.hass.async_add_executor_job(
            self._materialize_entry_credentials
        )
        self._credentials = credentials
        tasks: list[tuple[str, LocalCradleClient, asyncio.Task[None]]] = []

        if (
            self._mode in {CONNECTION_MODE_AUTOMATIC, CONNECTION_MODE_LOCAL}
            and self._state_url is None
            and credentials is not None
            and self._config.get(CONF_SERVER_CA_CERTIFICATE)
        ):
            host = str(self._config.get(CONF_LOCAL_HOST, "")).strip()
            if host:
                self._local_client = self._create_local_client(host, credentials)
                tasks.append(
                    (
                        "local",
                        self._local_client,
                        asyncio.create_task(self._local_client.async_start()),
                    )
                )

        if self._mode in {CONNECTION_MODE_AUTOMATIC, CONNECTION_MODE_CLOUD}:
            if credentials is not None:
                self._cloud_client = RemoteCradleClient(
                    host=REMOTE_MQTT_ENDPOINT,
                    cradle_id=self._cradle_id,
                    credentials=credentials,
                    update_callback=lambda update: self._handle_mqtt_update(
                        "cloud", update
                    ),
                    connection_callback=lambda connected: self._handle_connection(
                        "cloud", connected
                    ),
                )
                tasks.append(
                    (
                        "cloud",
                        self._cloud_client,
                        asyncio.create_task(self._cloud_client.async_start()),
                    )
                )
            email = self._config.get(CONF_EMAIL)
            password = self._config.get(CONF_PASSWORD)
            if email and password:
                self._cloud_account = CloudAccountClient(
                    email=str(email),
                    password=str(password),
                )

        if tasks:
            attempted_at = time.monotonic()
            self._last_start_attempt.update(
                {source: attempted_at for source, _, _ in tasks}
            )
            results = await asyncio.gather(
                *(task for _, _, task in tasks),
                return_exceptions=True,
            )
            for (source, client, _), result in zip(tasks, results, strict=True):
                if isinstance(result, BaseException):
                    self._state.mark_error(source, str(result))
                    _LOGGER.warning(
                        "Could not start Cradlewise %s MQTT provider: %s",
                        source,
                        result,
                    )
                    await client.async_stop()

    async def async_stop(self) -> None:
        """Stop push providers and remove runtime credential files."""
        clients = [
            client
            for client in (self._local_client, self._cloud_client)
            if client is not None
        ]
        if clients:
            await asyncio.gather(*(client.async_stop() for client in clients))
        if self._credential_directory is not None:
            await asyncio.to_thread(shutil.rmtree, self._credential_directory)
            self._credential_directory = None

    async def _async_update_data(self) -> dict[str, Any]:
        errors: list[str] = []
        await self._async_retry_stopped_clients()
        if self._state_url is not None:
            try:
                bridge = await async_fetch_bridge_state(
                    self._session,
                    self._state_url,
                    self._bearer_token,
                    self._cradle_id,
                )
                self._ingest_bridge(bridge)
            except (BridgeApiError, aiohttp.ClientError, TimeoutError) as exc:
                self._bridge_command_available = False
                self._mark_bridge_unavailable()
                self._state.set_connected("local", False)
                self._state.mark_error("local", str(exc))
                errors.append(f"media companion: {exc}")
        elif self._health_url is not None:
            try:
                healthy = await async_fetch_bridge_health(
                    self._session,
                    self._health_url,
                    self._bearer_token,
                )
                self._ingest_bridge_health(healthy)
                if not healthy:
                    errors.append("media companion: unhealthy")
            except (BridgeApiError, aiohttp.ClientError, TimeoutError) as exc:
                self._mark_bridge_unavailable()
                errors.append(f"media companion: {exc}")

        if self._cloud_account is not None and self._cloud_poll_due():
            self._last_cloud_poll = time.monotonic()
            try:
                payload = await self.hass.async_add_executor_job(
                    self._cloud_account.get_cradle_state,
                    self._cradle_id,
                )
                self._state.update_device_state(payload, "cloud")
            except CloudAuthenticationError as exc:
                self._entry.async_start_reauth(self.hass)
                self._state.mark_error("cloud", str(exc))
                errors.append(f"cloud REST fallback: {exc}")
            except CloudApiError as exc:
                self._state.mark_error("cloud", str(exc))
                errors.append(f"cloud REST fallback: {exc}")
            if (
                self._mode == CONNECTION_MODE_AUTOMATIC
                and self._state_url is None
                and not (
                    self._local_client is not None and self._local_client.connected
                )
            ):
                await self._async_refresh_local_endpoint()

        snapshot = self._snapshot()
        if not snapshot["device_state"]["available"] and errors:
            raise UpdateFailed("; ".join(errors))
        return snapshot

    async def async_send_command(self, command: str, value: Any) -> None:
        """Validate and send a command through exactly one provider."""
        if self._bridge_command_available and self._command_url is not None:
            try:
                build_desired(command, value)
            except CommandError as exc:
                raise HomeAssistantError(str(exc)) from exc
            await self._async_send_bridge_command(command, value)
            return

        client: LocalCradleClient | None = None
        if self._local_client is not None and self._local_client.connected:
            client = self._local_client
        elif self._cloud_client is not None and self._cloud_client.connected:
            client = self._cloud_client
        if client is None:
            raise HomeAssistantError("No Cradlewise command provider is connected")

        self._command_handler.set_publisher(client.publish_shadow)
        try:
            self._command_handler.handle_request({"command": command, "value": value})
        except (CommandError, CommandUnavailable) as exc:
            raise HomeAssistantError(str(exc)) from exc
        finally:
            self._command_handler.clear_publisher()

    async def _async_send_bridge_command(self, command: str, value: Any) -> None:
        try:
            async with self._session.post(
                self._command_url,
                headers=request_headers(self._bearer_token),
                json={"command": command, "value": value},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                detail = await response.text()
                if response.status == 401:
                    raise HomeAssistantError("Media companion authentication failed")
                if response.status != 200:
                    raise HomeAssistantError(
                        "Media companion command failed with HTTP "
                        f"{response.status}: {detail}"
                    )
        except HomeAssistantError:
            raise
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise HomeAssistantError(
                f"Media companion command request failed: {exc}"
            ) from exc
        await self.async_request_refresh()

    def _handle_mqtt_update(self, source: str, update: LocalCradleUpdate) -> None:
        if update.kind == "device_state":
            self._state.update_device_state(update.payload, source)
        elif update.kind == "cradle_state":
            if source == "local":
                self._state.update_cradle_state(update.payload)
            else:
                self._state.update_device_state(update.payload, source)
        elif update.kind == "beacon":
            self._state.update_device_state(update.payload, source)
        self.async_set_updated_data(self._snapshot())

    def _handle_connection(self, source: str, connected: bool) -> None:
        self._state.set_connected(source, connected)
        self.async_set_updated_data(self._snapshot())

    def _ingest_bridge(self, bridge: dict[str, Any]) -> None:
        self._bridge_snapshot = bridge
        mqtt_connected = strict_bool(bridge.get("mqtt", {}).get("connected")) is True
        self._bridge_command_available = mqtt_connected
        self._state.set_connected("local", mqtt_connected)
        device_state = bridge.get("device_state")
        if isinstance(device_state, dict):
            updated_at = device_state.get("updated_at")
            source = "cloud" if device_state.get("source") == "cloud" else "local"
            self._state.update_normalized_device_state(
                {
                    key: value
                    for key, value in device_state.items()
                    if key
                    not in {
                        "age_seconds",
                        "available",
                        "source",
                        "sources",
                        "stale",
                        "updated_at",
                    }
                },
                source,
                updated_at=(
                    float(updated_at) if isinstance(updated_at, int | float) else None
                ),
            )
        cradle_state = bridge.get("cradle_state")
        if isinstance(cradle_state, dict):
            updated_at = cradle_state.get("updated_at")
            self._state.update_cradle_state(
                cradle_state,
                updated_at=(
                    float(updated_at) if isinstance(updated_at, int | float) else None
                ),
            )

    def _ingest_bridge_health(self, healthy: bool) -> None:
        """Store media health without making local state or commands active."""
        self._bridge_snapshot = {
            "bridge": {
                "cradle_id": self._cradle_id,
                "healthy": healthy,
            }
        }

    def _mark_bridge_unavailable(self) -> None:
        """Keep diagnostics while making camera availability fail closed."""
        snapshot = dict(self._bridge_snapshot or {})
        bridge = dict(snapshot.get("bridge") or {})
        bridge.update({"cradle_id": self._cradle_id, "healthy": False})
        snapshot["bridge"] = bridge
        self._bridge_snapshot = snapshot

    def _snapshot(self) -> dict[str, Any]:
        snapshot = self._state.snapshot()
        if self._bridge_snapshot is None:
            return snapshot
        for key in ("analytics", "media", "sink", "webrtc"):
            value = self._bridge_snapshot.get(key)
            if isinstance(value, dict):
                snapshot[key] = value.copy()
        media_bridge = self._bridge_snapshot.get("bridge")
        if isinstance(media_bridge, dict):
            snapshot["bridge"].update(media_bridge)
            snapshot["bridge"]["provider_healthy"] = snapshot["device_state"][
                "available"
            ]
        return snapshot

    def _cloud_poll_due(self) -> bool:
        if self._last_cloud_poll is None:
            return True
        connected = self._cloud_client is not None and self._cloud_client.connected
        interval = (
            CLOUD_POLL_CONNECTED_SECONDS
            if connected
            else CLOUD_POLL_DISCONNECTED_SECONDS
        )
        return time.monotonic() - self._last_cloud_poll >= interval

    async def _async_retry_stopped_clients(self) -> None:
        """Retry providers whose initial MQTT connection did not start."""
        now = time.monotonic()
        clients = {
            "local": self._local_client,
            "cloud": self._cloud_client,
        }
        for source, client in clients.items():
            if client is None or client.started:
                continue
            if now - self._last_start_attempt.get(source, 0.0) < MQTT_RETRY_SECONDS:
                continue
            self._last_start_attempt[source] = now
            try:
                await client.async_start()
            except (LocalConnectionError, OSError, TimeoutError) as exc:
                self._state.mark_error(source, str(exc))
                _LOGGER.warning(
                    "Cradlewise %s MQTT provider retry failed: %s",
                    source,
                    exc,
                )

    async def _async_refresh_local_endpoint(self) -> None:
        """Rediscover and safely pin local MQTT after cloud-only startup."""
        if self._cloud_account is None or self._credentials is None:
            return
        try:
            host = await self.hass.async_add_executor_job(
                self._cloud_account.get_cradle_ip,
                self._cradle_id,
            )
            if not host:
                return
            server_ca = await self.hass.async_add_executor_job(
                pin_server_ca,
                host,
                self._credentials.client_cert_path,
                self._credentials.client_key_path,
            )
        except (BrokerCertificateError, CloudApiError, CloudAuthenticationError) as exc:
            self._state.mark_error("local", str(exc))
            return

        current_host = self._config.get(CONF_LOCAL_HOST)
        current_ca = self._config.get(CONF_SERVER_CA_CERTIFICATE)
        if host == current_host and server_ca == current_ca:
            return
        if current_ca and server_ca != current_ca:
            message = (
                "Local MQTT broker CA changed; use Reconfigure to trust the new "
                "broker certificate"
            )
            self._state.mark_error("local", message)
            _LOGGER.warning(message)
            return

        updated_data = {
            **self._entry.data,
            CONF_LOCAL_HOST: host,
            CONF_SERVER_CA_CERTIFICATE: server_ca,
        }
        self._config.update(updated_data)
        entry_was_loaded = self._entry.state is ConfigEntryState.LOADED
        self.hass.config_entries.async_update_entry(
            self._entry,
            data=updated_data,
        )
        if entry_was_loaded:
            return
        if self._credential_directory is None:
            return
        provisioned = ProvisionedCredentials(
            device_id=str(updated_data[CONF_DEVICE_ID]),
            client_certificate=str(updated_data[CONF_CLIENT_CERTIFICATE]),
            client_private_key=str(updated_data[CONF_CLIENT_PRIVATE_KEY]),
            group_ca_certificate=str(updated_data[CONF_GROUP_CA_CERTIFICATE]),
        )
        self._credentials = await self.hass.async_add_executor_job(
            partial(
                materialize_credentials,
                self._credential_directory,
                provisioned,
                server_ca_certificate=server_ca,
            )
        )
        if self._local_client is not None:
            await self._local_client.async_stop()
        self._local_client = self._create_local_client(host, self._credentials)
        self._last_start_attempt["local"] = time.monotonic()
        try:
            await self._local_client.async_start()
        except (LocalConnectionError, OSError, TimeoutError) as exc:
            self._state.mark_error("local", str(exc))

    def _create_local_client(
        self,
        host: str,
        credentials: LocalCredentials,
    ) -> LocalCradleClient:
        return LocalCradleClient(
            host=host,
            cradle_id=self._cradle_id,
            credentials=credentials,
            update_callback=lambda update: self._handle_mqtt_update("local", update),
            connection_callback=lambda connected: self._handle_connection(
                "local", connected
            ),
        )

    def _materialize_entry_credentials(self) -> LocalCredentials | None:
        values = {
            CONF_DEVICE_ID: self._config.get(CONF_DEVICE_ID),
            CONF_CLIENT_CERTIFICATE: self._config.get(CONF_CLIENT_CERTIFICATE),
            CONF_CLIENT_PRIVATE_KEY: self._config.get(CONF_CLIENT_PRIVATE_KEY),
            CONF_GROUP_CA_CERTIFICATE: self._config.get(CONF_GROUP_CA_CERTIFICATE),
        }
        if not all(
            isinstance(value, str) and value.strip() for value in values.values()
        ):
            return None
        provisioned = ProvisionedCredentials(
            device_id=str(values[CONF_DEVICE_ID]),
            client_certificate=str(values[CONF_CLIENT_CERTIFICATE]),
            client_private_key=str(values[CONF_CLIENT_PRIVATE_KEY]),
            group_ca_certificate=str(values[CONF_GROUP_CA_CERTIFICATE]),
        )
        directory = Path(tempfile.mkdtemp(prefix="cradlewise-"))
        self._credential_directory = directory
        server_ca = self._config.get(CONF_SERVER_CA_CERTIFICATE)
        return materialize_credentials(
            directory,
            provisioned,
            server_ca_certificate=(str(server_ca) if server_ca else None),
        )


CradlewiseStatusCoordinator = CradlewiseCoordinator
