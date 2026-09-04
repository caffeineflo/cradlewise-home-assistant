from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from cradlewise_client.cloud import CLIENT_SECRET

try:
    from homeassistant import config_entries, data_entry_flow
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.const import CONF_EMAIL, CONF_NAME, CONF_PASSWORD
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers import issue_registry as ir
    from pytest_homeassistant_custom_component.common import MockConfigEntry
except ModuleNotFoundError:
    pytest.skip(
        "Home Assistant runtime tests require the ha-test extra",
        allow_module_level=True,
    )

from cradlewise_client.certificates import BrokerCertificateError
from cradlewise_client.cloud import CradleAccount, ProvisionedCredentials, UserDevice

from custom_components.cradlewise.config_flow import (
    CradlewiseOptionsFlow,
    RegistrationNotFoundError,
)
from custom_components.cradlewise.const import (
    CONF_ALLOW_INSECURE_HTTP,
    CONF_BABY_ID,
    CONF_BEARER_TOKEN,
    CONF_BRIDGE_API_VERSION,
    CONF_BRIDGE_STATUS_URL,
    CONF_BRIDGE_VERSION,
    CONF_CLIENT_CERTIFICATE,
    CONF_CLIENT_PRIVATE_KEY,
    CONF_CONFIRM_REGISTRATION_REMOVAL,
    CONF_CONNECTION_MODE,
    CONF_CRADLE_ID,
    CONF_DEVICE_ID,
    CONF_GROUP_CA_CERTIFICATE,
    CONF_LOCAL_HOST,
    CONF_REMOVE_OLD_REGISTRATION,
    CONF_SERVER_CA_CERTIFICATE,
    CONF_SNAPSHOT_URL,
    CONF_STREAM_URL,
    CONNECTION_MODE_AUTOMATIC,
    CONNECTION_MODE_CLOUD,
    CONNECTION_MODE_LOCAL,
    DOMAIN,
)
from custom_components.cradlewise.coordinator import CradlewiseCoordinator
from custom_components.cradlewise.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.cradlewise.repairs import (
    ClientCertificateRepairFlow,
    async_update_client_certificate_issue,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.usefixtures("enable_custom_integrations"),
]

CRADLE_ID = "00000000-0000-4000-8000-000000000001"
DEVICE_ID = "00000000-0000-4000-8000-000000000002"
BRIDGE_URL = "http://bridge.test:8088"
STATE_URL = f"{BRIDGE_URL}/state"
INFO_URL = f"{BRIDGE_URL}/info"
STREAM_URL = "rtsp://bridge.test:8560/cradlewise"
TOKEN = "test-bearer-token"


def _credentials() -> ProvisionedCredentials:
    return ProvisionedCredentials(
        device_id=DEVICE_ID,
        client_certificate="client certificate",
        client_private_key="client private key",
        group_ca_certificate="group CA",
    )


def _account() -> CradleAccount:
    return CradleAccount(baby_id=42, cradle_id=CRADLE_ID, name="Nursery Crib")


def time_to_datetime(offset_seconds: int) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)


def _base_entry_data() -> dict[str, Any]:
    credentials = _credentials()
    return {
        CONF_NAME: "Nursery Crib",
        CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
        CONF_BABY_ID: 42,
        CONF_CRADLE_ID: CRADLE_ID,
        CONF_LOCAL_HOST: "192.0.2.10",
        CONF_DEVICE_ID: credentials.device_id,
        CONF_CLIENT_CERTIFICATE: credentials.client_certificate,
        CONF_CLIENT_PRIVATE_KEY: credentials.client_private_key,
        CONF_GROUP_CA_CERTIFICATE: credentials.group_ca_certificate,
        CONF_SERVER_CA_CERTIFICATE: "server CA",
    }


