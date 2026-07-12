from pathlib import Path

import pytest

from cradlewise_local.__main__ import build_parser
from cradlewise_local.config import BridgeConfig, BridgeConfigError


def write_cert_set(path: Path) -> None:
    path.mkdir(parents=True)
    for name in ("ca.pem", "client_cert.pem", "client_key.pem", "device_id"):
        (path / name).write_text("test")


def test_bridge_config_defaults_certs_dir(tmp_path, monkeypatch):
    cradle_id = "00000000-0000-4000-8000-000000000000"
    certs_dir = tmp_path / "certs" / cradle_id
    write_cert_set(certs_dir)
    monkeypatch.chdir(tmp_path)

    config = BridgeConfig.from_values(
        cradle_id=cradle_id,
        certs_dir=None,
        output_url="rtsp://127.0.0.1:8554/cradlewise",
    )

    assert config.certs_dir == Path("certs") / cradle_id
    assert config.frame_rate == 10
    assert config.enable_audio is True


def test_bridge_config_can_disable_audio(tmp_path):
    certs_dir = tmp_path / "certs"
    write_cert_set(certs_dir)

    config = BridgeConfig.from_values(
        cradle_id="cradle",
        certs_dir=certs_dir,
        output_url="rtsp://127.0.0.1:8554/cradlewise",
        enable_audio=False,
    )

    assert config.enable_audio is False


def test_bridge_config_enables_cloud_state_with_credentials(tmp_path):
    certs_dir = tmp_path / "certs"
    write_cert_set(certs_dir)

    config = BridgeConfig.from_values(
        cradle_id="cradle",
        certs_dir=certs_dir,
        output_url="rtsp://127.0.0.1:8554/cradlewise",
        cloud_email="user@example.com",
        cloud_password="secret",
        cloud_state_poll_interval=60,
    )

    assert config.cloud_state_enabled is True
    assert config.cloud_state_poll_interval == 60


def test_bridge_config_accepts_media_stale_timeout(tmp_path):
    certs_dir = tmp_path / "certs"
    write_cert_set(certs_dir)

    config = BridgeConfig.from_values(
        cradle_id="cradle",
        certs_dir=certs_dir,
        output_url="rtsp://127.0.0.1:8554/cradlewise",
        media_stale_timeout=120,
    )

    assert config.media_stale_timeout == 120


def test_bridge_config_accepts_initial_frame_timeout_and_status_token(tmp_path):
    certs_dir = tmp_path / "certs"
    write_cert_set(certs_dir)

    config = BridgeConfig.from_values(
        cradle_id="cradle",
        certs_dir=certs_dir,
        output_url="rtsp://127.0.0.1:8554/cradlewise",
        initial_frame_timeout=20,
        status_token="secret",
    )

    assert config.initial_frame_timeout == 20
    assert config.status_token == "secret"


def test_bridge_config_rejects_blank_status_token(tmp_path):
    certs_dir = tmp_path / "certs"
    write_cert_set(certs_dir)

    with pytest.raises(BridgeConfigError, match="must not be blank"):
        BridgeConfig.from_values(
            cradle_id="cradle",
            certs_dir=certs_dir,
            output_url="rtsp://127.0.0.1:8554/cradlewise",
            status_token=" ",
        )


def test_bridge_cli_rejects_invalid_integer_environment_value(monkeypatch):
    monkeypatch.setenv("CRADLEWISE_MEDIA_STALE_TIMEOUT", "not-an-integer")
    parser = build_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(
            [
                "--cradle-id",
                "cradle",
                "--output-url",
                "rtsp://127.0.0.1:8554/cradlewise",
            ]
        )

    assert exc_info.value.code == 2


def test_bridge_cli_reads_output_url_from_environment(monkeypatch):
    monkeypatch.setenv(
        "CRADLEWISE_OUTPUT_URL", "rtsp://publisher:secret@mediamtx:8554/cradlewise"
    )
    parser = build_parser()

    args = parser.parse_args(["--cradle-id", "cradle"])

    assert args.output_url == "rtsp://publisher:secret@mediamtx:8554/cradlewise"


def test_bridge_cli_requires_output_url_without_environment(monkeypatch):
    monkeypatch.delenv("CRADLEWISE_OUTPUT_URL", raising=False)
    parser = build_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--cradle-id", "cradle"])

    assert exc_info.value.code == 2


def test_bridge_config_requires_cloud_credentials_together(tmp_path):
    certs_dir = tmp_path / "certs"
    write_cert_set(certs_dir)

    with pytest.raises(BridgeConfigError, match="provided together"):
        BridgeConfig.from_values(
            cradle_id="cradle",
            certs_dir=certs_dir,
            output_url="rtsp://127.0.0.1:8554/cradlewise",
            cloud_email="user@example.com",
        )


def test_bridge_config_rejects_non_rtsp_url(tmp_path):
    certs_dir = tmp_path / "certs"
    write_cert_set(certs_dir)

    with pytest.raises(BridgeConfigError, match="rtsp://"):
        BridgeConfig.from_values(
            cradle_id="cradle",
            certs_dir=certs_dir,
            output_url="http://127.0.0.1:8080/cradlewise",
        )


def test_bridge_config_requires_all_cert_files(tmp_path):
    certs_dir = tmp_path / "certs"
    certs_dir.mkdir()

    with pytest.raises(BridgeConfigError, match="missing certificate files"):
        BridgeConfig.from_values(
            cradle_id="cradle",
            certs_dir=certs_dir,
            output_url="rtsp://127.0.0.1:8554/cradlewise",
        )
