import json
import logging
import socket
import urllib.error
import urllib.request

import pytest

from cradlewise_local.commands import (
    BridgeCommandHandler,
    CommandError,
    CommandUnavailable,
    build_desired,
    shadow_payload,
)
from cradlewise_local.status import BridgeStatusHttpServer, BridgeStatusStore


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _post_json(url: str, payload: dict, token: str | None = None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=2) as response:
        return response.status, json.loads(response.read())


@pytest.mark.parametrize(
    ("command", "value", "expected"),
    (
        ("actuator_on", True, {"actuator": {"on": True}}),
        ("bounce_mode", "manual", {"bounceMode": 1}),
        ("bounce_mode", "auto", {"bounceMode": 0}),
        ("bounce_amplitude", 26, {"actuator": {"amplitude": 26}}),
        ("bounce_level", 3, {"bounceLevel": 3}),
        ("bounce_duration", 15, {"actuator": {"duration": 15}}),
        ("bounce_setting", 4, {"bounceSetting": 4}),
        ("responsivity_setting", 6, {"responsivitySetting": 6}),
        ("disable_bounce", True, {"actuator": {"disableBouncing": True}}),
        ("super_gentle_bounce", True, {"actuator": {"bounceSuperGentle": True}}),
        ("always_on_bounce", True, {"actuator": {"bounceAlwaysOn": True}}),
        (
            "always_on_bounce_intensity",
            44,
            {"actuator": {"bounceAlwaysOnIntensity": 44}},
        ),
        ("tap_detection_enabled", True, {"actuator": {"tapDetectionEnable": True}}),
        ("push_gesture_enabled", False, {"actuator": {"pushGestureEnable": False}}),
        ("music_playing", False, {"soundSynth": {"play": False}}),
        ("music_volume", 23, {"soundSynth": {"volume": 23}}),
        ("music_level", 2, {"musicLevel": 2}),
        ("music_duration", 60, {"musicDuration": 60}),
        ("volume_profile", "Max", {"volumeProfile": "max"}),
        ("light_indicator_brightness", 40, {"light": {"indicatorBrightness": 40}}),
        ("light_indicator_mode", "manual", {"light": {"indicatorBrightnessMode": 1}}),
        ("keep_music_on_during_sleep", True, {"keepMusicOnDuringSleep": True}),
        ("keep_music_on_during_sleep_level", 2, {"keepMusicOnDuringSleepLevel": 2}),
        ("keep_bounce_on_during_sleep", False, {"keepBounceOnDuringSleep": False}),
        ("keep_bounce_on_during_sleep_level", 1, {"keepBounceOnDuringSleepLevel": 1}),
        ("auto_mode_lock_on", True, {"autoModeLockOn": True}),
        ("auto_mode_lock_duration", 20, {"autoModeLockDuration": 20}),
        ("max_bounce_limit", 55, {"maxBounceLimit": 55}),
        ("max_volume_limit", 45, {"maxVolumeLimit": 45}),
        ("start_recipe_enabled", True, {"startRecipeEnabled": True}),
        ("start_recipe_music_level", 2, {"startRecipeMusicLevel": 2}),
        ("start_recipe_bounce_level", 3, {"startRecipeBounceLevel": 3}),
        ("start_recipe_lock_duration", 20, {"startRecipeLockDuration": 20}),
        (
            "adaptive_soothing_enabled",
            True,
            {"control": {"adaptiveSoothingEnabled": True}},
        ),
        ("cry_sensitivity", 4, {"control": {"crySensitivity": 4}}),
    ),
)
def test_build_desired_uses_android_shadow_shapes(command, value, expected):
    assert build_desired(command, value) == expected


def test_shadow_payload_wraps_desired_state_like_app():
    assert shadow_payload({"bounceMode": 1}) == {
        "state": {"desired": {"bounceMode": 1}}
    }


@pytest.mark.parametrize(
    ("command", "value"),
    (
        ("music_volume", 101),
        ("music_volume", True),
        ("light_indicator_mode", True),
        ("volume_profile", "loud"),
        ("cry_sensitivity", 3),
        ("start_recipe_music_level", 6),
        ("bounce_duration", 0),
        ("responsivity_setting", 3),
        ("keep_bounce_on_during_sleep_level", 2),
        ("music_duration", 30),
        ("auto_mode_lock_duration", 61),
        ("start_recipe_lock_duration", 15),
        ("unknown", 1),
    ),
)
def test_build_desired_rejects_invalid_commands(command, value):
    with pytest.raises(CommandError):
        build_desired(command, value)


