#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import html
import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass
from typing import Any


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise RuntimeError(f"{name} must be greater than zero")
    return parsed


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    raise RuntimeError(f"{name} is required")


@dataclass(frozen=True)
class RecorderConfig:
    stream_url: str
    status_url: str
    base_dir: pathlib.Path
    gallery_dir: pathlib.Path = pathlib.Path("/config/www/cradlewise-wake")
    segment_seconds: int = 5
    pre_seconds: int = 120
    post_seconds: int = 120
    buffer_retention_seconds: int = 900
    poll_seconds: int = 5
    max_event_seconds: int = 4 * 60 * 60

    @classmethod
    def from_env(cls) -> "RecorderConfig":
        return cls(
            stream_url=_required_env("CRADLEWISE_WAKE_STREAM_URL"),
            status_url=_required_env("CRADLEWISE_WAKE_STATUS_URL"),
            base_dir=pathlib.Path(
                os.getenv("CRADLEWISE_WAKE_BASE_DIR", "/media/cradlewise-wake")
            ),
            gallery_dir=pathlib.Path(
                os.getenv("CRADLEWISE_WAKE_GALLERY_DIR", "/config/www/cradlewise-wake")
            ),
            segment_seconds=_env_int("CRADLEWISE_WAKE_SEGMENT_SECONDS", 5),
            pre_seconds=_env_int("CRADLEWISE_WAKE_PRE_SECONDS", 120),
            post_seconds=_env_int("CRADLEWISE_WAKE_POST_SECONDS", 120),
            buffer_retention_seconds=_env_int(
                "CRADLEWISE_WAKE_BUFFER_RETENTION_SECONDS", 900
            ),
            poll_seconds=_env_int("CRADLEWISE_WAKE_POLL_SECONDS", 5),
            max_event_seconds=_env_int("CRADLEWISE_WAKE_MAX_EVENT_SECONDS", 4 * 60 * 60),
        )


def log(message: str) -> None:
    timestamp = dt.datetime.now().isoformat(timespec="seconds")
    print(f"{timestamp} {message}", flush=True)


def ffmpeg_path() -> str:
    path = shutil.which("ffmpeg")
    if path:
        return path
    raise RuntimeError("ffmpeg was not found in PATH")


def pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def process_cmdline(pid: int) -> list[str]:
    try:
        raw = pathlib.Path(f"/proc/{pid}/cmdline").read_bytes()
    except FileNotFoundError:
        return []
    return [part.decode(errors="replace") for part in raw.split(b"\0") if part]


def pid_is_recorder(pid: int, mode: str) -> bool:
    if not pid_running(pid):
        return False

    script_name = pathlib.Path(__file__).name
    cmdline = process_cmdline(pid)
    return mode in cmdline and any(
        pathlib.Path(part).name == script_name for part in cmdline
    )


