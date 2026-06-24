from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).parents[1]
    / "examples"
    / "home-assistant"
    / "wake-recorder"
    / "cradlewise_wake_recorder.py"
)


def load_recorder_module():
    spec = importlib.util.spec_from_file_location("cradlewise_wake_recorder", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["cradlewise_wake_recorder"] = module
    spec.loader.exec_module(module)
    return module


def test_wake_active_requires_baby_present():
    recorder = load_recorder_module()

    payload = {
        "device_state": {
            "baby_present": False,
            "sleep_phase": "awake",
            "sleep_state": "awake",
        }
    }

    assert recorder.wake_active(payload) is False


def test_wake_active_detects_stirring_baby():
    recorder = load_recorder_module()

    payload = {
        "device_state": {
            "baby_present": True,
            "sleep_phase": "stirring",
            "sleep_state": "asleep",
        }
    }

    assert recorder.wake_active(payload) is True


def test_wake_active_treats_attention_as_active_event():
    recorder = load_recorder_module()

    payload = {
        "device_state": {
            "baby_present": "true",
            "sleep_phase": "sleep",
            "sleep_state": "asleep",
            "baby_needs_attention": "on",
        }
    }

    assert recorder.wake_active(payload) is True


def test_recorder_config_reads_environment(monkeypatch, tmp_path):
    recorder = load_recorder_module()
    monkeypatch.setenv("CRADLEWISE_WAKE_STREAM_URL", "rtsp://example.test/cradlewise")
    monkeypatch.setenv("CRADLEWISE_WAKE_STATUS_URL", "http://example.test/state")
    monkeypatch.setenv("CRADLEWISE_WAKE_BASE_DIR", str(tmp_path))
    monkeypatch.setenv("CRADLEWISE_WAKE_PRE_SECONDS", "90")

    config = recorder.RecorderConfig.from_env()

    assert config.stream_url == "rtsp://example.test/cradlewise"
    assert config.status_url == "http://example.test/state"
    assert config.base_dir == tmp_path
    assert config.pre_seconds == 90


def test_recorder_config_rejects_non_positive_seconds(monkeypatch):
    recorder = load_recorder_module()
    monkeypatch.setenv("CRADLEWISE_WAKE_STREAM_URL", "rtsp://example.test/cradlewise")
    monkeypatch.setenv("CRADLEWISE_WAKE_STATUS_URL", "http://example.test/state")
    monkeypatch.setenv("CRADLEWISE_WAKE_POST_SECONDS", "0")

    with pytest.raises(RuntimeError, match="CRADLEWISE_WAKE_POST_SECONDS"):
        recorder.RecorderConfig.from_env()


def test_claim_pid_replaces_unrelated_live_pid(monkeypatch, tmp_path):
    recorder = load_recorder_module()
    pid_path = tmp_path / "buffer.pid"
    pid_path.write_text("138\n")

    monkeypatch.setattr(recorder, "pid_running", lambda pid: True)
    monkeypatch.setattr(recorder, "process_cmdline", lambda pid: ["s6-supervise"])
    monkeypatch.setattr(recorder.os, "getpid", lambda: 999)

    assert recorder.claim_pid(pid_path, "buffer") is True
    assert pid_path.read_text() == "999\n"


def test_claim_pid_replaces_current_pid_file(monkeypatch, tmp_path):
    recorder = load_recorder_module()
    pid_path = tmp_path / "buffer.pid"
    pid_path.write_text("999\n")

    monkeypatch.setattr(recorder, "pid_running", lambda pid: True)
    monkeypatch.setattr(
        recorder,
        "process_cmdline",
        lambda pid: ["python3", "cradlewise_wake_recorder.py", "buffer"],
    )
    monkeypatch.setattr(recorder.os, "getpid", lambda: 999)

    assert recorder.claim_pid(pid_path, "buffer") is True
    assert pid_path.read_text() == "999\n"


def test_render_gallery_publishes_latest_eight_clips(tmp_path):
    recorder = load_recorder_module()
    config = recorder.RecorderConfig(
        stream_url="rtsp://example.test/cradlewise",
        status_url="http://example.test/state",
        base_dir=tmp_path / "media",
        gallery_dir=tmp_path / "www" / "cradlewise-wake",
    )
    recorder.event_dir(config).mkdir(parents=True)

    for index in range(10):
        clip = recorder.event_dir(config) / f"cradlewise_wake_20260622-120{index:02d}.mp4"
        clip.write_bytes(f"clip-{index}".encode())
        os.utime(clip, (index, index))
        clip.with_suffix(".json").write_text('{"stop_reason": "post_roll_complete"}\n')

    stale = recorder.gallery_clips_dir(config) / "cradlewise_wake_stale.mp4"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"stale")

    recorder.render_gallery(config)

    published = sorted(path.name for path in recorder.gallery_clips_dir(config).glob("*.mp4"))
    assert len(published) == 8
    assert "cradlewise_wake_20260622-12000.mp4" not in published
    assert "cradlewise_wake_20260622-12001.mp4" not in published
    assert "cradlewise_wake_stale.mp4" not in published
    assert "Cradlewise Wake Clips" in (config.gallery_dir / "index.html").read_text()