def test_command_handler_publishes_wrapped_payload():
    handler = BridgeCommandHandler()
    published = []
    handler.set_publisher(published.append)

    response = handler.handle_request({"command": "music_volume", "value": 22})

    assert response == {
        "ok": True,
        "status": "queued",
        "command": "music_volume",
        "desired": {"soundSynth": {"volume": 22}},
    }
    assert published == [{"state": {"desired": {"soundSynth": {"volume": 22}}}}]


def test_command_handler_requires_active_publisher():
    handler = BridgeCommandHandler()

    with pytest.raises(CommandUnavailable):
        handler.handle_request({"command": "music_volume", "value": 22})


def test_command_handler_enforces_reported_device_limits():
    handler = BridgeCommandHandler(
        state_provider=lambda: {
            "device_state": {
                "bounce_duration_limit": 30,
                "max_bounce_limit": 55,
                "max_volume_limit": 45,
            }
        }
    )
    handler.set_publisher(lambda payload: payload)

    with pytest.raises(CommandError, match="device limit of 30"):
        handler.handle_request({"command": "bounce_duration", "value": 31})


def test_command_handler_publishes_complete_app_shaped_sound_synth_state():
    handler = BridgeCommandHandler(
        state_provider=lambda: {
            "device_state": {
                "music_playing": False,
                "music_volume": 40,
                "music_mood": "Calming Rain",
                "sound_ambience_raw": 0,
                "sound_color_raw": 1,
                "sound_heartbeat_volume": 100,
                "sound_breath_volume": 0,
                "max_volume_limit": 80,
            }
        }
    )
    published = []
    handler.set_publisher(published.append)

    handler.handle_request({"command": "music_volume", "value": 50})

    assert published == [
        {
            "state": {
                "desired": {
                    "soundSynth": {
                        "play": False,
                        "ambience": 0,
                        "color": 1,
                        "heartbeatVolume": 100,
                        "breathVolume": 0,
                        "volume": 50,
                        "trackName": "Calming Rain",
                    }
                }
            }
        }
    ]


def test_status_http_server_serves_command_endpoint(caplog):
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
    handler = BridgeCommandHandler()
    published = []
    handler.set_publisher(published.append)
    server = BridgeStatusHttpServer(
        store,
        "127.0.0.1",
        _free_port(),
        command_handler=handler.handle_request,
        bearer_token="secret",
    )
    server.start()

    caplog.set_level(logging.INFO, logger="cradlewise_local.status")
    try:
        status, response = _post_json(
            f"http://127.0.0.1:{server.port}/command",
            {"command": "bounce_level", "value": 2},
            token="secret",
        )
    finally:
        server.close()

    assert status == 200
    assert response["ok"] is True
    assert response["status"] == "queued"
    assert published == [{"state": {"desired": {"bounceLevel": 2}}}]
    assert "Accepted bridge command bounce_level (queued)" in caplog.text


def test_status_http_server_rejects_invalid_command():
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
    handler = BridgeCommandHandler()
    handler.set_publisher(lambda payload: payload)
    server = BridgeStatusHttpServer(
        store,
        "127.0.0.1",
        _free_port(),
        command_handler=handler.handle_request,
        bearer_token="secret",
    )
    server.start()

    try:
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            _post_json(
                f"http://127.0.0.1:{server.port}/command",
                {"command": "music_volume", "value": 101},
                token="secret",
            )
    finally:
        server.close()

    assert exc_info.value.code == 400


def test_status_http_server_disables_commands_without_token():
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
    handler = BridgeCommandHandler()
    handler.set_publisher(lambda payload: payload)
    server = BridgeStatusHttpServer(
        store,
        "127.0.0.1",
        _free_port(),
        command_handler=handler.handle_request,
    )
    server.start()

    try:
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            _post_json(
                f"http://127.0.0.1:{server.port}/command",
                {"command": "bounce_level", "value": 2},
            )
    finally:
        server.close()

    assert exc_info.value.code == 503
