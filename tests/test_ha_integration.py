from __future__ import annotations

import time
from copy import deepcopy
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

try:
    from homeassistant import config_entries, data_entry_flow
    from homeassistant.components.camera import Camera
    from homeassistant.components.camera.const import DATA_CAMERA_PREFS
    from homeassistant.components.stream import HLS_PROVIDER
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.const import CONF_NAME, STATE_UNAVAILABLE
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers import entity_registry as er
    from homeassistant.helpers.update_coordinator import UpdateFailed
    from pytest_homeassistant_custom_component.common import MockConfigEntry
except ModuleNotFoundError:
    pytest.skip(
        "Home Assistant runtime tests require the ha-test extra",
        allow_module_level=True,
    )

from custom_components.cradlewise_local import async_migrate_entry
from custom_components.cradlewise_local.camera import CradlewiseBridgeCamera
from custom_components.cradlewise_local.const import (
    CONF_BEARER_TOKEN,
    CONF_BRIDGE_STATUS_URL,
    CONF_CRADLE_ID,
    CONF_SNAPSHOT_URL,
    CONF_STREAM_URL,
    DOMAIN,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.usefixtures("enable_custom_integrations"),
]

CRADLE_ID = "00000000-0000-4000-8000-000000000001"
BRIDGE_URL = "http://bridge.test:8088"
STATE_URL = f"{BRIDGE_URL}/state"
STREAM_URL = "rtsp://bridge.test:8560/cradlewise"
TOKEN = "test-bearer-token"

ANCHOR_KEYS = {
    "baby_present",
    "baby_needs_attention",
    "baby_needs_help",
    "loud_sound_detected",
    "sleep_phase",
    "sleep_state",
}

ANALYTICS_VALUES = {
    "total_sleep_today": 120,
    "day_sleep_today": 30,
    "night_sleep_today": 90,
    "naps_today": 2,
    "longest_stretch_today": 90,
    "soothes_today": 3,
}


def _bridge_payload(*, updated_at: float | None = None) -> dict[str, Any]:
    timestamp = time.time() if updated_at is None else updated_at
    return {
        "bridge": {
            "cradle_id": CRADLE_ID,
            "healthy": True,
        },
        "mqtt": {"connected": True},
        "webrtc": {
            "connection_state": "connected",
            "ice_connection_state": "connected",
        },
        "media": {"audio_track": True},
        "cradle_state": {
            "updated_at": timestamp,
            "wifi_strength": -45,
            "wifi_ssid": "crib-test",
        },
        "device_state": {
            "updated_at": timestamp,
            "source": "cloud",
            "baby_present": True,
            "baby_needs_attention": False,
            "baby_needs_help": False,
            "crib_helping": False,
            "light_on": False,
            "loud_sound_detected": False,
            "rocking_not_effective": False,
            "obstruction_detected": False,
            "lower_breath_rate_alert": False,
            "sleep_phase": "sleep",
            "sleep_state": "Light sleep",
            "bounce_time_remaining": 0,
            "music_mood": "calm",
            "ambient_temperature": 22,
            "software_version": "0.2.72",
        },
        "analytics": {
            "available": True,
            "updated_at": timestamp,
            **ANALYTICS_VALUES,
        },
    }


def _user_input(
    *,
    bridge_url: str = BRIDGE_URL,
    token: str = TOKEN,
    name: str = "Cradlewise Local",
) -> dict[str, str]:
    return {
        CONF_NAME: name,
        CONF_CRADLE_ID: CRADLE_ID,
        CONF_STREAM_URL: STREAM_URL,
        CONF_BRIDGE_STATUS_URL: bridge_url,
        CONF_BEARER_TOKEN: token,
    }


def _entry_data(
    *,
    bridge_url: str = BRIDGE_URL,
    token: str = TOKEN,
    name: str = "Cradlewise Local",
) -> dict[str, str]:
    return {
        **_user_input(bridge_url=bridge_url, token=token, name=name),
        CONF_SNAPSHOT_URL: f"{bridge_url}/snapshot.jpg",
    }


