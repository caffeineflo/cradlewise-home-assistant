from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from cradlewise_client.cloud import CloudAuthenticationError

try:
    from homeassistant import config_entries
    from homeassistant.const import CONF_EMAIL, CONF_NAME, CONF_PASSWORD
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.update_coordinator import UpdateFailed
    from pytest_homeassistant_custom_component.common import MockConfigEntry
except ModuleNotFoundError:
    pytest.skip(
        "Home Assistant runtime tests require the ha-test extra",
        allow_module_level=True,
    )

from custom_components.cradlewise.const import (
    CONF_BABY_ID,
    CONF_BEARER_TOKEN,
    CONF_BRIDGE_STATUS_URL,
    CONF_CONNECTION_MODE,
    CONF_CRADLE_ID,
    CONF_LOCAL_HOST,
    CONF_SERVER_CA_CERTIFICATE,
    CONNECTION_MODE_AUTOMATIC,
    CONNECTION_MODE_CLOUD,
    DOMAIN,
)
from custom_components.cradlewise.coordinator import (
    MQTT_RETRY_SECONDS,
    CradlewiseCoordinator,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.usefixtures("enable_custom_integrations"),
]

CRADLE_ID = "00000000-0000-4000-8000-000000000001"
BRIDGE_URL = "http://bridge.test:8088"


class FakeClient:
    def __init__(self, connected: bool) -> None:
        self.connected = connected
        self.started = connected
        self.published: list[dict[str, Any]] = []
        self.async_start = AsyncMock()

    def publish_shadow(self, payload: dict[str, Any]) -> None:
        self.published.append(payload)


def _entry(**overrides: Any) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Nursery Crib",
        unique_id=CRADLE_ID,
        data={
            CONF_NAME: "Nursery Crib",
            CONF_BABY_ID: 42,
            CONF_CRADLE_ID: CRADLE_ID,
            CONF_CONNECTION_MODE: CONNECTION_MODE_AUTOMATIC,
            **overrides,
        },
        version=1,
    )


async def test_command_prefers_local_and_falls_back_to_cloud(
    hass: HomeAssistant,
) -> None:
    coordinator = CradlewiseCoordinator(hass, _entry())
    local = FakeClient(connected=True)
    cloud = FakeClient(connected=True)
    coordinator._local_client = local
    coordinator._cloud_client = cloud

    await coordinator.async_send_command("actuator_on", True)
    local.connected = False
    await coordinator.async_send_command("actuator_on", False)

    assert local.published == [{"state": {"desired": {"actuator": {"on": True}}}}]
    assert cloud.published == [{"state": {"desired": {"actuator": {"on": False}}}}]


