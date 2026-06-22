"""Encoded media helpers for the Cradlewise bridge."""

from __future__ import annotations

import asyncio
import queue
from dataclasses import dataclass

from aiortc import rtcrtpreceiver
from aiortc.codecs import get_decoder


@dataclass(frozen=True)
class EncodedVideoFrame:
    """A complete depacketized encoded video access unit."""

    data: bytes
    timestamp: int


def install_encoded_frame_tap() -> None:
    """Route complete H.264 frames from aiortc to a track queue when requested."""
    if getattr(rtcrtpreceiver.decoder_worker, "_cradlewise_encoded_tap", False):
        return

    def decoder_worker_with_encoded_tap(
        loop: asyncio.AbstractEventLoop,
        input_q: queue.Queue,
        output_q: asyncio.Queue,
    ) -> None:
        codec_name = None
        decoder = None

        while True:
            task = input_q.get()
            encoded_queue = getattr(output_q, "encoded_passthrough_queue", None)
            if task is None:
                if encoded_queue is not None:
                    asyncio.run_coroutine_threadsafe(encoded_queue.put(None), loop)
                asyncio.run_coroutine_threadsafe(output_q.put(None), loop)
                break

            codec, encoded_frame = task
            if encoded_queue is not None and codec.name.lower() == "h264":
                frame = EncodedVideoFrame(
                    data=bytes(encoded_frame.data),
                    timestamp=encoded_frame.timestamp,
                )
                asyncio.run_coroutine_threadsafe(encoded_queue.put(frame), loop)
                continue

            if codec.name != codec_name:
                decoder = get_decoder(codec)
                codec_name = codec.name

            for frame in decoder.decode(encoded_frame):
                asyncio.run_coroutine_threadsafe(output_q.put(frame), loop)

        if decoder is not None:
            del decoder

    decoder_worker_with_encoded_tap._cradlewise_encoded_tap = True
    rtcrtpreceiver.decoder_worker = decoder_worker_with_encoded_tap


def h264_nal_types(data: bytes) -> list[int]:
    """Return Annex B NAL unit types in a depacketized H.264 access unit."""
    return [nal[0] & 0x1F for nal in iter_h264_nals(data) if nal]


def iter_h264_nals(data: bytes):
    """Yield Annex B NAL units without their start codes."""
    i = 0
    while True:
        start = data.find(b"\x00\x00\x01", i)
        if start == -1:
            return
        if start > 0 and data[start - 1] == 0:
            nal_start = start + 3
            start -= 1
        else:
            nal_start = start + 3

        next_start = data.find(b"\x00\x00\x01", nal_start)
        if next_start == -1:
            yield data[nal_start:]
            return
        if next_start > 0 and data[next_start - 1] == 0:
            nal_end = next_start - 1
        else:
            nal_end = next_start
        yield data[nal_start:nal_end]
        i = next_start