def _bridge_info(cradle_id: str = CRADLE_ID) -> dict[str, Any]:
    return {
        "api_version": 1,
        "bridge_version": "0.1.0",
        "device": {"id": cradle_id},
        "capabilities": {"camera": True},
        "endpoints": {"state": "/state", "snapshot": "/snapshot.jpg"},
        "stream": {"url": STREAM_URL},
    }


def _bridge_payload() -> dict[str, Any]:
    timestamp = time.time()
    return {
        "bridge": {"cradle_id": CRADLE_ID, "healthy": True},
        "mqtt": {"connected": True},
        "webrtc": {
            "connection_state": "connected",
            "ice_connection_state": "connected",
        },
        "media": {"video_track": True, "audio_track": True},
        "cradle_state": {
            "updated_at": timestamp,
            "wifi_strength": -45,
            "wifi_ssid": "crib-test",
        },
        "device_state": {
            "updated_at": timestamp,
            "baby_present": False,
            "baby_needs_attention": False,
            "baby_needs_help": False,
            "crib_helping": False,
            "light_on": False,
            "loud_sound_detected": False,
            "rocking_not_effective": False,
            "obstruction_detected": False,
            "lower_breath_rate_alert": False,
            "sleep_phase": "away",
            "sleep_state": "Baby not present",
            "bouncing": False,
            "bounce_mode": 0,
            "bounce_level": 0,
            "bounce_amplitude": 20,
            "bounce_duration": 10,
            "bounce_duration_limit": 30,
            "bounce_time_remaining": 0,
            "music_playing": False,
            "music_mode": 0,
            "music_level": 0,
            "music_volume": 25,
            "music_mood": "calm",
            "music_duration": 60,
            "music_time_remaining": 0,
            "adaptive_soothing_enabled": True,
            "max_bounce_limit": 60,
            "max_volume_limit": 80,
            "software_version": "0.2.72",
        },
    }


def _bridge_entry_data() -> dict[str, Any]:
    return {
        **_base_entry_data(),
        CONF_BRIDGE_STATUS_URL: BRIDGE_URL,
        CONF_BEARER_TOKEN: TOKEN,
        CONF_STREAM_URL: STREAM_URL,
        CONF_SNAPSHOT_URL: f"{BRIDGE_URL}/snapshot.jpg",
        CONF_BRIDGE_API_VERSION: 1,
        CONF_BRIDGE_VERSION: "0.1.0",
    }


def _mock_cloud_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "custom_components.cradlewise.config_flow.CloudAccountClient.authenticate",
        lambda self: None,
    )
    monkeypatch.setattr(
        "custom_components.cradlewise.config_flow.CloudAccountClient.list_accounts",
        lambda self: [_account()],
    )
    monkeypatch.setattr(
        "custom_components.cradlewise.config_flow.CloudAccountClient.provision_credentials",
        lambda self, account, **kwargs: _credentials(),
    )
    monkeypatch.setattr(
        "custom_components.cradlewise.config_flow.CloudAccountClient.get_cradle_ip",
        lambda self, cradle_id: "192.0.2.10",
    )
    monkeypatch.setattr(
        "custom_components.cradlewise.config_flow._pin_credentials",
        lambda credentials, host: "server CA",
    )


async def _start_account_flow(
    hass: HomeAssistant,
    mode: str,
) -> dict[str, Any]:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={CONF_CONNECTION_MODE: mode},
    )
    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == f"account_{mode}"
    return await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_EMAIL: "parent@example.com", CONF_PASSWORD: "secret"},
    )


