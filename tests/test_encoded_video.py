import asyncio
import queue

from aiortc.rtcrtpparameters import RTCRtpCodecParameters
from aiortc import rtcrtpreceiver
from aiortc.jitterbuffer import JitterFrame

from cradlewise_local.encoded import h264_nal_types, install_encoded_frame_tap
from cradlewise_local.streamer import BridgeStreamer


def test_h264_nal_types_reads_three_and_four_byte_start_codes():
    data = (
        b"\x00\x00\x00\x01\x67sps"
        b"\x00\x00\x01\x68pps"
        b"\x00\x00\x00\x01\x65idr"
    )

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
