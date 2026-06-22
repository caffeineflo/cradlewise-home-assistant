"""Video frame sinks for the Cradlewise bridge."""

from __future__ import annotations

import os
import queue
import subprocess
import threading
from dataclasses import dataclass
from typing import BinaryIO, Literal, Protocol


class FrameSink(Protocol):
    """Accepts media frames from aiortc."""

    def start(self, width: int, height: int) -> None:
        """Prepare the sink for decoded frames of the given size."""

    def start_h264(self) -> None:
        """Prepare the sink for encoded H.264 access units."""

    def write(self, frame_bytes: bytes) -> None:
        """Write one BGR24 frame."""

    def write_h264(self, frame_bytes: bytes) -> None:
        """Write one Annex B H.264 access unit."""

    def write_audio(self, frame_bytes: bytes) -> None:
        """Write one chunk of signed 16-bit little-endian PCM audio."""

    def close(self) -> None:
        """Release sink resources."""


@dataclass
class NullSink:
    """Sink used for probes and tests."""

    frames: int = 0
    audio_frames: int = 0
    width: int | None = None
    height: int | None = None

    def start(self, width: int, height: int) -> None:
        self.width = width
        self.height = height

    def start_h264(self) -> None:
        self.width = None
        self.height = None

    def write(self, frame_bytes: bytes) -> None:
        self.frames += 1

    def write_h264(self, frame_bytes: bytes) -> None:
        self.frames += 1

    def write_audio(self, frame_bytes: bytes) -> None:
        self.audio_frames += 1

    def close(self) -> None:
        return None