async def test_automatic_setup_retains_cloud_credentials_and_provisions_local(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_cloud_setup(monkeypatch)

    result = await _start_account_flow(hass, CONNECTION_MODE_AUTOMATIC)

    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Nursery Crib"
    assert result["data"][CONF_CONNECTION_MODE] == CONNECTION_MODE_AUTOMATIC
    assert result["data"][CONF_EMAIL] == "parent@example.com"
    assert result["data"][CONF_PASSWORD] == "secret"
    assert result["data"][CONF_LOCAL_HOST] == "192.0.2.10"
    assert result["data"][CONF_SERVER_CA_CERTIFICATE] == "server CA"


async def test_local_only_setup_discards_account_credentials(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_cloud_setup(monkeypatch)

    result = await _start_account_flow(hass, CONNECTION_MODE_LOCAL)

    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert CONF_EMAIL not in result["data"]
    assert CONF_PASSWORD not in result["data"]


async def test_cloud_only_setup_does_not_require_local_discovery(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_cloud_setup(monkeypatch)

    def fail_local_discovery(self: object, cradle_id: str) -> str:
        raise AssertionError("cloud-only setup must not discover the local broker")

    monkeypatch.setattr(
        "custom_components.cradlewise.config_flow.CloudAccountClient.get_cradle_ip",
        fail_local_discovery,
    )

    result = await _start_account_flow(hass, CONNECTION_MODE_CLOUD)

    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CONNECTION_MODE] == CONNECTION_MODE_CLOUD
    assert CONF_LOCAL_HOST not in result["data"]
    assert CONF_SERVER_CA_CERTIFICATE not in result["data"]


async def test_automatic_setup_continues_when_the_local_broker_is_offline(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_cloud_setup(monkeypatch)

    def fail_pin(credentials: ProvisionedCredentials, host: str) -> str:
        raise OSError("local broker unavailable")

    monkeypatch.setattr(
        "custom_components.cradlewise.config_flow._pin_credentials",
        fail_pin,
    )

    result = await _start_account_flow(hass, CONNECTION_MODE_AUTOMATIC)

    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_EMAIL] == "parent@example.com"
    assert CONF_LOCAL_HOST not in result["data"]
    assert CONF_SERVER_CA_CERTIFICATE not in result["data"]


async def test_automatic_setup_reports_cloud_provisioning_io_failure(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_cloud_setup(monkeypatch)

    def fail_provisioning(self: object, account: CradleAccount, **kwargs: Any) -> None:
        raise OSError("certificate service unavailable")

    monkeypatch.setattr(
        "custom_components.cradlewise.config_flow.CloudAccountClient.provision_credentials",
        fail_provisioning,
    )

    result = await _start_account_flow(hass, CONNECTION_MODE_AUTOMATIC)

    assert (result["type"], result["reason"]) == (
        data_entry_flow.FlowResultType.ABORT,
        "cannot_connect",
    )


async def test_reconfigure_switches_to_local_only_without_replacing_identity(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "custom_components.cradlewise.config_flow._pin_credentials",
        lambda credentials, host: "refreshed server CA",
    )
    schedule_reload = Mock()
    monkeypatch.setattr(
        hass.config_entries,
        "async_schedule_reload",
        schedule_reload,
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nursery Crib",
        unique_id=CRADLE_ID,
        data={
            **_base_entry_data(),
            CONF_CONNECTION_MODE: CONNECTION_MODE_AUTOMATIC,
            CONF_EMAIL: "parent@example.com",
            CONF_PASSWORD: "old-secret",
        },
        version=1,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_CONNECTION_MODE: CONNECTION_MODE_LOCAL,
            CONF_EMAIL: "",
            CONF_PASSWORD: "",
            CONF_LOCAL_HOST: "192.0.2.10",
        },
    )

    assert result["reason"] == "reconfigure_successful"
    assert entry.unique_id == CRADLE_ID
    assert entry.data[CONF_CONNECTION_MODE] == CONNECTION_MODE_LOCAL
    assert entry.data[CONF_SERVER_CA_CERTIFICATE] == "refreshed server CA"
    assert CONF_EMAIL not in entry.data
    assert CONF_PASSWORD not in entry.data
    assert schedule_reload.call_count == 0


async def test_reconfigure_repins_a_changed_local_broker_address(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_cloud_setup(monkeypatch)
    pin_calls: list[str] = []

    def pin_changed_host(credentials: ProvisionedCredentials, host: str) -> str:
        pin_calls.append(host)
        return "new server CA"

    monkeypatch.setattr(
        "custom_components.cradlewise.config_flow._pin_credentials",
        pin_changed_host,
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nursery Crib",
        unique_id=CRADLE_ID,
        data={
            **_base_entry_data(),
            CONF_CONNECTION_MODE: CONNECTION_MODE_AUTOMATIC,
            CONF_EMAIL: "parent@example.com",
            CONF_PASSWORD: "old-secret",
        },
        version=1,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_CONNECTION_MODE: CONNECTION_MODE_AUTOMATIC,
            CONF_EMAIL: "parent@example.com",
            CONF_PASSWORD: "",
            CONF_LOCAL_HOST: "192.0.2.11",
        },
    )

    assert result["reason"] == "reconfigure_successful"
    assert pin_calls == ["192.0.2.11"]
    assert entry.data[CONF_LOCAL_HOST] == "192.0.2.11"
    assert entry.data[CONF_SERVER_CA_CERTIFICATE] == "new server CA"


async def test_reconfigure_repins_an_automatic_entry_at_the_same_address(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_cloud_setup(monkeypatch)
    monkeypatch.setattr(
        "custom_components.cradlewise.config_flow._pin_credentials",
        lambda credentials, host: "rotated server CA",
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nursery Crib",
        unique_id=CRADLE_ID,
        data={
            **_base_entry_data(),
            CONF_CONNECTION_MODE: CONNECTION_MODE_AUTOMATIC,
            CONF_EMAIL: "parent@example.com",
            CONF_PASSWORD: "old-secret",
        },
        version=1,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_CONNECTION_MODE: CONNECTION_MODE_AUTOMATIC,
            CONF_EMAIL: "parent@example.com",
            CONF_PASSWORD: "",
            CONF_LOCAL_HOST: "192.0.2.10",
        },
    )

    assert (
        result["reason"],
        entry.data[CONF_SERVER_CA_CERTIFICATE],
    ) == ("reconfigure_successful", "rotated server CA")


async def test_reconfigure_cloud_only_to_automatic_discovers_local_address(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_cloud_setup(monkeypatch)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nursery Crib",
        unique_id=CRADLE_ID,
        data={
            key: value
            for key, value in _base_entry_data().items()
            if key not in {CONF_LOCAL_HOST, CONF_SERVER_CA_CERTIFICATE}
        }
        | {
            CONF_CONNECTION_MODE: CONNECTION_MODE_CLOUD,
            CONF_EMAIL: "parent@example.com",
            CONF_PASSWORD: "old-secret",
        },
        version=1,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_CONNECTION_MODE: CONNECTION_MODE_AUTOMATIC,
            CONF_EMAIL: "parent@example.com",
            CONF_PASSWORD: "",
            CONF_LOCAL_HOST: "",
        },
    )

    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_LOCAL_HOST] == "192.0.2.10"
    assert entry.data[CONF_SERVER_CA_CERTIFICATE] == "server CA"