async def test_start_materializes_credentials_outside_event_loop(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = CradlewiseCoordinator(hass, _entry())
    materialize_thread_id = None

    def materialize() -> None:
        nonlocal materialize_thread_id
        materialize_thread_id = threading.get_ident()

    monkeypatch.setattr(coordinator, "_materialize_entry_credentials", materialize)

    await coordinator.async_start()

    assert materialize_thread_id != threading.get_ident()


async def test_media_companion_is_the_only_local_command_publisher(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    coordinator = CradlewiseCoordinator(
        hass,
        _entry(
            **{
                CONF_BRIDGE_STATUS_URL: BRIDGE_URL,
                CONF_BEARER_TOKEN: "token",
            }
        ),
    )
    cloud = FakeClient(connected=True)
    coordinator._cloud_client = cloud
    coordinator._bridge_command_available = True
    aioclient_mock.post(f"{BRIDGE_URL}/command", text="ok")
    coordinator.async_request_refresh = AsyncMock()

    await coordinator.async_send_command("actuator_on", True)

    assert cloud.published == []
    assert aioclient_mock.mock_calls[-1][2] == {
        "command": "actuator_on",
        "value": True,
    }


async def test_cloud_only_reads_only_media_health(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    coordinator = CradlewiseCoordinator(
        hass,
        _entry(
            **{
                CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD,
                CONF_BRIDGE_STATUS_URL: BRIDGE_URL,
                CONF_BEARER_TOKEN: "token",
            }
        ),
    )
    aioclient_mock.get(f"{BRIDGE_URL}/health", json={"healthy": True})

    snapshot = await coordinator._async_update_data()

    assert (
        snapshot["device_state"]["available"],
        snapshot["device_state"]["baby_present"],
        snapshot["bridge"]["healthy"],
        aioclient_mock.call_count,
    ) == (False, None, True, 1)


async def test_cloud_only_media_health_fails_closed_without_hiding_cloud_state(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    coordinator = CradlewiseCoordinator(
        hass,
        _entry(
            **{
                CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD,
                CONF_BRIDGE_STATUS_URL: BRIDGE_URL,
                CONF_BEARER_TOKEN: "token",
            }
        ),
    )
    coordinator._state.set_connected("cloud", True)
    coordinator._state.update_device_state(
        {"state": {"reported": {"babyPresent": False}}},
        "cloud",
    )
    aioclient_mock.get(
        f"{BRIDGE_URL}/health",
        status=503,
        json={"healthy": False},
    )

    snapshot = await coordinator._async_update_data()

    assert (
        snapshot["device_state"]["available"],
        snapshot["providers"]["active"],
        snapshot["bridge"]["healthy"],
    ) == (True, "cloud", False)


async def test_cloud_auth_failure_starts_reauth_without_hiding_local_state(
    hass: HomeAssistant,
) -> None:
    entry = _entry(
        **{
            CONF_EMAIL: "parent@example.com",
            CONF_PASSWORD: "expired-secret",
        }
    )
    entry.add_to_hass(hass)
    coordinator = CradlewiseCoordinator(hass, entry)
    coordinator._cloud_account = SimpleNamespace(
        get_cradle_state=Mock(
            side_effect=CloudAuthenticationError("credentials rejected")
        )
    )
    coordinator._state.set_connected("local", True)
    coordinator._state.update_device_state(
        {"state": {"reported": {"babyPresent": False}}},
        "local",
    )

    snapshot = await coordinator._async_update_data()
    await hass.async_block_till_done()

    active_flows = list(
        entry.async_get_active_flows(
            hass,
            {config_entries.SOURCE_REAUTH},
        )
    )
    assert (snapshot["device_state"]["available"], len(active_flows)) == (True, 1)


async def test_cloud_only_auth_failure_is_unavailable_and_starts_reauth(
    hass: HomeAssistant,
) -> None:
    entry = _entry(
        **{
            CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD,
            CONF_EMAIL: "parent@example.com",
            CONF_PASSWORD: "expired-secret",
        }
    )
    entry.add_to_hass(hass)
    coordinator = CradlewiseCoordinator(hass, entry)
    coordinator._cloud_account = SimpleNamespace(
        get_cradle_state=Mock(
            side_effect=CloudAuthenticationError("credentials rejected")
        )
    )

    with pytest.raises(UpdateFailed, match="credentials rejected"):
        await coordinator._async_update_data()
    await hass.async_block_till_done()

    active_flows = list(
        entry.async_get_active_flows(
            hass,
            {config_entries.SOURCE_REAUTH},
        )
    )
    assert len(active_flows) == 1


async def test_stopped_mqtt_provider_is_retried_with_backoff(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = CradlewiseCoordinator(hass, _entry())
    cloud = FakeClient(connected=False)
    coordinator._cloud_client = cloud
    coordinator._last_start_attempt["cloud"] = 10
    monkeypatch.setattr(
        "custom_components.cradlewise.coordinator.time.monotonic",
        lambda: 10 + MQTT_RETRY_SECONDS,
    )

    await coordinator._async_retry_stopped_clients()

    assert cloud.async_start.await_count == 1


async def test_local_rediscovery_accepts_a_new_address_with_the_pinned_ca(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = _entry(
        **{
            CONF_LOCAL_HOST: "192.0.2.10",
            CONF_SERVER_CA_CERTIFICATE: "pinned CA",
        }
    )
    entry.add_to_hass(hass)
    coordinator = CradlewiseCoordinator(hass, entry)
    coordinator._cloud_account = SimpleNamespace(
        get_cradle_ip=lambda cradle_id: "192.0.2.11"
    )
    coordinator._credentials = SimpleNamespace(
        client_cert_path="client.pem",
        client_key_path="client.key",
    )
    monkeypatch.setattr(
        "custom_components.cradlewise.coordinator.pin_server_ca",
        lambda host, client_certificate_path, client_private_key_path: "pinned CA",
    )

    await coordinator._async_refresh_local_endpoint()

    assert entry.data[CONF_LOCAL_HOST] == "192.0.2.11"


async def test_local_rediscovery_rejects_a_changed_broker_ca(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = _entry(
        **{
            CONF_LOCAL_HOST: "192.0.2.10",
            CONF_SERVER_CA_CERTIFICATE: "pinned CA",
        }
    )
    entry.add_to_hass(hass)
    coordinator = CradlewiseCoordinator(hass, entry)
    coordinator._cloud_account = SimpleNamespace(
        get_cradle_ip=lambda cradle_id: "192.0.2.11"
    )
    coordinator._credentials = SimpleNamespace(
        client_cert_path="client.pem",
        client_key_path="client.key",
    )
    monkeypatch.setattr(
        "custom_components.cradlewise.coordinator.pin_server_ca",
        lambda host, client_certificate_path, client_private_key_path: "different CA",
    )

    await coordinator._async_refresh_local_endpoint()

    assert (
        entry.data[CONF_LOCAL_HOST],
        entry.data[CONF_SERVER_CA_CERTIFICATE],
    ) == ("192.0.2.10", "pinned CA")


async def test_command_availability_accepts_any_single_healthy_provider(
    hass: HomeAssistant,
) -> None:
    coordinator = CradlewiseCoordinator(hass, _entry())
    coordinator._local_client = SimpleNamespace(connected=False)
    coordinator._cloud_client = SimpleNamespace(connected=True)

    assert coordinator.command_available is True
