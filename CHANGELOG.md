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
- A versioned, authenticated bridge `/info` contract for compact HA setup.
- Opt-in authenticated Prometheus metrics with no identifying labels.
- Opt-in Sentry-compatible fatal error reporting with privacy redaction.
- A dedicated `/live` probe that keeps API routing available during media
  outages without weakening semantic `/health` checks.

### Changed

- Local MQTT, WebRTC, and RTSP failures now reconnect with bounded backoff
  without stopping the status API or optional cloud polling.
- A previously healthy stream now retries with the initial delay instead of
  inheriting an outage's maximum reconnect delay.
- Starting music in smart mode now selects the same default sound level as the
  Android app when no smart level has been chosen yet.
- Limited the default Home Assistant surface to high-value entities and kept
  advanced configuration and diagnostics disabled by default.
- Preserved `cradlewise_local` entity and device identity while using the plain
  `Cradlewise` display name required by Home Assistant naming guidance.
- Reduced Home Assistant setup to a bridge URL and bearer token while
  preserving existing config-entry, entity, camera, and HomeKit identities.
- Bound the bridge HTTP server to loopback by default and required a bearer
  token for non-loopback deployments.