async def test_reauth_updates_credentials_for_the_existing_cradle(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_cloud_setup(monkeypatch)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nursery Crib",
        unique_id=CRADLE_ID,
        data={
            **_base_entry_data(),
            CONF_CONNECTION_MODE: CONNECTION_MODE_AUTOMATIC,
            CONF_EMAIL: "parent@example.com",
            CONF_PASSWORD: "old-secret",
        },
        version=1,
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=dict(entry.data),
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_EMAIL: "new-parent@example.com",
            CONF_PASSWORD: "new-secret",
        },
    )

    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_EMAIL] == "new-parent@example.com"
    assert entry.data[CONF_PASSWORD] == "new-secret"


async def test_media_options_validate_identity_and_derive_endpoints(
    hass: HomeAssistant,
    aioclient_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nursery Crib",
        unique_id=CRADLE_ID,
        data=_base_entry_data(),
        version=1,
    )
    entry.add_to_hass(hass)
    monkeypatch.setattr(
        "custom_components.cradlewise.config_flow.http_url_resolves_to_private_network",
        lambda url: True,
    )
    aioclient_mock.get(INFO_URL, json=_bridge_info())

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"next_step_id": "media"},
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_BRIDGE_STATUS_URL: BRIDGE_URL,
            CONF_BEARER_TOKEN: TOKEN,
            CONF_ALLOW_INSECURE_HTTP: True,
        },
    )

    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_STREAM_URL] == STREAM_URL
    assert result["data"][CONF_SNAPSHOT_URL] == f"{BRIDGE_URL}/snapshot.jpg"
    assert result["data"][CONF_ALLOW_INSECURE_HTTP] is True


