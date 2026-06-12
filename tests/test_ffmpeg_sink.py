from cradlewise_local.sinks import FfmpegRtspSink, NullSink


def test_ffmpeg_rtsp_sink_command_uses_raw_bgr_and_pcm_inputs():
    sink = FfmpegRtspSink(
        output_url="rtsp://127.0.0.1:8554/cradlewise",
        ffmpeg_path="/usr/bin/ffmpeg",
        frame_rate=12,
        video_bitrate="1800k",
    )

    command = sink.build_command(1280, 720)

    assert command[:3] == ["/usr/bin/ffmpeg", "-hide_banner", "-loglevel"]
    assert ["-f", "rawvideo"] == command[command.index("-f") : command.index("-f") + 2]
    assert "1280x720" in command
    assert ["-framerate", "12"] == command[
        command.index("-framerate") : command.index("-framerate") + 2
    ]
    assert ["-f", "s16le"] in [
        command[index : index + 2]
        for index, value in enumerate(command)
        if value == "-f"
    ]
    assert ["-c:a", "aac"] == command[
        command.index("-c:a") : command.index("-c:a") + 2
    ]
    assert ["-b:v", "1800k"] == command[command.index("-b:v") : command.index("-b:v") + 2]
    assert ["-g", "12"] == command[command.index("-g") : command.index("-g") + 2]
    assert ["-keyint_min", "12"] == command[
        command.index("-keyint_min") : command.index("-keyint_min") + 2
    ]
    assert ["-sc_threshold", "0"] == command[
        command.index("-sc_threshold") : command.index("-sc_threshold") + 2
    ]
    assert command[-2:] == ["tcp", "rtsp://127.0.0.1:8554/cradlewise"]


def test_ffmpeg_rtsp_sink_can_disable_audio():
    sink = FfmpegRtspSink(
        output_url="rtsp://127.0.0.1:8554/cradlewise",
        enable_audio=False,
    )

    command = sink.build_command(1280, 720)

    assert "-an" in command
    assert "-c:a" not in command
    assert "s16le" not in command


def test_null_sink_counts_frames():
    sink = NullSink()

    sink.start(1280, 720)
    sink.write(b"frame")
    sink.write(b"frame")
    sink.write_audio(b"audio")

    assert sink.width == 1280
    assert sink.height == 720
    assert sink.frames == 2
    assert sink.audio_frames == 1
