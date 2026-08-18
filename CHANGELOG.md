# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- A guarded `cradlewise-pin-mqtt-ca` command for validating and pinning the
  Greengrass v2 MQTT core CA.
- Optional official Cradlewise Data API polling for six daily sleep metrics.
- File-backed secrets for cloud credentials and the official Data API token.
- Authenticated bridge status, snapshot, and command endpoints.
- Authenticated RTSP publishing and reading through MediaMTX.
- Home Assistant config flow, diagnostics, controls, camera, and wake recorder.
- Reproducible bridge container builds and GHCR publishing in CI.

### Changed

- Local MQTT, WebRTC, and RTSP failures now reconnect with bounded backoff
  without stopping the status API or optional cloud polling.
- Limited the default Home Assistant surface to high-value entities and kept
  advanced configuration and diagnostics disabled by default.
- Preserved `cradlewise_local` entity and device identity while using the plain
  `Cradlewise` display name required by Home Assistant naming guidance.