async def test_media_options_reject_a_different_cradle(
    hass: HomeAssistant,
    aioclient_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nursery Crib",
        unique_id=CRADLE_ID,
        data=_base_entry_data(),
        version=1,
    )
    flow = CradlewiseOptionsFlow(entry)
    flow.hass = hass
    monkeypatch.setattr(
        "custom_components.cradlewise.config_flow.http_url_resolves_to_private_network",
        lambda url: True,
    )
    aioclient_mock.get(
        INFO_URL,
        json=_bridge_info("00000000-0000-4000-8000-000000000099"),
    )

    result = await flow.async_step_media(
        {
            CONF_BRIDGE_STATUS_URL: BRIDGE_URL,
            CONF_BEARER_TOKEN: TOKEN,
            CONF_ALLOW_INSECURE_HTTP: True,
        }
    )

    assert result["errors"] == {"base": "wrong_cradle"}


async def test_media_options_require_confirmation_for_private_http(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nursery Crib",
        unique_id=CRADLE_ID,
        data=_base_entry_data(),
        version=1,
    )
    flow = CradlewiseOptionsFlow(entry)
    flow.hass = hass
    monkeypatch.setattr(
        "custom_components.cradlewise.config_flow.http_url_resolves_to_private_network",
        lambda url: True,
    )

    result = await flow.async_step_media(
        {CONF_BRIDGE_STATUS_URL: BRIDGE_URL, CONF_BEARER_TOKEN: TOKEN}
    )

    assert result["errors"] == {"base": "insecure_http_requires_confirmation"}


async def test_media_options_reject_public_http_before_sending_token(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nursery Crib",
        unique_id=CRADLE_ID,
        data=_base_entry_data(),
        version=1,
    )
    flow = CradlewiseOptionsFlow(entry)
    flow.hass = hass
    monkeypatch.setattr(
        "custom_components.cradlewise.config_flow.http_url_resolves_to_private_network",
        lambda url: False,
    )

    result = await flow.async_step_media(
        {
            CONF_BRIDGE_STATUS_URL: BRIDGE_URL,
            CONF_BEARER_TOKEN: TOKEN,
            CONF_ALLOW_INSECURE_HTTP: True,
        }
    )

    assert result["errors"] == {"base": "insecure_public_http"}


async def test_registration_cleanup_removes_only_current_device_and_entry(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nursery Crib",
        unique_id=CRADLE_ID,
        data={
            **_base_entry_data(),
            CONF_EMAIL: "parent@example.com",
            CONF_PASSWORD: "stored-secret",
        },
        version=1,
    )
    entry.add_to_hass(hass)
    removed: list[list[str]] = []
    monkeypatch.setattr(
        "custom_components.cradlewise.config_flow.CloudAccountClient.authenticate",
        lambda self: None,
    )
    monkeypatch.setattr(
        "custom_components.cradlewise.config_flow.CloudAccountClient.list_accounts",
        lambda self: [_account()],
    )
    monkeypatch.setattr(
        "custom_components.cradlewise.config_flow.CloudAccountClient.list_user_devices",
        lambda self, account: [UserDevice(DEVICE_ID, "Pixel", "android", None)],
    )
    monkeypatch.setattr(
        "custom_components.cradlewise.config_flow.CloudAccountClient.remove_user_devices",
        lambda self, account, device_ids: removed.append(device_ids) or device_ids,
    )

    flow = CradlewiseOptionsFlow(entry)
    flow.hass = hass
    result = await flow.async_step_remove_registration(
        {
            CONF_EMAIL: "parent@example.com",
            CONF_PASSWORD: "",
            CONF_CONFIRM_REGISTRATION_REMOVAL: True,
        }
    )

    assert (
        result["reason"],
        removed,
        hass.config_entries.async_get_entry(entry.entry_id),
    ) == (
        "registration_removed",
        [[DEVICE_ID]],
        None,
    )


