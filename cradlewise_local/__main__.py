"""Command line entry point for the Cradlewise bridge."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import time

from .cloud_state import poll_cloud_state
from .commands import BridgeCommandHandler
from .config import BridgeConfig, BridgeConfigError, resolve_secret_value
from .data_api import poll_data_api
from .observability import (
    DisabledErrorReporter,
    ErrorReporter,
    initialize_error_reporting,
)
from .sinks import FfmpegRtspSink
from .status import BridgeStatusHttpServer, BridgeStatusStore
from .streamer import run_bridge

RECONNECT_INITIAL_DELAY_SECONDS = 5
RECONNECT_MAX_DELAY_SECONDS = 60


def _env_int_default(name: str, default: int) -> str:
    """Return a string default so argparse validates environment values."""
    return os.environ.get(name, str(default))


def _parse_bool(value: str) -> bool:
    cleaned = value.strip().lower()
    if cleaned in {"1", "true", "yes", "on"}:
        return True
    if cleaned in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError("expected true or false")


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
    output_url = os.environ.get("CRADLEWISE_OUTPUT_URL")
    parser.add_argument(
        "--output-url",
        default=output_url,
        required=output_url is None,
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
        default=os.environ.get("CRADLEWISE_STATUS_HOST", "127.0.0.1"),
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
    parser.set_defaults(
        cloud_email_file=os.environ.get("CRADLEWISE_EMAIL_FILE"),
        cloud_password_file=os.environ.get("CRADLEWISE_PASSWORD_FILE"),
    )
    parser.add_argument(
        "--cloud-state-poll-interval",
        type=int,
        default=_env_int_default("CRADLEWISE_STATE_POLL_INTERVAL", 30),
        help="Seconds between optional Cradlewise cloud state polls",
    )
    parser.add_argument(
        "--data-api-token",
        default=os.environ.get("CRADLEWISE_DATA_API_TOKEN"),
        help="Token for optional official Data API sleep analytics",
    )
    parser.set_defaults(
        data_api_token_file=os.environ.get("CRADLEWISE_DATA_API_TOKEN_FILE")
    )
    parser.add_argument(
        "--data-api-poll-interval",
        type=int,
        default=_env_int_default("CRADLEWISE_DATA_API_POLL_INTERVAL", 900),
        help="Seconds between optional official Data API sleep polls",
    )
    parser.add_argument(
        "--media-stale-timeout",
        type=int,
        default=_env_int_default("CRADLEWISE_MEDIA_STALE_TIMEOUT", 90),
        help="Restart bridge when video frames stop for this many seconds",
    )
    parser.add_argument(
        "--initial-frame-timeout",
        type=int,
        default=_env_int_default("CRADLEWISE_INITIAL_FRAME_TIMEOUT", 15),
        help="Restart bridge if the first video frame does not arrive in time",
    )
    parser.add_argument(
        "--status-token",
        default=os.environ.get("CRADLEWISE_STATUS_TOKEN"),
        help="Bearer token for status, snapshot, and command HTTP routes",
    )
    parser.set_defaults(
        status_token_file=os.environ.get("CRADLEWISE_STATUS_TOKEN_FILE")
    )
    parser.add_argument(
        "--stream-url",
        default=os.environ.get("CRADLEWISE_STREAM_URL"),
        help="Reader RTSP(S) URL advertised to authenticated API clients",
    )
    parser.add_argument(
        "--metrics-enabled",
        type=_parse_bool,
        default=os.environ.get("CRADLEWISE_METRICS_ENABLED", "false"),
        help="Expose authenticated, label-free Prometheus metrics",
    )
    parser.add_argument(
        "--error-reporting-dsn",
        default=os.environ.get("CRADLEWISE_ERROR_REPORTING_DSN"),
        help="Optional consumer-owned Sentry-compatible DSN",
    )
    parser.set_defaults(
        error_reporting_dsn_file=os.environ.get("CRADLEWISE_ERROR_REPORTING_DSN_FILE")
    )
    parser.add_argument(
        "--error-reporting-environment",
        default=os.environ.get("CRADLEWISE_ERROR_REPORTING_ENVIRONMENT", "production"),
        help="Environment name attached to explicitly enabled error events",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    return parser


def resolve_cloud_credentials(args: argparse.Namespace) -> None:
    """Resolve direct or file-backed cloud credentials into CLI arguments."""
    args.cloud_email = resolve_secret_value(
        direct_value=args.cloud_email,
        file_path=args.cloud_email_file,
        direct_name="CRADLEWISE_EMAIL",
        file_name="CRADLEWISE_EMAIL_FILE",
    )
    args.cloud_password = resolve_secret_value(
        direct_value=args.cloud_password,
        file_path=args.cloud_password_file,
        direct_name="CRADLEWISE_PASSWORD",
        file_name="CRADLEWISE_PASSWORD_FILE",
    )


def resolve_data_api_token(args: argparse.Namespace) -> None:
    """Resolve the direct or file-backed official Data API token."""
    args.data_api_token = resolve_secret_value(
        direct_value=args.data_api_token,
        file_path=args.data_api_token_file,
        direct_name="CRADLEWISE_DATA_API_TOKEN",
        file_name="CRADLEWISE_DATA_API_TOKEN_FILE",
    )


def resolve_status_token(args: argparse.Namespace) -> None:
    """Resolve the bridge HTTP bearer token."""
    args.status_token = resolve_secret_value(
        direct_value=args.status_token,
        file_path=args.status_token_file,
        direct_name="CRADLEWISE_STATUS_TOKEN",
        file_name="CRADLEWISE_STATUS_TOKEN_FILE",
    )


def resolve_error_reporting_dsn(args: argparse.Namespace) -> None:
    """Resolve the optional consumer-owned error-reporting DSN."""
    args.error_reporting_dsn = resolve_secret_value(
        direct_value=args.error_reporting_dsn,
        file_path=args.error_reporting_dsn_file,
        direct_name="CRADLEWISE_ERROR_REPORTING_DSN",
        file_name="CRADLEWISE_ERROR_REPORTING_DSN_FILE",
    )


async def monitor_media_freshness(
    store: BridgeStatusStore,
    stale_timeout: int,
    initial_frame_timeout: int = 15,
    sink: FfmpegRtspSink | None = None,
) -> None:
    """Raise when media or its RTSP sink fails to become or remain healthy."""
    while True:
        interval = min(5, max(1, min(stale_timeout, initial_frame_timeout) // 3))
        await asyncio.sleep(interval)
        if sink is not None:
            store.update_sink_health(sink.health_snapshot())
        snapshot = store.snapshot()
        media = snapshot["media"]
        video_frames = media["video_frames"]
        last_video_frame_at = media["last_video_frame_at"]
        stream_started_at = media["stream_started_at"]
        connection_state = snapshot["webrtc"]["connection_state"]
        ice_state = snapshot["webrtc"]["ice_connection_state"]

        failed_states = {"failed", "closed", "disconnected"}
        if connection_state in failed_states or ice_state in failed_states:
            raise RuntimeError(
                f"WebRTC failed: connection={connection_state}, ice={ice_state}"
            )

        if video_frames <= 0 or last_video_frame_at is None:
            if (
                stream_started_at is not None
                and time.time() - stream_started_at > initial_frame_timeout
            ):
                raise RuntimeError(
                    "first video frame did not arrive within "
                    f"{initial_frame_timeout}s; restarting bridge"
                )
            continue

        age = time.time() - last_video_frame_at
        if age > stale_timeout:
            raise RuntimeError(f"video stream stale for {age:.0f}s; restarting bridge")

        sink_status = snapshot["sink"]
        if sink_status["started"] and not sink_status["healthy"]:
            error = sink_status["error"] or "RTSP sink stopped"
            raise RuntimeError(f"RTSP sink unhealthy: {error}")


def build_rtsp_sink(config: BridgeConfig) -> FfmpegRtspSink:
    """Create a fresh RTSP sink for one local bridge connection attempt."""
    return FfmpegRtspSink(
        output_url=config.output_url,
        ffmpeg_path=config.ffmpeg_path,
        frame_rate=config.frame_rate,
        video_bitrate=config.video_bitrate,
        enable_audio=config.enable_audio,
    )


async def supervise_local_bridge(
    config: BridgeConfig,
    store: BridgeStatusStore,
    command_handler: BridgeCommandHandler | None,
) -> None:
    """Reconnect local MQTT, WebRTC, and RTSP without stopping the status API."""
    reconnect_delay = RECONNECT_INITIAL_DELAY_SECONDS
    while True:
        store.begin_connection_attempt()
        sink = build_rtsp_sink(config)
        bridge_task = asyncio.create_task(
            run_bridge(config, sink, store, command_handler),
            name="cradlewise-local-bridge",
        )
        watchdog_task = asyncio.create_task(
            monitor_media_freshness(
                store,
                config.media_stale_timeout,
                config.initial_frame_timeout,
                sink,
            ),
            name="cradlewise-media-watchdog",
        )
        attempt_tasks = {bridge_task, watchdog_task}
        streamed_video = False
        try:
            done, _ = await asyncio.wait(
                attempt_tasks,
                return_when=asyncio.FIRST_EXCEPTION,
            )
            for task in done:
                task.result()
            raise RuntimeError("local bridge stopped unexpectedly")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            streamed_video = store.snapshot()["media"]["video_frames"] > 0
            retry_delay = (
                RECONNECT_INITIAL_DELAY_SECONDS if streamed_video else reconnect_delay
            )
            store.mark_reconnecting(str(exc))
            logging.warning(
                "Local bridge failed: %s; retrying in %d seconds",
                exc,
                retry_delay,
            )
        finally:
            for task in attempt_tasks:
                task.cancel()
            await asyncio.gather(*attempt_tasks, return_exceptions=True)
            sink.close()
            store.update_sink_health(sink.health_snapshot())

        await asyncio.sleep(retry_delay)
        reconnect_delay = (
            RECONNECT_INITIAL_DELAY_SECONDS
            if streamed_video
            else min(RECONNECT_MAX_DELAY_SECONDS, reconnect_delay * 2)
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
        data_api_token=args.data_api_token,
        data_api_poll_interval=args.data_api_poll_interval,
        media_stale_timeout=args.media_stale_timeout,
        initial_frame_timeout=args.initial_frame_timeout,
        status_token=args.status_token,
        advertised_stream_url=args.stream_url,
        metrics_enabled=args.metrics_enabled,
    )
    store = BridgeStatusStore(
        cradle_id=config.cradle_id,
        crib_ip=config.crib_ip or "discovery",
        cloud_state_stale_after=max(90, config.cloud_state_poll_interval * 3),
        analytics_stale_after=max(1800, config.data_api_poll_interval * 3),
    )
    command_handler = BridgeCommandHandler(state_provider=store.snapshot)
    status_server = BridgeStatusHttpServer(
        store=store,
        host=config.status_host,
        port=config.status_port,
        command_handler=command_handler.handle_request,
        bearer_token=config.status_token,
        advertised_stream_url=config.advertised_stream_url,
        audio_enabled=config.enable_audio,
        cloud_state_enabled=config.cloud_state_enabled,
        data_api_enabled=config.data_api_enabled,
        metrics_enabled=config.metrics_enabled,
    )
    status_server.start()
    logging.info(
        "Status API listening on http://%s:%d",
        config.status_host,
        config.status_port,
    )
    tasks = [
        asyncio.create_task(
            supervise_local_bridge(config, store, command_handler),
            name="cradlewise-local-supervisor",
        )
    ]
    if config.cloud_state_enabled:
        tasks.append(asyncio.create_task(poll_cloud_state(config, store)))
    if config.data_api_enabled:
        tasks.append(asyncio.create_task(poll_data_api(config, store)))
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
    try:
        resolve_cloud_credentials(args)
        resolve_data_api_token(args)
        resolve_status_token(args)
        resolve_error_reporting_dsn(args)
    except BridgeConfigError as exc:
        parser.error(str(exc))
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    reporter: ErrorReporter = DisabledErrorReporter()
    try:
        reporter = initialize_error_reporting(
            args.error_reporting_dsn,
            args.error_reporting_environment,
        )
    except RuntimeError as exc:
        parser.error(str(exc))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def cancel_tasks() -> None:
        for task in asyncio.all_tasks(loop):
            task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, cancel_tasks)

    try:
        loop.run_until_complete(async_main(args))
    except BridgeConfigError as exc:
        parser.error(str(exc))
    except asyncio.CancelledError:
        logging.info("Bridge stopped by signal")
    except KeyboardInterrupt:
        logging.info("Bridge interrupted")
    except Exception as exc:
        reporter.capture_exception(exc)
        reporter.flush()
        logging.exception("Fatal bridge error; exiting process for supervisor restart")
        os._exit(1)
    finally:
        reporter.flush()
        loop.close()


if __name__ == "__main__":
    main()
