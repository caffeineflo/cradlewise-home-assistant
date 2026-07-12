"""Configuration helpers for the Cradlewise bridge service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


class BridgeConfigError(ValueError):
    """Raised when bridge configuration is invalid."""


@dataclass(frozen=True)
class BridgeConfig:
    """Runtime settings for a single Cradlewise bridge stream."""

    cradle_id: str
    certs_dir: Path
    output_url: str
    crib_ip: str | None = None
    ffmpeg_path: str = "ffmpeg"
    frame_rate: int = 10
    video_bitrate: str = "2500k"
    enable_audio: bool = True
    status_host: str = "0.0.0.0"
    status_port: int = 8080
    cloud_email: str | None = None
    cloud_password: str | None = None
    cloud_state_poll_interval: int = 30
    media_stale_timeout: int = 90
    initial_frame_timeout: int = 15
    status_token: str | None = None

    @classmethod
    def from_values(
        cls,
        *,
        cradle_id: str,
        certs_dir: str | Path | None,
        output_url: str | None,
        crib_ip: str | None = None,
        ffmpeg_path: str = "ffmpeg",
        frame_rate: int = 10,
        video_bitrate: str = "2500k",
        enable_audio: bool = True,
        status_host: str = "0.0.0.0",
        status_port: int = 8080,
        cloud_email: str | None = None,
        cloud_password: str | None = None,
        cloud_state_poll_interval: int = 30,
        media_stale_timeout: int = 90,
        initial_frame_timeout: int = 15,
        status_token: str | None = None,
    ) -> BridgeConfig:
        """Build and validate config from CLI-style values."""
        if not output_url:
            raise BridgeConfigError(
                "output_url is required via --output-url or CRADLEWISE_OUTPUT_URL"
            )
        resolved_certs = Path(certs_dir) if certs_dir else Path("certs") / cradle_id
        config = cls(
            cradle_id=cradle_id,
            crib_ip=crib_ip,
            certs_dir=resolved_certs,
            output_url=output_url,
            ffmpeg_path=ffmpeg_path,
            frame_rate=frame_rate,
            video_bitrate=video_bitrate,
            enable_audio=enable_audio,
            status_host=status_host,
            status_port=status_port,
            cloud_email=cloud_email,
            cloud_password=cloud_password,
            cloud_state_poll_interval=cloud_state_poll_interval,
            media_stale_timeout=media_stale_timeout,
            initial_frame_timeout=initial_frame_timeout,
            status_token=status_token.strip() if status_token is not None else None,
        )
        config.validate()
        return config

    def validate(self) -> None:
        """Validate static settings and required certificate files."""
        if not self.cradle_id:
            raise BridgeConfigError("cradle_id is required")

        if self.frame_rate <= 0:
            raise BridgeConfigError("frame_rate must be positive")

        if not 1 <= self.status_port <= 65535:
            raise BridgeConfigError("status_port must be between 1 and 65535")

        if self.cloud_state_poll_interval <= 0:
            raise BridgeConfigError("cloud_state_poll_interval must be positive")

        if self.media_stale_timeout <= 0:
            raise BridgeConfigError("media_stale_timeout must be positive")

        if self.initial_frame_timeout <= 0:
            raise BridgeConfigError("initial_frame_timeout must be positive")

        if self.status_token is not None and not self.status_token.strip():
            raise BridgeConfigError("status_token must not be blank")

        if bool(self.cloud_email) != bool(self.cloud_password):
            raise BridgeConfigError(
                "cloud_email and cloud_password must be provided together"
            )

        if not self.output_url:
            raise BridgeConfigError(
                "output_url is required via --output-url or CRADLEWISE_OUTPUT_URL"
            )

        parsed = urlparse(self.output_url)
        if parsed.scheme != "rtsp" or not parsed.netloc:
            raise BridgeConfigError("output_url must be an rtsp:// URL")

        missing = [path.name for path in self.required_cert_paths if not path.exists()]
        if missing:
            joined = ", ".join(missing)
            raise BridgeConfigError(
                f"missing certificate files in {self.certs_dir}: {joined}"
            )

    @property
    def required_cert_paths(self) -> tuple[Path, Path, Path, Path]:
        """Files required for local Greengrass MQTT auth."""
        return (
            self.certs_dir / "ca.pem",
            self.certs_dir / "client_cert.pem",
            self.certs_dir / "client_key.pem",
            self.certs_dir / "device_id",
        )

    @property
    def cloud_state_enabled(self) -> bool:
        """Whether cloud REST state polling should run."""
        return bool(self.cloud_email and self.cloud_password)