async def test_registration_cleanup_refuses_an_unknown_device(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nursery Crib",
        unique_id=CRADLE_ID,
        data=_base_entry_data(),
        version=1,
    )
    flow = CradlewiseOptionsFlow(entry)
    flow.hass = hass
    monkeypatch.setattr(
        "custom_components.cradlewise.config_flow.CloudAccountClient.authenticate",
        lambda self: None,
    )
    monkeypatch.setattr(
        "custom_components.cradlewise.config_flow.CloudAccountClient.list_accounts",
        lambda self: [_account()],
    )
    monkeypatch.setattr(
        "custom_components.cradlewise.config_flow.CloudAccountClient.list_user_devices",
        lambda self, account: [],
    )

    with pytest.raises(RegistrationNotFoundError):
        flow._remove_registration("parent@example.com", "secret")


async def test_registration_cleanup_requires_explicit_confirmation(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nursery Crib",
        unique_id=CRADLE_ID,
        data=_base_entry_data(),
        version=1,
    )
    flow = CradlewiseOptionsFlow(entry)
    flow.hass = hass
    remove_registration = Mock()
    monkeypatch.setattr(flow, "_remove_registration", remove_registration)

    result = await flow.async_step_remove_registration(
        {
            CONF_EMAIL: "parent@example.com",
            CONF_PASSWORD: "secret",
            CONF_CONFIRM_REGISTRATION_REMOVAL: False,
        }
    )

    assert (result["errors"], remove_registration.call_count) == (
        {"base": "registration_removal_not_confirmed"},
        0,
    )


async def test_invalid_client_certificate_creates_fixable_repair(
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nursery Crib",
        unique_id=CRADLE_ID,
        data=_base_entry_data(),
        version=1,
    )
    entry.add_to_hass(hass)

    async_update_client_certificate_issue(hass, entry)

    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"client_certificate_{entry.entry_id}"
    )
    assert (issue.translation_key, issue.is_fixable, issue.severity) == (
        "client_certificate_invalid",
        True,
        ir.IssueSeverity.ERROR,
    )


@pytest.mark.parametrize(
    ("expires_in", "translation_key", "severity"),
    [
        (timedelta(minutes=-1), "client_certificate_expired", ir.IssueSeverity.ERROR),
        (timedelta(days=10), "client_certificate_expiring", ir.IssueSeverity.WARNING),
    ],
)
async def test_client_certificate_date_issues_are_classified(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    expires_in: timedelta,
    translation_key: str,
    severity: ir.IssueSeverity,
) -> None:
    current = datetime(2026, 9, 3, tzinfo=timezone.utc)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nursery Crib",
        unique_id=CRADLE_ID,
        data=_base_entry_data(),
        version=1,
    )
    entry.add_to_hass(hass)
    monkeypatch.setattr(
        "custom_components.cradlewise.repairs.client_certificate_validity",
        lambda pem: (current - timedelta(days=1), current + expires_in),
    )

    async_update_client_certificate_issue(hass, entry, now=current)

    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"client_certificate_{entry.entry_id}"
    )
    assert (issue.translation_key, issue.severity) == (translation_key, severity)


