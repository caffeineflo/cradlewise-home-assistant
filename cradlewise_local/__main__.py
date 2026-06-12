"""Command line entry point for the Cradlewise bridge."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import time

from .cloud_state import poll_cloud_state
from .config import BridgeConfig, BridgeConfigError
from .sinks import FfmpegRtspSink
from .status import BridgeStatusHttpServer, BridgeStatusStore
from .streamer import run_bridge


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bridge a local Cradlewise WebRTC stream to RTSP"
    )
    parser.add_argument("--cradle-id", required=True, help="Cradle UUID")
    parser.add_argument("--ip", help="Crib IP or hostname; discovers if omitted")
    parser.add_argument(
        "--certs-dir",
        help="Certificate directory; defaults to certs/<cradle-id>",
    )
    parser.add_argument(
        "--output-url",
        required=True,
        help="RTSP URL to push to, for example rtsp://127.0.0.1:8554/cradlewise",
    )
    parser.add_argument("--ffmpeg-path", default="ffmpeg", help="ffmpeg executable")
    parser.add_argument("--frame-rate", type=int, default=10, help="Output frame rate")
    parser.add_argument("--video-bitrate", default="2500k", help="H.264 bitrate")
    parser.add_argument(
        "--no-audio",
        action="store_true",
        help="Publish video only, without muxing the crib audio track",
    )
    parser.add_argument(
        "--status-host",
        default="0.0.0.0",
        help="Host/interface for the bridge status HTTP server",
    )
    parser.add_argument(
        "--status-port",
        type=int,
        default=8080,
        help="Port for the bridge status HTTP server",
    )
    parser.add_argument(
        "--cloud-email",
        default=os.environ.get("CRADLEWISE_EMAIL"),
        help="Cradlewise account email for optional cloud state polling",
    )
    parser.add_argument(
        "--cloud-password",
        default=os.environ.get("CRADLEWISE_PASSWORD"),
        help="Cradlewise account password for optional cloud state polling",
    )
    parser.add_argument(
        "--cloud-state-poll-interval",
        type=int,
        default=_env_int("CRADLEWISE_STATE_POLL_INTERVAL", 30),
        help="Seconds between optional Cradlewise cloud state polls",
    )
    parser.add_argument(
        "--media-stale-timeout",
        type=int,
        default=_env_int("CRADLEWISE_MEDIA_STALE_TIMEOUT", 90),
        help="Restart bridge when video frames stop for this many seconds",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    return parser


async def monitor_media_freshness(
    store: BridgeStatusStore,
    stale_timeout: int,
) -> None:
    """Raise when media has started once and then stops producing video."""
    while True:
        await asyncio.sleep(min(10, max(1, stale_timeout // 3)))
        snapshot = store.snapshot()
        media = snapshot["media"]
        video_frames = media["video_frames"]
        last_video_frame_at = media["last_video_frame_at"]
        if video_frames <= 0 or last_video_frame_at is None:
            continue

        age = time.time() - last_video_frame_at
        if age > stale_timeout:
            raise RuntimeError(
                f"video stream stale for {age:.0f}s; restarting bridge"
            )


async def async_main(args: argparse.Namespace) -> None:
    config = BridgeConfig.from_values(
        cradle_id=args.cradle_id,
        crib_ip=args.ip,
        certs_dir=args.certs_dir,
        output_url=args.output_url,
        ffmpeg_path=args.ffmpeg_path,
        frame_rate=args.frame_rate,
        video_bitrate=args.video_bitrate,
        enable_audio=not args.no_audio,
        status_host=args.status_host,
        status_port=args.status_port,
        cloud_email=args.cloud_email,
        cloud_password=args.cloud_password,
        cloud_state_poll_interval=args.cloud_state_poll_interval,
        media_stale_timeout=args.media_stale_timeout,
    )
    sink = FfmpegRtspSink(
        output_url=config.output_url,
        ffmpeg_path=config.ffmpeg_path,
        frame_rate=config.frame_rate,
        video_bitrate=config.video_bitrate,
        enable_audio=config.enable_audio,
    )
    store = BridgeStatusStore(
        cradle_id=config.cradle_id,
        crib_ip=config.crib_ip or "discovery",
    )
    status_server = BridgeStatusHttpServer(
        store=store,
        host=config.status_host,
        port=config.status_port,
    )
    status_server.start()
    logging.info(
        "Status API listening on http://%s:%d",
        config.status_host,
        config.status_port,
    )
    tasks = [asyncio.create_task(run_bridge(config, sink, store))]
    tasks.append(
        asyncio.create_task(
            monitor_media_freshness(store, config.media_stale_timeout)
        )
    )
    if config.cloud_state_enabled:
        tasks.append(asyncio.create_task(poll_cloud_state(config, store)))
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        for task in done:
            task.result()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        status_server.close()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: [t.cancel() for t in asyncio.all_tasks(loop)])

    try:
        loop.run_until_complete(async_main(args))
    except BridgeConfigError as exc:
        parser.error(str(exc))
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()


if __name__ == "__main__":
    main()