def claim_pid(path: pathlib.Path, mode: str) -> bool:
    if path.exists():
        try:
            pid = int(path.read_text().strip())
        except ValueError:
            path.unlink(missing_ok=True)
        else:
            if pid != os.getpid() and pid_is_recorder(pid, mode):
                return False
            path.unlink(missing_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{os.getpid()}\n")
    return True


def release_pid(path: pathlib.Path) -> None:
    try:
        if int(path.read_text().strip()) == os.getpid():
            path.unlink(missing_ok=True)
    except (FileNotFoundError, ValueError):
        return


def cleanup_old_segments(config: RecorderConfig) -> None:
    cutoff = time.time() - config.buffer_retention_seconds
    for segment in buffer_dir(config).glob("*.ts"):
        try:
            if segment.stat().st_mtime < cutoff:
                segment.unlink()
        except FileNotFoundError:
            continue


def buffer_dir(config: RecorderConfig) -> pathlib.Path:
    return config.base_dir / "buffer"


def event_dir(config: RecorderConfig) -> pathlib.Path:
    return config.base_dir / "events"


def gallery_clips_dir(config: RecorderConfig) -> pathlib.Path:
    return config.gallery_dir / "clips"


def work_dir(config: RecorderConfig) -> pathlib.Path:
    return config.base_dir / "work"


def buffer_pid(config: RecorderConfig) -> pathlib.Path:
    return config.base_dir / "buffer.pid"


def event_pid(config: RecorderConfig) -> pathlib.Path:
    return config.base_dir / "event.pid"


def run_buffer(config: RecorderConfig) -> None:
    if not claim_pid(buffer_pid(config), "buffer"):
        log("buffer already running")
        return

    try:
        render_gallery(config)
        buffer_dir(config).mkdir(parents=True, exist_ok=True)
        pattern = str(buffer_dir(config) / "cradlewise_%Y%m%d-%H%M%S.ts")

        while True:
            cleanup_old_segments(config)
            command = [
                ffmpeg_path(),
                "-hide_banner",
                "-nostdin",
                "-loglevel",
                "warning",
                "-rtsp_transport",
                "tcp",
                "-i",
                config.stream_url,
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c",
                "copy",
                "-f",
                "segment",
                "-segment_format",
                "mpegts",
                "-segment_time",
                str(config.segment_seconds),
                "-reset_timestamps",
                "1",
                "-strftime",
                "1",
                pattern,
            ]
            log("starting rolling buffer")
            process = subprocess.Popen(command)
            process.wait()
            log(f"rolling buffer exited with status {process.returncode}; restarting")
            time.sleep(5)
    finally:
        release_pid(buffer_pid(config))


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def norm(value: Any) -> str:
    return str(value or "").strip().lower()


def fetch_status(config: RecorderConfig) -> dict[str, Any]:
    with urllib.request.urlopen(config.status_url, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Cradlewise status endpoint returned non-object JSON")
    return payload


def wake_active(payload: dict[str, Any]) -> bool:
    device_state = payload.get("device_state")
    if not isinstance(device_state, dict):
        return True

    baby_present = boolish(device_state.get("baby_present"))
    sleep_phase = norm(device_state.get("sleep_phase"))
    sleep_state = norm(device_state.get("sleep_state"))
    attention = boolish(device_state.get("baby_needs_attention"))
    help_needed = boolish(device_state.get("baby_needs_help"))

    phase_awake = sleep_phase in {"awake", "stirring"}
    state_awake = sleep_state not in {
        "",
        "none",
        "unknown",
        "unavailable",
        "asleep",
        "sleep",
        "baby not present",
    }
    return baby_present and (phase_awake or state_awake or attention or help_needed)


def copy_preroll(
    config: RecorderConfig,
    destination: pathlib.Path,
    event_started_at: float,
) -> list[pathlib.Path]:
    destination.mkdir(parents=True, exist_ok=True)
    cutoff = event_started_at - config.pre_seconds - config.segment_seconds
    copied: list[pathlib.Path] = []

    for index, segment in enumerate(sorted(buffer_dir(config).glob("*.ts"))):
        try:
            if segment.stat().st_mtime < cutoff:
                continue
        except FileNotFoundError:
            continue
        target = destination / f"pre_{index:04d}.ts"
        shutil.copy2(segment, target)
        copied.append(target)
    return copied


def stop_process(process: subprocess.Popen[Any]) -> None:
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def record_live(config: RecorderConfig, path: pathlib.Path) -> subprocess.Popen[Any]:
    command = [
        ffmpeg_path(),
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "warning",
        "-rtsp_transport",
        "tcp",
        "-i",
        config.stream_url,
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c",
        "copy",
        "-f",
        "mpegts",
        str(path),
    ]
    return subprocess.Popen(command)


def write_concat_file(path: pathlib.Path, parts: list[pathlib.Path]) -> None:
    lines = [f"file '{part}'\n" for part in parts if part.exists() and part.stat().st_size > 0]
    if not lines:
        raise RuntimeError("no recording segments were available to concatenate")
    path.write_text("".join(lines))


def finalize_clip(
    parts: list[pathlib.Path],
    output: pathlib.Path,
    concat_file: pathlib.Path,
) -> None:
    write_concat_file(concat_file, parts)
    command = [
        ffmpeg_path(),
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "warning",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
        "-map",
        "0",
        "-c",
        "copy",
        "-bsf:a",
        "aac_adtstoasc",
        "-movflags",
        "+faststart",
        str(output),
    ]
    subprocess.run(command, check=True)


def clip_label(path: pathlib.Path) -> str:
    prefix = "cradlewise_wake_"
    stamp = path.stem.removeprefix(prefix)
    try:
        parsed = dt.datetime.strptime(stamp, "%Y%m%d-%H%M%S")
    except ValueError:
        return path.stem
    return parsed.strftime("%b %d, %Y %I:%M %p")


def read_clip_metadata(path: pathlib.Path) -> dict[str, Any]:
    metadata_path = path.with_suffix(".json")
    try:
        metadata = json.loads(metadata_path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    if not isinstance(metadata, dict):
        return {}
    return metadata


def link_or_copy_clip(source: pathlib.Path, target: pathlib.Path) -> None:
    target.unlink(missing_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def latest_clips(config: RecorderConfig, limit: int = 8) -> list[pathlib.Path]:
    clips = [
        path
        for path in event_dir(config).glob("cradlewise_wake_*.mp4")
        if path.is_file()
    ]
    return sorted(clips, key=lambda path: path.stat().st_mtime, reverse=True)[:limit]


def render_gallery(config: RecorderConfig, limit: int = 8) -> None:
    clips = latest_clips(config, limit)
    clips_dir = gallery_clips_dir(config)
    clips_dir.mkdir(parents=True, exist_ok=True)

    keep = {clip.name for clip in clips}
    for old_clip in clips_dir.glob("cradlewise_wake_*.mp4"):
        if old_clip.name not in keep:
            old_clip.unlink(missing_ok=True)

    entries = []
    for clip in clips:
        target = clips_dir / clip.name
        link_or_copy_clip(clip, target)
        metadata = read_clip_metadata(clip)
        stop_reason = html.escape(str(metadata.get("stop_reason", "recorded")))
        size_mb = clip.stat().st_size / (1024 * 1024)
        entries.append(
            f"""
      <article class="clip">
        <video controls preload="metadata" src="clips/{html.escape(clip.name)}"></video>
        <div class="meta">
          <strong>{html.escape(clip_label(clip))}</strong>
          <span>{size_mb:.1f} MB - {stop_reason}</span>
        </div>
      </article>"""
        )

    if entries:
        body = "\n".join(entries)
    else:
        body = """
      <section class="empty">
        <strong>No wake clips yet</strong>
        <span>The next Cradlewise wake event will appear here automatically.</span>
      </section>"""

    generated = dt.datetime.now().strftime("%b %d, %Y %I:%M %p")
    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="300">
  <title>Cradlewise Wake Clips</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #111827;
      --panel: #1f2937;
      --text: #f9fafb;
      --muted: #9ca3af;
      --line: #374151;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 16px;
      background: var(--bg);
      color: var(--text);
      font: 14px system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    header {{
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }}
    h1 {{
      margin: 0;
      font-size: 18px;
      font-weight: 650;
      letter-spacing: 0;
    }}
    .updated {{
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 12px;
    }}
    .clip, .empty {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    video {{
      display: block;
      width: 100%;
      aspect-ratio: 16 / 9;
      background: #000;
    }}
    .meta {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 10px 12px;
    }}
    .meta strong, .empty strong {{
      font-size: 13px;
      font-weight: 650;
    }}
    .meta span, .empty span {{
      color: var(--muted);
      font-size: 12px;
    }}
    .empty {{
      padding: 18px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    @media (max-width: 560px) {{
      body {{ padding: 10px; }}
      header {{ align-items: start; flex-direction: column; }}
      .grid {{ grid-template-columns: 1fr; }}
      .meta {{ align-items: start; flex-direction: column; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Cradlewise Wake Clips</h1>
    <div class="updated">Updated {html.escape(generated)}</div>
  </header>
  <main class="grid">
{body}
  </main>
</body>
</html>
"""
    config.gallery_dir.mkdir(parents=True, exist_ok=True)
    (config.gallery_dir / "index.html").write_text(page)


def run_event(config: RecorderConfig) -> None:
    if not claim_pid(event_pid(config), "event"):
        log("wake recording already running")
        return

    event_started_at = time.time()
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    work = work_dir(config) / stamp
    preroll_dir = work / "preroll"
    live_path = work / "live.ts"
    concat_file = work / "concat.txt"
    final_path = event_dir(config) / f"cradlewise_wake_{stamp}.mp4"
    partial_path = final_path.with_suffix(".mp4.part")
    metadata_path = final_path.with_suffix(".json")

    try:
        event_dir(config).mkdir(parents=True, exist_ok=True)
        work.mkdir(parents=True, exist_ok=True)
        preroll_parts = copy_preroll(config, preroll_dir, event_started_at)
        log(f"copied {len(preroll_parts)} preroll segments")

        process = record_live(config, live_path)
        last_active_at = time.time()
        stop_reason = "post_roll_complete"

        while True:
            now = time.time()
            if now - event_started_at > config.max_event_seconds:
                stop_reason = "max_event_seconds"
                break

            try:
                active = wake_active(fetch_status(config))
            except Exception as exc:
                log(f"status check failed; keeping recording active: {exc}")
                active = True

            if active:
                last_active_at = now
            elif now - last_active_at >= config.post_seconds:
                break

            if process.poll() is not None:
                raise RuntimeError(f"live ffmpeg exited early with status {process.returncode}")

            time.sleep(config.poll_seconds)

        stop_process(process)
        finalize_clip(preroll_parts + [live_path], partial_path, concat_file)
        partial_path.rename(final_path)

        metadata = {
            "created_at": dt.datetime.now().isoformat(timespec="seconds"),
            "event_started_at": dt.datetime.fromtimestamp(event_started_at).isoformat(
                timespec="seconds"
            ),
            "final_path": str(final_path),
            "pre_seconds": config.pre_seconds,
            "post_seconds": config.post_seconds,
            "preroll_segments": len(preroll_parts),
            "stop_reason": stop_reason,
        }
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
        shutil.rmtree(work, ignore_errors=True)
        render_gallery(config)
        log(f"wrote {final_path}")
    finally:
        release_pid(event_pid(config))


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"buffer", "event", "gallery"}:
        raise SystemExit("usage: cradlewise_wake_recorder.py [buffer|event|gallery]")

    config = RecorderConfig.from_env()
    if sys.argv[1] == "buffer":
        run_buffer(config)
    elif sys.argv[1] == "event":
        run_event(config)
    else:
        render_gallery(config)


if __name__ == "__main__":
    main()