async def test_healthy_client_certificate_clears_existing_repair(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = datetime(2026, 9, 3, tzinfo=timezone.utc)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nursery Crib",
        unique_id=CRADLE_ID,
        data=_base_entry_data(),
        version=1,
    )
    entry.add_to_hass(hass)
    async_update_client_certificate_issue(hass, entry, now=current)
    monkeypatch.setattr(
        "custom_components.cradlewise.repairs.client_certificate_validity",
        lambda pem: (current - timedelta(days=1), current + timedelta(days=365)),
    )

    async_update_client_certificate_issue(hass, entry, now=current)

    assert (
        ir.async_get(hass).async_get_issue(
            DOMAIN, f"client_certificate_{entry.entry_id}"
        )
        is None
    )


async def test_certificate_repair_preserves_identity_and_can_remove_old_registration(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nursery Crib",
        unique_id=CRADLE_ID,
        data={
            **_base_entry_data(),
            CONF_CONNECTION_MODE: CONNECTION_MODE_AUTOMATIC,
            CONF_EMAIL: "parent@example.com",
            CONF_PASSWORD: "old-secret",
        },
        version=1,
    )
    entry.add_to_hass(hass)
    old_entry_id = entry.entry_id
    replacement = ProvisionedCredentials(
        device_id="replacement-device",
        client_certificate="replacement certificate",
        client_private_key="replacement private key",
        group_ca_certificate="replacement group CA",
    )
    removed: list[list[str]] = []
    _mock_cloud_setup(monkeypatch)
    monkeypatch.setattr(
        "custom_components.cradlewise.repairs.CloudAccountClient.provision_credentials",
        lambda self, account, **kwargs: replacement,
    )
    monkeypatch.setattr(
        "custom_components.cradlewise.repairs.CloudAccountClient.list_user_devices",
        lambda self, account: [UserDevice(DEVICE_ID, "Pixel", "android", None)],
    )
    monkeypatch.setattr(
        "custom_components.cradlewise.repairs.CloudAccountClient.remove_user_devices",
        lambda self, account, device_ids: removed.append(device_ids) or device_ids,
    )
    monkeypatch.setattr(
        "custom_components.cradlewise.repairs.client_certificate_validity",
        lambda pem: (time_to_datetime(-60), time_to_datetime(3600)),
    )
    monkeypatch.setattr(
        "custom_components.cradlewise.repairs._pin_credentials",
        lambda credentials, host: "replacement server CA",
    )
    schedule_reload = Mock()
    monkeypatch.setattr(hass.config_entries, "async_schedule_reload", schedule_reload)
    flow = ClientCertificateRepairFlow(entry)
    flow.hass = hass

    result = await flow.async_step_reprovision(
        {
            CONF_EMAIL: "parent@example.com",
            CONF_PASSWORD: "new-secret",
            CONF_REMOVE_OLD_REGISTRATION: True,
        }
    )

    assert (
        result["type"],
        entry.entry_id,
        entry.unique_id,
        entry.data[CONF_DEVICE_ID],
        removed,
    ) == (
        data_entry_flow.FlowResultType.CREATE_ENTRY,
        old_entry_id,
        CRADLE_ID,
        "replacement-device",
        [[DEVICE_ID]],
    )


