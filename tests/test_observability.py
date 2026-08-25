from __future__ import annotations

from types import SimpleNamespace

import cradlewise_local.observability as observability


def test_metrics_contain_only_operational_values() -> None:
    snapshot = {
        "bridge": {
            "healthy": True,
            "uptime_seconds": 120,
            "reconnect_attempts": 3,
            "cradle_id": "00000000-0000-4000-8000-000000000001",
            "crib_ip": "192.0.2.10",
        },
        "mqtt": {"connected": True},
        "webrtc": {
            "connection_state": "connected",
            "ice_connection_state": "connected",
        },
        "media": {
            "video_frames": 42,
            "audio_frames": 12,
            "last_video_frame_at": 995.0,
            "last_audio_frame_at": 990.0,
        },
        "sink": {"healthy": True, "dropped_video_frames": 2},
        "device_state": {
            "available": True,
            "age_seconds": 4.0,
            "baby_present": True,
        },
        "analytics": {"available": False, "age_seconds": None},
    }

    body = observability.render_prometheus_metrics(snapshot, now=1000.0).decode()

    assert (
        "cradlewise_bridge_healthy 1\n" in body,
        "cradlewise_bridge_reconnect_attempts_total 3\n" in body,
        "cradlewise_bridge_last_video_frame_age_seconds 5.0\n" in body,
        "00000000-0000-4000-8000-000000000001" not in body,
        "192.0.2.10" not in body,
        "baby" not in body,
    ) == (True, True, True, True, True, True)


def test_error_reporting_does_not_load_sdk_without_dsn(monkeypatch) -> None:
    def fail_load():
        raise AssertionError("Sentry SDK must not load without an explicit DSN")

    monkeypatch.setattr(observability, "_load_sentry_sdk", fail_load)

    reporter = observability.initialize_error_reporting(None, "production")
    reporter.capture_exception(RuntimeError("local only"))

    assert reporter.enabled is False


def test_error_reporting_uses_privacy_preserving_sdk_options(monkeypatch) -> None:
    calls: dict[str, object] = {}

    def init(**kwargs) -> None:
        calls["init"] = kwargs

    sdk = SimpleNamespace(
        init=init,
        capture_exception=lambda exc: calls.setdefault("exception", exc),
        flush=lambda timeout: calls.setdefault("flush", timeout),
    )
    monkeypatch.setattr(observability, "_load_sentry_sdk", lambda: sdk)

    reporter = observability.initialize_error_reporting(
        "https://public@example.invalid/1",
        "consumer-hosted",
    )
    reporter.capture_exception(RuntimeError("fatal"))
    reporter.flush()
    options = calls["init"]

    assert (
        reporter.enabled,
        options["send_default_pii"],
        options["traces_sample_rate"],
        options["profiles_sample_rate"],
        options["include_local_variables"],
        options["max_breadcrumbs"],
        calls["flush"],
    ) == (True, False, 0.0, 0.0, False, 0, 2.0)


def test_error_reporting_redacts_sensitive_event_fields(monkeypatch) -> None:
    calls: dict[str, object] = {}
    sdk = SimpleNamespace(
        init=lambda **kwargs: calls.setdefault("init", kwargs),
        capture_exception=lambda exc: None,
        flush=lambda timeout: None,
    )
    monkeypatch.setattr(observability, "_load_sentry_sdk", lambda: sdk)
    observability.initialize_error_reporting(
        "https://public@example.invalid/1",
        "consumer-hosted",
    )
    before_send = calls["init"]["before_send"]

    event = before_send(
        {
            "user": {"email": "parent@example.com"},
            "request": {"url": "http://reader:secret@192.0.2.10/state"},
            "breadcrumbs": {"values": [{"message": "crib"}]},
            "exception": {
                "values": [
                    {
                        "value": (
                            "parent@example.com at 192.0.2.10 for "
                            "00000000-0000-4000-8000-000000000001 via "
                            "rtsp://reader:secret@stream.test/cradlewise"
                        )
                    }
                ]
            },
        },
        {},
    )
    rendered = str(event)

    assert (
        "user" not in event,
        "request" not in event,
        "breadcrumbs" not in event,
        "parent@example.com" not in rendered,
        "192.0.2.10" not in rendered,
        "00000000-0000-4000-8000-000000000001" not in rendered,
        "stream.test" not in rendered,
        "secret" not in rendered,
    ) == (True, True, True, True, True, True, True, True)
