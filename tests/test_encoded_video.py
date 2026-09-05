import asyncio
import json
import queue
import threading
import time
from types import SimpleNamespace

import pytest
from aiortc import rtcrtpreceiver
from aiortc.jitterbuffer import JitterFrame
from aiortc.rtcrtpparameters import RTCRtpCodecParameters

from cradlewise_local.encoded import (
    EncodedVideoFrame,
    _offer_encoded_frame,
    h264_nal_types,
    install_encoded_frame_tap,
)
from cradlewise_local.status import BridgeStatusStore
from cradlewise_local.streamer import BridgeStreamer
from stream_local import CribStreamer, _discovery_bind_address, discover_crib_race


def test_h264_nal_types_reads_three_and_four_byte_start_codes():
    data = b"\x00\x00\x00\x01\x67sps\x00\x00\x01\x68pps\x00\x00\x00\x01\x65idr"

    assert h264_nal_types(data) == [7, 8, 5]
    assert BridgeStreamer._is_h264_sync_point(data) is True


def test_encoded_frame_tap_routes_h264_without_decoding():
    install_encoded_frame_tap()
    loop = asyncio.new_event_loop()
    input_q = queue.Queue()
    output_q = asyncio.Queue()
    encoded_q = asyncio.Queue()
    output_q.encoded_passthrough_queue = encoded_q
    codec = RTCRtpCodecParameters(
        mimeType="video/H264",
        clockRate=90000,
        payloadType=97,
    )
    input_q.put((codec, JitterFrame(data=b"\x00\x00\x01\x65idr", timestamp=123)))
    input_q.put(None)

    try:
        rtcrtpreceiver.decoder_worker(loop, input_q, output_q)
        frame = loop.run_until_complete(encoded_q.get())
        assert frame.data == b"\x00\x00\x01\x65idr"
        assert frame.timestamp == 123
        assert loop.run_until_complete(encoded_q.get()) is None
    finally:
        loop.close()


def test_encoded_frame_queue_is_bounded_and_marks_discontinuity():
    encoded_queue = asyncio.Queue(maxsize=1)
    encoded_queue.put_nowait(EncodedVideoFrame(data=b"old", timestamp=1))

    _offer_encoded_frame(encoded_queue, EncodedVideoFrame(data=b"new", timestamp=2))

    frame = encoded_queue.get_nowait()
    assert frame.data == b"new"
    assert frame.discontinuity is True


def test_stream_session_filter_matches_app_compatibility_rules():
    streamer = object.__new__(CribStreamer)
    streamer.session_id = "active-session"

    assert streamer._session_matches({"streamInfo": {"sessionId": "active-session"}})
    assert streamer._session_matches({"streamInfo": {"sessionId": "[empty]"}})
    assert not streamer._session_matches({"streamInfo": {"sessionId": "stale"}})
    assert not streamer._session_matches({})


def test_shadow_get_is_published_only_after_subscription_acknowledgement():
    streamer = object.__new__(BridgeStreamer)
    streamer._shutting_down = False
    streamer._shadow_subscription_mids = {42}
    streamer.shadow_get_topic = "$aws/things/cradle-1/shadow/get"
    published = []

    class Client:
        def publish(self, topic, payload, qos, retain):
            published.append((topic, payload, qos, retain))
            return SimpleNamespace(rc=0)

    streamer._on_subscribe(Client(), None, 7, [0], None)
    assert published == []

    streamer._on_subscribe(Client(), None, 42, [0], None)
    assert published == [("$aws/things/cradle-1/shadow/get", "{}", 0, False)]


def test_shadow_response_updates_local_shadow_source():
    streamer = object.__new__(BridgeStreamer)
    streamer.status_store = BridgeStatusStore(
        cradle_id="cradle-1", crib_ip="192.0.2.10"
    )
    streamer.beacon_topic = "/cradle-1/beacon"
    streamer.cradle_state_topic = "/cradle/cradle-1/cradle_state"
    streamer.shadow_get_accepted_topic = "$aws/things/cradle-1/shadow/get/accepted"
    streamer.shadow_get_rejected_topic = "$aws/things/cradle-1/shadow/get/rejected"
    streamer.shadow_update_accepted_topic = (
        "$aws/things/cradle-1/shadow/update/accepted"
    )
    streamer.shadow_update_rejected_topic = (
        "$aws/things/cradle-1/shadow/update/rejected"
    )
    message = SimpleNamespace(
        topic=streamer.shadow_get_accepted_topic,
        payload=json.dumps({"state": {"reported": {"babyPresent": True}}}).encode(),
    )

    streamer._on_message(None, None, message)

    device_state = streamer.status_store.snapshot()["device_state"]
    assert device_state["baby_present"] is True
    assert device_state["source"] == "local_shadow"


def test_service_discovery_does_not_start_interactive_cloud_login(monkeypatch):
    cloud_called = False

    def discover_udp(_cradle_id):
        return "192.0.2.10", "cradle-1"

    def discover_cloud(*_args):
        nonlocal cloud_called
        cloud_called = True
        raise AssertionError("cloud discovery should not run")

    monkeypatch.setattr("stream_local.discover_crib", discover_udp)
    monkeypatch.setattr("stream_local.discover_crib_cloud", discover_cloud)

    result = discover_crib_race("cradle-1", allow_interactive=False)

    assert result == "192.0.2.10"
    assert cloud_called is False


def test_discovery_callback_binds_to_the_outbound_lan_interface(monkeypatch):
    class RouteProbe:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        @staticmethod
        def setsockopt(*_args):
            return None

        @staticmethod
        def connect(_address):
            return None

        @staticmethod
        def getsockname():
            return "192.0.2.25", 54321

    monkeypatch.setattr("stream_local.socket.socket", lambda *_args: RouteProbe())

    assert _discovery_bind_address() == "192.0.2.25"


def test_discovery_returns_without_waiting_for_losing_worker(monkeypatch):
    cloud_started = threading.Event()
    release_cloud = threading.Event()

    def discover_udp(_cradle_id):
        cloud_started.wait(timeout=1)
        return "192.0.2.10", "cradle-1"

    def discover_cloud(*_args):
        cloud_started.set()
        release_cloud.wait(timeout=2)
        return "192.0.2.11"

    monkeypatch.setattr("stream_local.discover_crib", discover_udp)
    monkeypatch.setattr("stream_local.discover_crib_cloud", discover_cloud)

    started_at = time.monotonic()
    result = discover_crib_race(
        "cradle-1",
        email="user@example.com",
        password="secret",
        allow_interactive=False,
    )
    elapsed = time.monotonic() - started_at
    release_cloud.set()

    assert result == "192.0.2.10"
    assert elapsed < 1


def test_discovery_reports_each_method_failure(monkeypatch):
    def discover_udp(_cradle_id):
        raise RuntimeError("no broadcast response")

    def discover_cloud(*_args):
        raise RuntimeError("authentication failed")

    monkeypatch.setattr("stream_local.discover_crib", discover_udp)
    monkeypatch.setattr("stream_local.discover_crib_cloud", discover_cloud)

    with pytest.raises(RuntimeError) as exc_info:
        discover_crib_race(
            "cradle-1",
            email="user@example.com",
            password="secret",
            allow_interactive=False,
        )

    assert "UDP: no broadcast response" in str(exc_info.value)
    assert "cloud: authentication failed" in str(exc_info.value)