async def test_certificate_repair_rolls_back_registration_when_local_pin_fails(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nursery Crib",
        unique_id=CRADLE_ID,
        data=_base_entry_data(),
        version=1,
    )
    replacement = ProvisionedCredentials(
        device_id="replacement-device",
        client_certificate="replacement certificate",
        client_private_key="replacement private key",
        group_ca_certificate="replacement group CA",
    )
    removed: list[list[str]] = []
    _mock_cloud_setup(monkeypatch)
    monkeypatch.setattr(
        "custom_components.cradlewise.repairs.CloudAccountClient.provision_credentials",
        lambda self, account, **kwargs: replacement,
    )
    monkeypatch.setattr(
        "custom_components.cradlewise.repairs.CloudAccountClient.remove_user_devices",
        lambda self, account, device_ids: removed.append(device_ids) or device_ids,
    )
    monkeypatch.setattr(
        "custom_components.cradlewise.repairs.client_certificate_validity",
        lambda pem: (time_to_datetime(-60), time_to_datetime(3600)),
    )
    monkeypatch.setattr(
        "custom_components.cradlewise.repairs._pin_credentials",
        Mock(side_effect=BrokerCertificateError("offline")),
    )
    flow = ClientCertificateRepairFlow(entry)
    flow.hass = hass

    result = await flow.async_step_reprovision(
        {
            CONF_EMAIL: "parent@example.com",
            CONF_PASSWORD: "secret",
            CONF_REMOVE_OLD_REGISTRATION: False,
        }
    )

    assert (result["errors"], removed, entry.data[CONF_DEVICE_ID]) == (
        {"base": "cannot_connect_local"},
        [["replacement-device"]],
        DEVICE_ID,
    )


async def test_setup_with_media_creates_only_focused_entity_surface(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    aioclient_mock.get(STATE_URL, json=_bridge_payload())
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nursery Crib",
        unique_id=CRADLE_ID,
        data=_bridge_entry_data(),
        version=1,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entries = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    enabled = sum(item.disabled_by is None for item in entries)
    disabled = sum(
        item.disabled_by is er.RegistryEntryDisabler.INTEGRATION for item in entries
    )
    assert entry.state is ConfigEntryState.LOADED
    assert (enabled, disabled, len(entries)) == (29, 2, 31)
    assert any(item.domain == "camera" for item in entries)


async def test_setup_without_media_creates_no_camera(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_start(self: CradlewiseCoordinator) -> None:
        return None

    async def direct_snapshot(self: CradlewiseCoordinator) -> dict[str, Any]:
        self._ingest_bridge(_bridge_payload())
        return self._snapshot()

    monkeypatch.setattr(CradlewiseCoordinator, "async_start", no_start)
    monkeypatch.setattr(CradlewiseCoordinator, "_async_update_data", direct_snapshot)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nursery Crib",
        unique_id=CRADLE_ID,
        data=_base_entry_data(),
        version=1,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    entries = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert len(entries) == 30
    assert all(item.domain != "camera" for item in entries)


async def test_diagnostics_redact_all_credentials(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    aioclient_mock.get(STATE_URL, json=_bridge_payload())
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nursery Crib",
        unique_id=CRADLE_ID,
        data={
            **_bridge_entry_data(),
            CONF_EMAIL: "parent@example.com",
            CONF_PASSWORD: "secret",
        },
        version=1,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    serialized = str(diagnostics)
    assert "secret" not in serialized
    assert CLIENT_SECRET not in serialized
    assert "parent@example.com" not in serialized
    assert "client private key" not in serialized
    assert "192.0.2.10" not in serialized
    assert diagnostics["config_entry"][CONF_BABY_ID] != 42
    assert diagnostics["coordinator"]["active_provider"] == "local"
    assert "error" not in diagnostics["coordinator"]["providers"]["local"]


async def test_diagnostics_report_an_unloaded_entry(
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nursery Crib",
        unique_id=CRADLE_ID,
        data=_base_entry_data(),
        version=1,
    )
    entry.add_to_hass(hass)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["coordinator"] == {
        "loaded": False,
        "last_update_success": False,
        "command_available": False,
        "active_provider": None,
        "providers": {},
    }


async def test_unload_stops_provider_clients(
    hass: HomeAssistant,
    aioclient_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aioclient_mock.get(STATE_URL, json=_bridge_payload())
    stop = AsyncMock()
    monkeypatch.setattr(CradlewiseCoordinator, "async_stop", stop)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nursery Crib",
        unique_id=CRADLE_ID,
        data=_bridge_entry_data(),
        version=1,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert stop.await_count == 1
