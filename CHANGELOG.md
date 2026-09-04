# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-09-04

### Added

- Home Assistant Repairs for missing, invalid, expired, and soon-to-expire
  provisioned client certificates, with in-place reprovisioning.
- An explicit cloud-registration cleanup action that verifies and removes only
  the current integration's device ID before deleting its config entry.

### Changed

- Explain credential retention and private-key storage for the selected
  connection mode directly in the setup flow.
- Register new certificate clients with randomized Android-style device names
  instead of an identifying Home Assistant label.
- Use the Android app's empty pre-Firebase token state because the integration
  doesn't implement push notifications.

### Fixed

- Retain and observe connection-error shutdown tasks so unload waits for local
  MQTT cleanup and shutdown failures are logged.
- Limit cloud authentication and certificate-download recovery to expected
  provider failures so unexpected errors remain visible.

### Security

- Require HTTPS for non-private media companion destinations and explicit
  consent before accepting HTTP on a private network.
- Require a validated pinned broker CA for local MQTT instead of disabling TLS
  hostname verification when a pin is missing.

## [0.1.0] - 2026-08-29

### Added

- A standalone, media-free `cradlewise-client` Python distribution.
- Automatic local-first/cloud-fallback, local-only, and cloud-only Home
  Assistant connection modes.
- In-place mode reconfiguration, account reauthentication, local broker
  certificate pinning, and local endpoint rediscovery.
- An optional media companion flow; no camera or media dependency is created
  for consumers who do not configure it.
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

- Renamed the unreleased Home Assistant domain from `cradlewise_local` to
  `cradlewise` before public HACS release.
- Reduced the Home Assistant registry surface from 113 entities to 30 without
  media or 31 with media; raw and internal entities are no longer created.
- Local MQTT, WebRTC, and RTSP failures now reconnect with bounded backoff
  without stopping the status API or optional cloud polling.
- A previously healthy stream now retries with the initial delay instead of
  inheriting an outage's maximum reconnect delay.
- Starting music in smart mode now selects the same default sound level as the
  Android app when no smart level has been chosen yet.
- Bound the bridge HTTP server to loopback by default and required a bearer
  token for non-loopback deployments.
- Report upstream HTTP 403 responses as bridge API failures instead of
  incorrectly identifying them as rejected bearer tokens.
- Move MQTT TLS setup and credential-file materialization off Home Assistant's
  event loop.
- Restrict runtime credential directories to mode `0700` and every materialized
  certificate, private key, and device-ID file to mode `0600`.
- Keep an optional companion camera available in Cloud only mode while using
  cloud exclusively for state and controls, with authenticated companion
  health used only for camera availability.
- Reload a reconfigured or reauthenticated entry once through its update
  listener instead of scheduling a second reload.
- Return safe redacted diagnostics while an entry is temporarily unloaded
  during a reload.

[Unreleased]: https://github.com/caffeineflo/cradlewise-home-assistant/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/caffeineflo/cradlewise-home-assistant/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/caffeineflo/cradlewise-home-assistant/releases/tag/v0.1.0
