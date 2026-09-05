import numpy as np
import pytest

import cradlewise_local.streamer as streamer_module
from cradlewise_local.streamer import BridgeStreamer, encode_jpeg


def test_encode_jpeg_returns_single_jpeg_image():
    image = np.zeros((16, 16, 3), dtype=np.uint8)
    image[:, :, 2] = 255

    jpeg = encode_jpeg(image)

    assert jpeg.startswith(b"\xff\xd8")
    assert jpeg.endswith(b"\xff\xd9")


def test_release_media_resources_drops_attempt_owned_codecs():
    streamer = object.__new__(BridgeStreamer)
    streamer._snapshot_decoder = object()
    streamer._audio_resampler = object()

    streamer.release_media_resources()

    assert (streamer._snapshot_decoder, streamer._audio_resampler) == (None, None)


@pytest.mark.asyncio
async def test_run_bridge_releases_media_resources_after_failure(monkeypatch):
    events = []

    class FailingStreamer:
        def __init__(self, *_args):
            return None

        async def run(self):
            events.append("run")
            raise RuntimeError("stream failed")

        def release_media_resources(self):
            events.append("release")

    monkeypatch.setattr(streamer_module, "BridgeStreamer", FailingStreamer)

    with pytest.raises(RuntimeError, match="stream failed"):
        await streamer_module.run_bridge(None, None, None)

    assert events == ["run", "release"]