async def _setup_entry(
    hass: HomeAssistant,
    aioclient_mock: Any,
    *,
    payload: dict[str, Any] | None = None,
) -> MockConfigEntry:
    aioclient_mock.get(STATE_URL, json=payload or _bridge_payload())
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Cradlewise Local",
        unique_id=CRADLE_ID,
        data=_entry_data(),
        version=2,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _registry_entries(
    hass: HomeAssistant,
    entry: MockConfigEntry,
) -> list[er.RegistryEntry]:
    registry = er.async_get(hass)
    return er.async_entries_for_config_entry(registry, entry.entry_id)


def _anchor_entity_ids(
    hass: HomeAssistant,
    entry: MockConfigEntry,
) -> dict[str, str]:
    return {
        registry_entry.unique_id.removeprefix(f"{CRADLE_ID}_"): registry_entry.entity_id
        for registry_entry in _registry_entries(hass, entry)
        if registry_entry.unique_id.removeprefix(f"{CRADLE_ID}_") in ANCHOR_KEYS
    }


def _entity_state(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    assert state is not None
    return state.state


async def test_config_flow_creates_entry_and_sends_bearer_token(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    aioclient_mock.get(STATE_URL, json=_bridge_payload())

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data=_user_input(),
    )

    assert result["type"] is data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Cradlewise Local"
    assert result["data"][CONF_BEARER_TOKEN] == TOKEN
    assert result["data"][CONF_SNAPSHOT_URL] == f"{BRIDGE_URL}/snapshot.jpg"
    assert any(
        headers is not None and headers.get("Authorization") == f"Bearer {TOKEN}"
        for _, _, _, headers in aioclient_mock.mock_calls
    )


async def test_config_flow_maps_rejected_token_to_invalid_auth(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    aioclient_mock.get(STATE_URL, status=401)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data=_user_input(),
    )

    assert result["type"] is data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_config_flow_aborts_duplicate_cradle(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    existing = MockConfigEntry(
        domain=DOMAIN,
        title="Existing Cradlewise",
        unique_id=CRADLE_ID,
        data=_entry_data(),
        version=2,
    )
    existing.add_to_hass(hass)
    aioclient_mock.get(STATE_URL, json=_bridge_payload())

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data=_user_input(),
    )

    assert result["type"] is data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_updates_urls_name_and_token(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Old Cradlewise",
        unique_id=CRADLE_ID,
        data=_entry_data(token="old-token", name="Old Cradlewise"),
        version=2,
    )
    entry.add_to_hass(hass)
    new_bridge_url = "http://new-bridge.test:8088"
    aioclient_mock.get(f"{new_bridge_url}/state", json=_bridge_payload())

    initial = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        initial["flow_id"],
        user_input=_user_input(
            bridge_url=new_bridge_url,
            token="new-token",
            name="Nursery Cradlewise",
        ),
    )

    assert result["type"] is data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_BRIDGE_STATUS_URL] == new_bridge_url
    assert entry.data[CONF_BEARER_TOKEN] == "new-token"
    assert entry.data[CONF_NAME] == "Nursery Cradlewise"
    assert entry.data[CONF_SNAPSHOT_URL] == f"{new_bridge_url}/snapshot.jpg"
    assert aioclient_mock.mock_calls[-1][3]["Authorization"] == "Bearer new-token"

    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_setup_and_unload_with_bridge_http(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    entry = await _setup_entry(hass, aioclient_mock)
    camera = next(
        registry_entry
        for registry_entry in _registry_entries(hass, entry)
        if registry_entry.unique_id == f"{CRADLE_ID}_camera"
    )

    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(camera.entity_id) is not None
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_reload_replaces_and_restarts_preloaded_camera_stream(
    hass: HomeAssistant,
    aioclient_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = await _setup_entry(hass, aioclient_mock)
    registry_entry = next(
        registry_entry
        for registry_entry in _registry_entries(hass, entry)
        if registry_entry.unique_id == f"{CRADLE_ID}_camera"
    )
    old_camera = hass.data["camera"].get_entity(registry_entry.entity_id)
    stream_settings = await hass.data[DATA_CAMERA_PREFS].get_dynamic_stream_settings(
        registry_entry.entity_id
    )
    await hass.data[DATA_CAMERA_PREFS].async_update(
        registry_entry.entity_id, preload_stream=True
    )
    old_stop = AsyncMock()
    old_camera.stream = SimpleNamespace(
        dynamic_stream_settings=stream_settings,
        stop=old_stop,
    )
    replacement_stream = SimpleNamespace(
        dynamic_stream_settings=stream_settings,
        add_provider=Mock(),
        start=AsyncMock(),
    )

    async def create_replacement_stream(camera):
        camera.stream = replacement_stream
        return replacement_stream

    monkeypatch.setattr(
        CradlewiseBridgeCamera,
        "async_create_stream",
        create_replacement_stream,
    )

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    replacement_camera = hass.data["camera"].get_entity(registry_entry.entity_id)

    assert (
        old_stop.await_count,
        stream_settings.preload_stream,
        replacement_camera is old_camera,
        replacement_stream.add_provider.call_args.args,
        replacement_stream.start.await_count,
    ) == (
        1,
        True,
        False,
        (HLS_PROVIDER,),
        1,
    )


async def test_stream_stop_error_still_cleans_up_camera(
    hass: HomeAssistant,
    aioclient_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = await _setup_entry(hass, aioclient_mock)
    registry_entry = next(
        registry_entry
        for registry_entry in _registry_entries(hass, entry)
        if registry_entry.unique_id == f"{CRADLE_ID}_camera"
    )
    camera = hass.data["camera"].get_entity(registry_entry.entity_id)
    stream_settings = SimpleNamespace(preload_stream=True)
    camera.stream = SimpleNamespace(
        dynamic_stream_settings=stream_settings,
        stop=AsyncMock(side_effect=RuntimeError("stop failed")),
    )
    parent_cleanup_calls = []

    async def parent_cleanup(parent_camera):
        parent_cleanup_calls.append(parent_camera)

    monkeypatch.setattr(Camera, "async_will_remove_from_hass", parent_cleanup)

    with pytest.raises(RuntimeError, match="stop failed"):
        await camera.async_will_remove_from_hass()

    assert (
        camera.stream,
        stream_settings.preload_stream,
        parent_cleanup_calls,
    ) == (None, True, [camera])


async def test_entity_registry_defaults_match_policy_counts(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    entry = await _setup_entry(hass, aioclient_mock)
    entries = _registry_entries(hass, entry)
    enabled = sum(registry_entry.disabled_by is None for registry_entry in entries)
    disabled = sum(
        registry_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        for registry_entry in entries
    )

    assert (enabled, disabled, len(entries)) == (35, 78, 113)


async def test_official_sleep_analytics_map_to_enabled_sensor_states(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    entry = await _setup_entry(hass, aioclient_mock)
    states = {}
    for registry_entry in _registry_entries(hass, entry):
        key = registry_entry.unique_id.removeprefix(f"{CRADLE_ID}_")
        if key in ANALYTICS_VALUES:
            states[key] = _entity_state(hass, registry_entry.entity_id)

    assert states == {key: str(value) for key, value in ANALYTICS_VALUES.items()}


async def test_camera_and_anchor_unique_ids_are_stable(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    entry = await _setup_entry(hass, aioclient_mock)
    entries = _registry_entries(hass, entry)
    unique_ids = {registry_entry.unique_id for registry_entry in entries}
    expected = {
        f"{CRADLE_ID}_camera",
        *(f"{CRADLE_ID}_{key}" for key in ANCHOR_KEYS),
    }

    assert expected <= unique_ids


async def test_two_cradles_keep_separate_config_entry_identity(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    first_entry = await _setup_entry(hass, aioclient_mock)
    second_cradle_id = "00000000-0000-4000-8000-000000000002"
    second_bridge_url = "http://second-bridge.test:8088"
    second_payload = deepcopy(_bridge_payload())
    second_payload["bridge"]["cradle_id"] = second_cradle_id
    aioclient_mock.get(f"{second_bridge_url}/state", json=second_payload)
    second_entry = MockConfigEntry(
        domain=DOMAIN,
        title="Second Cradlewise",
        unique_id=second_cradle_id,
        data={
            **_entry_data(bridge_url=second_bridge_url, name="Second Cradlewise"),
            CONF_CRADLE_ID: second_cradle_id,
        },
        version=2,
    )
    second_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(second_entry.entry_id)
    await hass.async_block_till_done()

    first_unique_ids = {
        entry.unique_id for entry in _registry_entries(hass, first_entry)
    }
    second_unique_ids = {
        entry.unique_id for entry in _registry_entries(hass, second_entry)
    }
    assert len(first_unique_ids) == len(second_unique_ids) == 113
    assert first_unique_ids.isdisjoint(second_unique_ids)


async def test_anchor_entities_become_unavailable_when_state_is_stale(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    entry = await _setup_entry(hass, aioclient_mock)
    anchor_entity_ids = _anchor_entity_ids(hass, entry)
    assert set(anchor_entity_ids) == ANCHOR_KEYS
    assert all(
        _entity_state(hass, entity_id) != STATE_UNAVAILABLE
        for entity_id in anchor_entity_ids.values()
    )

    stale_payload = _bridge_payload(updated_at=time.time() - 121)
    entry.runtime_data.coordinator.async_set_updated_data(stale_payload)
    await hass.async_block_till_done()

    assert all(
        _entity_state(hass, entity_id) == STATE_UNAVAILABLE
        for entity_id in anchor_entity_ids.values()
    )


async def test_anchor_entities_reject_unknown_or_missing_values(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    entry = await _setup_entry(hass, aioclient_mock)
    anchor_entity_ids = _anchor_entity_ids(hass, entry)
    invalid_payload = deepcopy(_bridge_payload())
    invalid_payload["device_state"].update(
        {
            "baby_present": "unknown",
            "baby_needs_attention": 2,
            "baby_needs_help": None,
            "loud_sound_detected": "unavailable",
            "sleep_phase": "",
            "sleep_state": None,
        }
    )

    entry.runtime_data.coordinator.async_set_updated_data(invalid_payload)
    await hass.async_block_till_done()

    assert all(
        _entity_state(hass, entity_id) == STATE_UNAVAILABLE
        for entity_id in anchor_entity_ids.values()
    )


async def test_coordinator_failure_marks_camera_and_anchors_unavailable(
    hass: HomeAssistant,
    aioclient_mock: Any,
) -> None:
    entry = await _setup_entry(hass, aioclient_mock)
    registry_entries = _registry_entries(hass, entry)
    observed = {
        registry_entry.entity_id
        for registry_entry in registry_entries
        if registry_entry.unique_id
        in {f"{CRADLE_ID}_camera", *(f"{CRADLE_ID}_{key}" for key in ANCHOR_KEYS)}
    }

    entry.runtime_data.coordinator.async_set_update_error(UpdateFailed("offline"))
    await hass.async_block_till_done()

    assert all(
        _entity_state(hass, entity_id) == STATE_UNAVAILABLE for entity_id in observed
    )


async def test_version_one_migration_removes_duplicates_and_disables_diagnostics(
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Cradlewise Local",
        unique_id=CRADLE_ID,
        data=_entry_data(),
        version=1,
        minor_version=1,
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    duplicate = registry.async_get_or_create(
        "binary_sensor",
        DOMAIN,
        f"{CRADLE_ID}_bouncing",
        config_entry=entry,
    )
    diagnostic = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{CRADLE_ID}_wifi_strength",
        config_entry=entry,
    )
    retained = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{CRADLE_ID}_sleep_state",
        config_entry=entry,
    )

    assert await async_migrate_entry(hass, entry)

    migrated_diagnostic = registry.async_get(diagnostic.entity_id)
    assert registry.async_get(duplicate.entity_id) is None
    assert migrated_diagnostic is not None
    assert migrated_diagnostic.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert registry.async_get(retained.entity_id) is not None
    assert (entry.version, entry.minor_version) == (2, 1)
