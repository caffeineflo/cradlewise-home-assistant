import queue

from cradlewise_local.sinks import FfmpegRtspSink, NullSink


def test_ffmpeg_rtsp_sink_command_copies_h264_and_transcodes_audio():
    sink = FfmpegRtspSink(
        output_url="rtsp://127.0.0.1:8554/cradlewise",
        ffmpeg_path="/usr/bin/ffmpeg",
        frame_rate=12,
    )

    command = sink.build_command()

    assert command[:3] == ["/usr/bin/ffmpeg", "-hide_banner", "-loglevel"]
    assert ["-f", "h264"] in [
        command[index : index + 2]
        for index, value in enumerate(command)
        if value == "-f"
    ]
    assert ["-r", "12"] == command[command.index("-r") : command.index("-r") + 2]
    timestamp_index = command.index("-use_wallclock_as_timestamps")
    assert ["-use_wallclock_as_timestamps", "1"] == command[
        timestamp_index : timestamp_index + 2
    ]
    assert ["-f", "s16le"] in [
        command[index : index + 2]
        for index, value in enumerate(command)
        if value == "-f"
    ]
    assert ["-c:v", "copy"] == command[
        command.index("-c:v") : command.index("-c:v") + 2
    ]
    assert "libx264" not in command
    assert ["-c:a", "aac"] == command[command.index("-c:a") : command.index("-c:a") + 2]
    assert ["-pkt_size", "1200"] == command[
        command.index("-pkt_size") : command.index("-pkt_size") + 2
    ]
    assert command[-1:] == ["rtsp://127.0.0.1:8554/cradlewise"]


def test_ffmpeg_rtsp_sink_command_can_encode_raw_bgr_for_diagnostics():
    sink = FfmpegRtspSink(
        output_url="rtsp://127.0.0.1:8554/cradlewise",
        ffmpeg_path="/usr/bin/ffmpeg",
        frame_rate=12,
        video_bitrate="1800k",
        video_input="raw_bgr",
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
    assert ["-c:a", "aac"] == command[command.index("-c:a") : command.index("-c:a") + 2]
    assert ["-b:v", "1800k"] == command[
        command.index("-b:v") : command.index("-b:v") + 2
    ]
    assert ["-g", "12"] == command[command.index("-g") : command.index("-g") + 2]
    assert ["-keyint_min", "12"] == command[
        command.index("-keyint_min") : command.index("-keyint_min") + 2
    ]
    assert ["-sc_threshold", "0"] == command[
        command.index("-sc_threshold") : command.index("-sc_threshold") + 2
    ]
    assert command[-1:] == ["rtsp://127.0.0.1:8554/cradlewise"]


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

    sink.start_h264()
    sink.write_h264(b"frame")
    sink.write(b"frame")
    sink.write_audio(b"audio")

    assert sink.width is None
    assert sink.height is None
    assert sink.frames == 2
    assert sink.audio_frames == 1


def test_ffmpeg_sink_health_reports_writer_failure():
    sink = FfmpegRtspSink(output_url="rtsp://127.0.0.1:8554/cradlewise")

    class Process:
        def poll(self):
            return None

    class Thread:
        def is_alive(self):
            return True

    sink.process = Process()
    sink.video_thread = Thread()
    assert sink.health_snapshot()["healthy"] is True

    sink._writer_error = "video writer failed: broken pipe"
    health = sink.health_snapshot()

    assert health["healthy"] is False
    assert health["error"] == "video writer failed: broken pipe"


def test_ffmpeg_sink_drops_backlog_and_waits_for_h264_sync():
    sink = FfmpegRtspSink(output_url="rtsp://127.0.0.1:8554/cradlewise")

    class Process:
        returncode = None

        def poll(self):
            return None

    sink.process = Process()
    sink.video_queue = queue.Queue(maxsize=1)
    sink.video_queue.put_nowait(b"pending")

    sink.write_h264(b"next")

    assert sink.health_snapshot()["dropped_video_frames"] == 2


def test_ffmpeg_sink_resumes_on_h264_sync_after_overflow():
    sink = FfmpegRtspSink(output_url="rtsp://127.0.0.1:8554/cradlewise")

    class Process:
        returncode = None

        def poll(self):
            return None

    sink.process = Process()
    sink.video_queue = queue.Queue(maxsize=1)
    sink.video_queue.put_nowait(b"pending")
    sink.write_h264(b"overflow")
    sink.write_h264(b"non-keyframe")

    sync_point = b"\x00\x00\x01\x67\x01\x00\x00\x01\x68\x01\x00\x00\x01\x65\x01"
    sink.write_h264(sync_point)

    assert sink.video_queue.get_nowait() == sync_point


def test_ffmpeg_sink_accepts_a_ten_second_startup_burst():
    sink = FfmpegRtspSink(output_url="rtsp://127.0.0.1:8554/cradlewise")

    class Process:
        returncode = None

        def poll(self):
            return None

    sink.process = Process()
    sink.video_queue = queue.Queue(maxsize=sink.video_queue_capacity)

    for _ in range(sink.frame_rate * 10):
        sink.write_h264(b"frame")

    assert sink.video_queue.qsize() == 100
