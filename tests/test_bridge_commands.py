import json
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


def _post_json(url: str, payload: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
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
        ("bounce_setting", 4, {"bounceSetting": 4}),
        ("responsivity_setting", 6, {"responsivitySetting": 6}),
        ("music_playing", False, {"music": {"play": False}}),
        ("music_volume", 23, {"music": {"volume": 23}}),
        ("music_level", 2, {"musicLevel": 2}),
        ("volume_profile", "Max", {"volumeProfile": "max"}),
        ("light_indicator_brightness", 40, {"light": {"indicatorBrightness": 40}}),
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
        ("volume_profile", "loud"),
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
        "command": "music_volume",
        "desired": {"music": {"volume": 22}},
    }
    assert published == [{"state": {"desired": {"music": {"volume": 22}}}}]


def test_command_handler_requires_active_publisher():
    handler = BridgeCommandHandler()

    with pytest.raises(CommandUnavailable):
        handler.handle_request({"command": "music_volume", "value": 22})


def test_status_http_server_serves_command_endpoint():
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
    handler = BridgeCommandHandler()
    published = []
    handler.set_publisher(published.append)
    server = BridgeStatusHttpServer(
        store,
        "127.0.0.1",
        _free_port(),
        command_handler=handler.handle_request,
    )
    server.start()

    try:
        status, response = _post_json(
            f"http://127.0.0.1:{server.port}/command",
            {"command": "bounce_level", "value": 2},
        )
    finally:
        server.close()

    assert status == 200
    assert response["ok"] is True
    assert published == [{"state": {"desired": {"bounceLevel": 2}}}]


def test_status_http_server_rejects_invalid_command():
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
                {"command": "music_volume", "value": 101},
            )
    finally:
        server.close()

    assert exc_info.value.code == 400
