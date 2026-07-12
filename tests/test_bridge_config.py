import sys
from pathlib import Path

import pytest

from cradlewise_local.__main__ import build_parser, main, resolve_cloud_credentials
from cradlewise_local.config import (
    BridgeConfig,
    BridgeConfigError,
    resolve_secret_value,
)


def write_cert_set(path: Path) -> None:
    path.mkdir(parents=True)
    for name in ("ca.pem", "client_cert.pem", "client_key.pem", "device_id"):
        (path / name).write_text("test")


def parse_bridge_args():
    return build_parser().parse_args(
        [
            "--cradle-id",
            "cradle",
            "--output-url",
            "rtsp://127.0.0.1:8554/cradlewise",
        ]
    )


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


def test_bridge_cli_keeps_direct_cloud_credentials(monkeypatch):
    monkeypatch.setenv("CRADLEWISE_EMAIL", "user@example.com")
    monkeypatch.setenv("CRADLEWISE_PASSWORD", "direct-secret")
    monkeypatch.delenv("CRADLEWISE_EMAIL_FILE", raising=False)
    monkeypatch.delenv("CRADLEWISE_PASSWORD_FILE", raising=False)
    args = parse_bridge_args()

    resolve_cloud_credentials(args)

    assert (args.cloud_email, args.cloud_password) == (
        "user@example.com",
        "direct-secret",
    )


def test_bridge_cli_reads_cloud_credentials_from_files(tmp_path, monkeypatch):
    email_file = tmp_path / "email"
    password_file = tmp_path / "password"
    email_file.write_text("user@example.com\n")
    password_file.write_text("file-secret\r\n")
    monkeypatch.setenv("CRADLEWISE_EMAIL", "")
    monkeypatch.setenv("CRADLEWISE_PASSWORD", "")
    monkeypatch.setenv("CRADLEWISE_EMAIL_FILE", str(email_file))
    monkeypatch.setenv("CRADLEWISE_PASSWORD_FILE", str(password_file))
    args = parse_bridge_args()

    resolve_cloud_credentials(args)

    assert (args.cloud_email, args.cloud_password) == (
        "user@example.com",
        "file-secret",
    )


def test_bridge_cli_allows_mixed_file_and_direct_cloud_credentials(
    tmp_path, monkeypatch
):
    email_file = tmp_path / "email"
    email_file.write_text("user@example.com\n")
    monkeypatch.setenv("CRADLEWISE_EMAIL", "")
    monkeypatch.setenv("CRADLEWISE_PASSWORD", "direct-secret")
    monkeypatch.setenv("CRADLEWISE_EMAIL_FILE", str(email_file))
    monkeypatch.delenv("CRADLEWISE_PASSWORD_FILE", raising=False)
    args = parse_bridge_args()

    resolve_cloud_credentials(args)

    certs_dir = tmp_path / "certs"
    write_cert_set(certs_dir)
    config = BridgeConfig.from_values(
        cradle_id="cradle",
        certs_dir=certs_dir,
        output_url=args.output_url,
        cloud_email=args.cloud_email,
        cloud_password=args.cloud_password,
    )
    assert config.cloud_state_enabled is True


def test_bridge_cli_rejects_direct_and_file_cloud_credential(tmp_path, monkeypatch):
    email_file = tmp_path / "email"
    email_file.write_text("file-user@example.com")
    monkeypatch.setenv("CRADLEWISE_EMAIL", "direct-user@example.com")
    monkeypatch.setenv("CRADLEWISE_EMAIL_FILE", str(email_file))
    args = parse_bridge_args()

    with pytest.raises(BridgeConfigError, match="cannot both be configured"):
        resolve_cloud_credentials(args)


@pytest.mark.parametrize(
    ("file_name", "contents", "message"),
    [
        ("missing", None, "could not read CRADLEWISE_EMAIL_FILE file"),
        ("blank", " \n", "CRADLEWISE_EMAIL_FILE file is blank"),
    ],
)
def test_file_backed_cloud_credential_rejects_missing_or_blank_file(
    tmp_path, file_name, contents, message
):
    path = tmp_path / file_name
    if contents is not None:
        path.write_text(contents)

    with pytest.raises(BridgeConfigError, match=message):
        resolve_secret_value(
            direct_value=None,
            file_path=str(path),
            direct_name="CRADLEWISE_EMAIL",
            file_name="CRADLEWISE_EMAIL_FILE",
        )


def test_file_backed_cloud_credential_rejects_unreadable_file(tmp_path, monkeypatch):
    path = tmp_path / "email"
    path.write_text("user@example.com")

    def deny_read(self, *args, **kwargs):
        raise PermissionError(13, "Permission denied", self)

    monkeypatch.setattr(Path, "read_text", deny_read)

    with pytest.raises(BridgeConfigError, match="Permission denied"):
        resolve_secret_value(
            direct_value=None,
            file_path=str(path),
            direct_name="CRADLEWISE_EMAIL",
            file_name="CRADLEWISE_EMAIL_FILE",
        )


def test_file_backed_cloud_credential_rejects_blank_file_path():
    with pytest.raises(BridgeConfigError, match="must not be blank"):
        resolve_secret_value(
            direct_value=None,
            file_path=" ",
            direct_name="CRADLEWISE_EMAIL",
            file_name="CRADLEWISE_EMAIL_FILE",
        )


def test_file_backed_cloud_credential_rejects_invalid_utf8(tmp_path):
    path = tmp_path / "email"
    path.write_bytes(b"user@example.com\xff")

    with pytest.raises(BridgeConfigError, match="not valid UTF-8"):
        resolve_secret_value(
            direct_value=None,
            file_path=str(path),
            direct_name="CRADLEWISE_EMAIL",
            file_name="CRADLEWISE_EMAIL_FILE",
        )


def test_bridge_cli_reports_secret_file_error_without_traceback_or_value(
    tmp_path, monkeypatch, capsys
):
    missing_path = tmp_path / "missing-email"
    monkeypatch.setenv("CRADLEWISE_EMAIL_FILE", str(missing_path))
    monkeypatch.setenv("CRADLEWISE_PASSWORD", "not-in-error-output")
    monkeypatch.delenv("CRADLEWISE_EMAIL", raising=False)
    monkeypatch.delenv("CRADLEWISE_PASSWORD_FILE", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cradlewise-local",
            "--cradle-id",
            "cradle",
            "--output-url",
            "rtsp://127.0.0.1:8554/cradlewise",
        ],
    )

    with pytest.raises(SystemExit) as exc_info:
        main()

    error = capsys.readouterr().err
    assert exc_info.value.code == 2
    assert "could not read CRADLEWISE_EMAIL_FILE file" in error
    assert "Traceback" not in error
    assert "not-in-error-output" not in error


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
