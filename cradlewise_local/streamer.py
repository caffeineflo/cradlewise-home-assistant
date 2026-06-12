"""Headless bridge wrapper around the proven local Cradlewise streamer."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import time

from aiortc.mediastreams import MediaStreamError
import av
from av.audio.resampler import AudioResampler

from stream_local import CribStreamer, discover_crib_race

from .config import BridgeConfig
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
    """Cradlewise streamer that sends decoded video frames to a sink."""

    def __init__(
        self,
        config: BridgeConfig,
        sink: FrameSink,
        status_store: BridgeStatusStore,
    ):
        crib_ip = config.crib_ip or discover_crib_race(config.cradle_id)
        super().__init__(crib_ip, config.cradle_id, config.certs_dir)
        self.config = config
        self.sink = sink
        self.status_store = status_store
        self.status_store.crib_ip = crib_ip
        self.beacon_topic = f"/{config.cradle_id}/beacon"
        self.cradle_state_topic = f"/cradle/{config.cradle_id}/cradle_state"
        self._audio_resampler = AudioResampler(format="s16", layout="mono", rate=48000)
        self._last_snapshot_update = 0.0

    def _handle_mqtt_connected(self):
        self.status_store.set_mqtt_connected(True)

    def _handle_mqtt_disconnected(self):
        self.status_store.set_mqtt_connected(False)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        super()._on_connect(client, userdata, flags, reason_code, properties)
        if reason_code == 0:
            client.subscribe(self.beacon_topic)
            client.subscribe(self.cradle_state_topic)
            log.info(
                "Subscribed to state topics: %s, %s",
                self.beacon_topic,
                self.cradle_state_topic,
            )

    def _on_message(self, client, userdata, message):
        self.status_store.mark_mqtt_message()
        topic = message.topic
        if topic in {self.beacon_topic, self.cradle_state_topic}:
            try:
                payload = json.loads(message.payload)
            except json.JSONDecodeError:
                log.warning("Invalid JSON from %s: %s", topic, message.payload[:100])
                return

            if topic == self.beacon_topic:
                self.status_store.update_beacon(payload)
            else:
                self.status_store.update_cradle_state(payload)
            return

        super()._on_message(client, userdata, message)

    async def _handle_track(self, track):
        if track.kind == "audio":
            self.status_store.mark_audio_track()
            asyncio.ensure_future(self._consume_audio(track))
            return
        await super()._handle_track(track)

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

    async def _consume_video(self, track):
        log.info("Waiting for first video frame...")
        frame = await track.recv()
        image = frame.to_ndarray(format="bgr24")
        height, width = image.shape[:2]
        log.info("Video resolution: %dx%d", width, height)
        self.status_store.set_video_resolution(width, height)
        self.status_store.set_webrtc_state("connected")
        self.status_store.set_ice_state("completed")
        self.sink.start(width, height)
        self.sink.write(image.tobytes())
        self._frame_count = 1
        self.status_store.increment_video_frames()
        self._update_snapshot(image)

        try:
            while True:
                frame = await track.recv()
                image = frame.to_ndarray(format="bgr24")
                self.sink.write(image.tobytes())
                self._frame_count += 1
                self.status_store.increment_video_frames()
                self._update_snapshot(image)
                if self._frame_count % 300 == 0:
                    log.info("Frames bridged: %d", self._frame_count)
        except (asyncio.CancelledError, MediaStreamError):
            log.info("Video bridge stopped")
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
        except (asyncio.CancelledError, MediaStreamError):
            log.info("Audio bridge stopped")
        except Exception as exc:
            log.warning("Audio bridge stopped: %s", exc)


async def run_bridge(
    config: BridgeConfig,
    sink: FrameSink,
    status_store: BridgeStatusStore,
) -> None:
    """Run the bridge until cancelled."""
    streamer = BridgeStreamer(config, sink, status_store)
    await streamer.run()