@dataclass
class FfmpegRtspSink:
    """Push video and audio to an RTSP endpoint using ffmpeg."""

    output_url: str
    ffmpeg_path: str = "ffmpeg"
    frame_rate: int = 10
    video_bitrate: str = "2500k"
    video_input: Literal["h264", "raw_bgr"] = "h264"
    enable_audio: bool = True
    audio_sample_rate: int = 48000
    audio_channels: int = 1
    audio_bitrate: str = "96k"
    rtp_packet_size: int = 1200
    loglevel: str = "warning"
    process: subprocess.Popen | None = None
    audio_stdin: BinaryIO | None = None
    video_queue: queue.Queue[bytes | None] | None = None
    audio_queue: queue.Queue[bytes | None] | None = None
    video_thread: threading.Thread | None = None
    audio_thread: threading.Thread | None = None

    def build_command(
        self,
        width: int | None = None,
        height: int | None = None,
        audio_pipe: str = "pipe:3",
    ) -> list[str]:
        """Return the ffmpeg command for the current output settings."""
        command = [
            self.ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            self.loglevel,
            "-thread_queue_size",
            "512",
        ]
        if self.video_input == "h264":
            command.extend(
                [
                    "-fflags",
                    "+genpts",
                    "-use_wallclock_as_timestamps",
                    "1",
                    "-f",
                    "h264",
                    "-r",
                    str(self.frame_rate),
                    "-i",
                    "pipe:0",
                ]
            )
        else:
            if width is None or height is None:
                raise ValueError("width and height are required for raw_bgr video")
            command.extend(
                [
                    "-re",
                    "-f",
                    "rawvideo",
                    "-pixel_format",
                    "bgr24",
                    "-video_size",
                    f"{width}x{height}",
                    "-framerate",
                    str(self.frame_rate),
                    "-i",
                    "pipe:0",
                ]
            )
        if self.enable_audio:
            command.extend(
                [
                    "-f",
                    "s16le",
                    "-thread_queue_size",
                    "512",
                    "-ar",
                    str(self.audio_sample_rate),
                    "-ac",
                    str(self.audio_channels),
                    "-i",
                    audio_pipe,
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                ]
            )
        else:
            command.append("-an")

        if self.video_input == "h264":
            command.extend(["-c:v", "copy"])
        else:
            command.extend(
                [
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-tune",
                    "zerolatency",
                    "-b:v",
                    self.video_bitrate,
                    "-g",
                    str(self.frame_rate),
                    "-keyint_min",
                    str(self.frame_rate),
                    "-sc_threshold",
                    "0",
                    "-pix_fmt",
                    "yuv420p",
                ]
            )
        if self.enable_audio:
            command.extend(
                [
                    "-c:a",
                    "aac",
                    "-b:a",
                    self.audio_bitrate,
                    "-ar",
                    str(self.audio_sample_rate),
                    "-ac",
                    str(self.audio_channels),
                ]
            )

        command.extend(
            [
                "-f",
                "rtsp",
                "-rtsp_transport",
                "tcp",
                "-pkt_size",
                str(self.rtp_packet_size),
                self.output_url,
            ]
        )
        return command

    def start(self, width: int, height: int) -> None:
        if self.video_input != "raw_bgr":
            raise RuntimeError("start() is only valid for raw_bgr video input")
        self._start(width=width, height=height)

    def start_h264(self) -> None:
        if self.video_input != "h264":
            raise RuntimeError("start_h264() is only valid for h264 video input")
        self._start()

    def _start(self, width: int | None = None, height: int | None = None) -> None:
        if self.process is not None:
            return
        audio_read_fd: int | None = None
        audio_write_fd: int | None = None
        pass_fds: tuple[int, ...] = ()
        command = self.build_command(width, height)
        try:
            if self.enable_audio:
                audio_read_fd, audio_write_fd = os.pipe()
                pass_fds = (audio_read_fd,)
                command = self.build_command(width, height, f"pipe:{audio_read_fd}")

            self.process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                pass_fds=pass_fds,
            )
            if audio_write_fd is not None:
                self.audio_stdin = os.fdopen(audio_write_fd, "wb", buffering=0)
                audio_write_fd = None
                self.audio_queue = queue.Queue(maxsize=64)
                self.audio_thread = self._start_writer(
                    "cradlewise-ffmpeg-audio",
                    self.audio_stdin,
                    self.audio_queue,
                )
            if self.process.stdin is not None:
                self.video_queue = queue.Queue(maxsize=2)
                self.video_thread = self._start_writer(
                    "cradlewise-ffmpeg-video",
                    self.process.stdin,
                    self.video_queue,
                )
        finally:
            if audio_read_fd is not None:
                os.close(audio_read_fd)
            if audio_write_fd is not None:
                os.close(audio_write_fd)

    def write(self, frame_bytes: bytes) -> None:
        if self.process is None or self.video_queue is None:
            raise RuntimeError("ffmpeg sink has not been started")
        if self.process.poll() is not None:
            raise RuntimeError(f"ffmpeg exited with status {self.process.returncode}")
        self._offer(self.video_queue, frame_bytes)

    def write_h264(self, frame_bytes: bytes) -> None:
        if self.process is None or self.video_queue is None:
            raise RuntimeError("ffmpeg sink has not been started")
        if self.process.poll() is not None:
            raise RuntimeError(f"ffmpeg exited with status {self.process.returncode}")
        self._offer(self.video_queue, frame_bytes)

    def write_audio(self, frame_bytes: bytes) -> None:
        if not self.enable_audio or self.process is None or self.audio_queue is None:
            return
        if self.process.poll() is not None:
            raise RuntimeError(f"ffmpeg exited with status {self.process.returncode}")
        self._offer(self.audio_queue, frame_bytes)

    def _start_writer(
        self,
        name: str,
        stream: BinaryIO,
        media_queue: queue.Queue[bytes | None],
    ) -> threading.Thread:
        thread = threading.Thread(
            target=self._writer_loop,
            args=(stream, media_queue),
            name=name,
            daemon=True,
        )
        thread.start()
        return thread

    @staticmethod
    def _writer_loop(
        stream: BinaryIO,
        media_queue: queue.Queue[bytes | None],
    ) -> None:
        while True:
            chunk = media_queue.get()
            if chunk is None:
                return
            try:
                stream.write(chunk)
                stream.flush()
            except (BrokenPipeError, OSError):
                return

    @staticmethod
    def _offer(media_queue: queue.Queue[bytes | None], chunk: bytes) -> None:
        try:
            media_queue.put_nowait(chunk)
            return
        except queue.Full:
            pass

        try:
            media_queue.get_nowait()
        except queue.Empty:
            pass

        try:
            media_queue.put_nowait(chunk)
        except queue.Full:
            pass

    def close(self) -> None:
        if self.process is None:
            return
        for media_queue in (self.video_queue, self.audio_queue):
            if media_queue is not None:
                self._offer(media_queue, None)
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        for thread in (self.video_thread, self.audio_thread):
            if thread is not None:
                thread.join(timeout=2)
        if self.process.stdin:
            self.process.stdin.close()
        if self.audio_stdin:
            self.audio_stdin.close()
            self.audio_stdin = None
        self.video_queue = None
        self.audio_queue = None
        self.video_thread = None
        self.audio_thread = None
        self.process = None
