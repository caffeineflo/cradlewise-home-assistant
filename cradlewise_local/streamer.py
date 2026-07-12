"""Headless bridge wrapper around the proven local Cradlewise streamer."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import threading
import time
from typing import Any

import av
from aiortc.mediastreams import MediaStreamError
from av.audio.resampler import AudioResampler
from paho.mqtt.client import MQTT_ERR_SUCCESS

from stream_local import CribStreamer, discover_crib_race

from .commands import BridgeCommandHandler
from .config import BridgeConfig
from .encoded import EncodedVideoFrame, h264_nal_types, install_encoded_frame_tap
from .sinks import FrameSink
from .status import BridgeStatusStore

log = logging.getLogger(__name__)

SNAPSHOT_INTERVAL_SECONDS = 1.0


def encode_jpeg(image) -> bytes:
    """Encode one BGR24 video frame as JPEG."""
    height, width = image.shape[:2]
    frame = av.VideoFrame.from_ndarray(image, format="bgr24")
    buffer = io.BytesIO()
    with av.open(buffer, mode="w", format="mjpeg") as output:
        stream = output.add_stream("mjpeg", rate=1)
        stream.width = width
        stream.height = height
        stream.pix_fmt = "yuvj420p"
        for packet in stream.encode(frame):
            output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)
    return buffer.getvalue()


class BridgeStreamer(CribStreamer):
    """Cradlewise streamer that copies H.264 video to a sink."""

    def __init__(
        self,
        config: BridgeConfig,
        sink: FrameSink,
        status_store: BridgeStatusStore,
    ):
        install_encoded_frame_tap()
        crib_ip = config.crib_ip or discover_crib_race(
            config.cradle_id,
            email=config.cloud_email,
            password=config.cloud_password,
            allow_interactive=False,
        )
        super().__init__(crib_ip, config.cradle_id, config.certs_dir)
        self.config = config
        self.sink = sink
        self.status_store = status_store
        self.status_store.crib_ip = crib_ip
        self.beacon_topic = f"/{config.cradle_id}/beacon"
        self.cradle_state_topic = f"/cradle/{config.cradle_id}/cradle_state"
        self.shadow_get_topic = f"$aws/things/{config.cradle_id}/shadow/get"
        self.shadow_get_accepted_topic = f"{self.shadow_get_topic}/accepted"
        self.shadow_get_rejected_topic = f"{self.shadow_get_topic}/rejected"
        self.shadow_update_topic = f"$aws/things/{config.cradle_id}/shadow/update"
        self.shadow_update_accepted_topic = f"{self.shadow_update_topic}/accepted"
        self.shadow_update_rejected_topic = f"{self.shadow_update_topic}/rejected"
        self._audio_resampler = AudioResampler(format="s16", layout="mono", rate=48000)
        self._encoded_video_queue: asyncio.Queue[EncodedVideoFrame | None] = (
            asyncio.Queue(maxsize=120)
        )
        self._snapshot_decoder = av.CodecContext.create("h264", "r")
        self._last_snapshot_update = 0.0
        self._command_lock = threading.Lock()
        self._shadow_subscription_mids: set[int] = set()

    def _setup_mqtt(self):
        super()._setup_mqtt()
        self._mqtt.on_subscribe = self._on_subscribe

    def _handle_mqtt_connected(self):
        self.status_store.set_mqtt_connected(True)

    def _handle_mqtt_disconnected(self):
        self.status_store.set_mqtt_connected(False)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        super()._on_connect(client, userdata, flags, reason_code, properties)
        if reason_code == 0:
            self.status_store.mark_stream_started()
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
                self._signal_fatal_threadsafe(
                    RuntimeError(f"MQTT state topic subscribe failed with rc={result}")
                )
                return
            self._shadow_subscription_mids.add(mid)
            log.info(
                "Requested state topic subscriptions: %s, %s and shadow responses",
                self.beacon_topic,
                self.cradle_state_topic,
            )

    def _on_subscribe(self, client, userdata, mid, reason_code_list, properties):
        if mid not in self._shadow_subscription_mids:
            return
        self._shadow_subscription_mids.discard(mid)

        def rejected(reason_code) -> bool:
            failure = getattr(reason_code, "is_failure", None)
            if failure is not None:
                return bool(failure() if callable(failure) else failure)
            try:
                return int(reason_code) >= 128
            except (TypeError, ValueError):
                return True

        if any(rejected(reason_code) for reason_code in reason_code_list):
            self._signal_fatal_threadsafe(
                RuntimeError("MQTT shadow response topic subscription was rejected")
            )
            return

        result = client.publish(
            self.shadow_get_topic,
            "{}",
            qos=0,
            retain=False,
        )
        if result.rc != MQTT_ERR_SUCCESS:
            self._signal_fatal_threadsafe(
                RuntimeError(f"MQTT shadow get failed with rc={result.rc}")
            )
            return
        log.info(
            "Requested current local device shadow after subscription acknowledgement"
        )

    def _on_message(self, client, userdata, message):
        self.status_store.mark_mqtt_message()
        topic = message.topic
        state_topics = {
            self.beacon_topic,
            self.cradle_state_topic,
            self.shadow_get_accepted_topic,
            self.shadow_update_accepted_topic,
        }
        if topic in state_topics:
            try:
                payload = json.loads(message.payload)
            except json.JSONDecodeError:
                log.warning("Invalid JSON from %s: %s", topic, message.payload[:100])
                return
            if not isinstance(payload, dict):
                log.warning("Ignored non-object JSON from %s", topic)
                return

            if topic == self.beacon_topic:
                self.status_store.update_beacon(payload)
            elif topic == self.cradle_state_topic:
                self.status_store.update_cradle_state(payload)
            else:
                self.status_store.update_device_state(payload, source="local_shadow")
            return

        if topic in {
            self.shadow_get_rejected_topic,
            self.shadow_update_rejected_topic,
        }:
            self.status_store.mark_device_state_error(
                "local_shadow", message.payload[:200].decode(errors="replace")
            )
            log.warning(
                "Local device shadow request rejected: %s", message.payload[:200]
            )
            return

        super()._on_message(client, userdata, message)

    def publish_shadow_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Publish a desired-state payload to the local shadow update topic."""
        if self._mqtt is None or not self._mqtt.is_connected():
            raise RuntimeError("MQTT is not connected")

        data = json.dumps(payload, separators=(",", ":"))
        log.info("Publishing command to %s", self.shadow_update_topic)
        with self._command_lock:
            result = self._mqtt.publish(self.shadow_update_topic, data)
        if result.rc != MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT publish failed with rc={result.rc}")
        return payload

    async def _handle_track(self, track):
        if track.kind == "audio":
            self.status_store.mark_audio_track()
            await self._consume_audio(track)
            return
        await super()._handle_track(track)

    def _prepare_track(self, track):
        if track.kind == "video":
            track._queue.encoded_passthrough_queue = self._encoded_video_queue

    def _handle_webrtc_connection_state(self, state):
        self.status_store.set_webrtc_state(state)

    def _handle_ice_connection_state(self, state):
        self.status_store.set_ice_state(state)

    def _update_snapshot(self, image) -> None:
        now = time.monotonic()
        if now - self._last_snapshot_update < SNAPSHOT_INTERVAL_SECONDS:
            return
        self.status_store.update_snapshot(encode_jpeg(image))
        self._last_snapshot_update = now

    def _decode_for_snapshot(self, data: bytes) -> None:
        try:
            frames = self._snapshot_decoder.decode(av.Packet(data))
        except av.FFmpegError as exc:
            log.debug("Snapshot decoder skipped H.264 frame: %s", exc)
            return

        for frame in frames:
            image = frame.to_ndarray(format="bgr24")
            height, width = image.shape[:2]
            self.status_store.set_video_resolution(width, height)
            self._update_snapshot(image)

    @staticmethod
    def _is_h264_sync_point(data: bytes) -> bool:
        nal_types = set(h264_nal_types(data))
        return {5, 7, 8}.issubset(nal_types)

    async def _consume_video(self, track):
        log.info("Waiting for first H.264 keyframe...")
        sink_started = False
        awaiting_sync_point = True
        self._frame_count = 0

        try:
            while True:
                encoded_frame = await self._encoded_video_queue.get()
                if encoded_frame is None:
                    raise MediaStreamError

                if encoded_frame.discontinuity:
                    awaiting_sync_point = True
                    log.warning(
                        "Encoded video backlog dropped; waiting for a new keyframe"
                    )

                if awaiting_sync_point:
                    if not self._is_h264_sync_point(encoded_frame.data):
                        continue
                    awaiting_sync_point = False
                    if not sink_started:
                        self.sink.start_h264()
                        sink_started = True
                        self.status_store.update_sink_health(
                            self.sink.health_snapshot()
                        )
                        self.status_store.set_webrtc_state("connected")
                        self.status_store.set_ice_state("completed")
                        log.info("H.264 passthrough started")

                self.sink.write_h264(encoded_frame.data)
                self.status_store.update_sink_health(self.sink.health_snapshot())
                self._frame_count += 1
                self.status_store.increment_video_frames()
                self._decode_for_snapshot(encoded_frame.data)
                if self._frame_count % 300 == 0:
                    log.info("Frames bridged: %d", self._frame_count)
        except asyncio.CancelledError:
            log.info("Video bridge stopped")
            raise
        except MediaStreamError as exc:
            log.info("Video bridge stopped")
            raise RuntimeError("crib video track ended") from exc
        except Exception as exc:
            log.error("Video bridge stopped: %s", exc)
            raise
        finally:
            self.sink.close()

    async def _consume_audio(self, track):
        log.info("Consuming audio track")
        try:
            while True:
                frame = await track.recv()
                self.status_store.increment_audio_frames()
                if self.config.enable_audio:
                    for resampled in self._audio_resampler.resample(frame):
                        self.sink.write_audio(bytes(resampled.planes[0]))
                        self.status_store.update_sink_health(
                            self.sink.health_snapshot()
                        )
        except asyncio.CancelledError:
            log.info("Audio bridge stopped")
            raise
        except MediaStreamError as exc:
            log.info("Audio bridge stopped")
            raise RuntimeError("crib audio track ended") from exc
        except Exception as exc:
            log.warning("Audio bridge stopped: %s", exc)
            raise


async def run_bridge(
    config: BridgeConfig,
    sink: FrameSink,
    status_store: BridgeStatusStore,
    command_handler: BridgeCommandHandler | None = None,
) -> None:
    """Run the bridge until cancelled."""
    streamer = BridgeStreamer(config, sink, status_store)
    if command_handler is not None:
        command_handler.set_publisher(streamer.publish_shadow_payload)
    try:
        await streamer.run()
    finally:
        if command_handler is not None:
            command_handler.clear_publisher()
