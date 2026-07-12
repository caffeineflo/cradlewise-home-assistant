# Cradlewise Local

Cradlewise Local bridges a Cradlewise smart crib into Home Assistant with a
local audio/video stream, local device state, and selected crib controls.

The bridge connects to the crib over the LAN using the local Greengrass
MQTT/WebRTC path, publishes an ordinary RTSP stream, and exposes a small HTTP
status/command API. The Home Assistant custom integration creates a camera
entity from that RTSP stream and maps current bridge/device state into a
deliberately limited default entity surface.

## Status

This is early software. It works in a live Home Assistant setup, but it still needs more mileage before a public HACS release.

Working now:

- Local H264 video copied to RTSP without re-encoding
- Crib audio muxed into the same RTSP stream as AAC mono
- Home Assistant camera entity
- A 29-entity default Home Assistant surface, with 78 advanced configuration
  and diagnostic entities available but disabled by default
- Bridge health based on MQTT, WebRTC, recent video, and the RTSP sink
- APK-backed baby, sleep, bounce, music, light, firmware, WiFi, breath,
  lullaby, and crib setting state from the crib's local MQTT shadow
- APK-backed Home Assistant controls for normal soothing/settings actions.
  Discrete APK values use selects, and amplitude, duration, and volume controls
  honor the device-advertised limits.

Still planned:

- Sleep analytics entities
- Packaged releases and HACS release workflow
- More fixture coverage for alternate Cradlewise payload shapes

## Architecture

```text
Cradlewise crib
  -> local MQTT/WebRTC over LAN
  -> cradlewise-local bridge
  -> RTSP H264 passthrough + AAC audio
  -> MediaMTX or another RTSP server
  -> Home Assistant camera
```

The bridge gets normal device state directly from the crib's local MQTT
shadow. Optional `CRADLEWISE_EMAIL` and `CRADLEWISE_PASSWORD` credentials can
provide a cloud fallback, but they are not required for normal operation.

## Home Assistant Installation

Until this has a tagged HACS release, install it as a custom repository:

1. In HACS, add this repository as a custom repository.
2. Choose category `Integration`.
3. Install `Cradlewise Local`.
4. Restart Home Assistant.
5. Add `Cradlewise Local` from Settings -> Devices & services.

The integration asks for:

- Cradle ID
- Authenticated RTSP stream URL, for example
  `rtsps://cradlewise-reader:<password>@cradlewise-rtsp.example.com:443/cradlewise`
- Optional bridge status URL, for example
  `https://cradlewise-api.example.com/state`
- Optional snapshot URL if you expose snapshots separately
- Bridge bearer token matching `CRADLEWISE_STATUS_TOKEN`

With the bridge status URL configured, the default entity set contains the
camera and the high-value baby, sleep, safety, soothing, and environment state
and controls. Configuration and diagnostic entities are present in the entity
registry but disabled by default. An upgrade from config entry version 1
removes obsolete duplicate/cross-domain registry entries and preserves the
unique IDs of retained entities.

## Optional Wake Event Recording

The repository includes an optional native Home Assistant automation that
records wake events with two minutes of lookback and two minutes after each
trigger. It uses `camera.record`, stores clips under Home Assistant's
authenticated `/media` directory, and deletes clips older than 14 days with a
short daily maintenance command. It does not run a separate ffmpeg recorder or
maintain a duplicate rolling buffer.

See [Wake Event Recording](docs/process/wake-event-recording.md) for the
automation and required camera preload setting.

## Bridge Deployment

Fetch the device certificates once:

```bash
uv sync
uv run python fetch_certs.py
```

The script prompts for your Cradlewise email and password. You can also set
`CRADLEWISE_EMAIL` and `CRADLEWISE_PASSWORD` in your shell if you're running it
non-interactively.

That creates:

```text
certs/<cradle_id>/
  ca.pem
  client_cert.pem
  client_key.pem
  device_id
```

Copy `.env.example` to `.env`. Fill in the cradle ID, crib IP, host bind
address, bridge token, and separate RTSP publisher and reader credentials.
Cloud credentials are optional:

```bash
cp .env.example .env
```

For the optional cloud fallback, direct `CRADLEWISE_EMAIL` and
`CRADLEWISE_PASSWORD` values remain supported. A container secret or other
mounted file can instead be supplied with `CRADLEWISE_EMAIL_FILE` and
`CRADLEWISE_PASSWORD_FILE`. Do not configure a non-empty direct value together
with its corresponding `_FILE` variable. File paths are resolved inside the
bridge process, so container deployments must mount them read-only at the
configured paths.

Run the development/trusted-LAN example bridge stack:

```bash
docker compose --env-file .env -f examples/docker-compose.yaml up -d --build
```

The example exposes:

- RTSP: `rtsp://<reader>:<password>@<host>:8560/cradlewise`
- Authenticated bridge state: `http://<host>:8088/state`
- Bridge health: `http://<host>:8088/health`

These direct plaintext ports are for development or a trusted LAN. The verified
site-specific production configuration lives with the host's existing Traefik
stack rather than in this repository and publishes neither `8088` nor `8560`.
The bridge, MediaMTX, and Traefik join the external private Docker network named
`cradlewise-proxy`. Traefik uses its existing `https` entrypoint on port 443: an
HTTP `Host("cradlewise-api.example.com")` router terminates HTTPS to bridge port
8080, while a TCP `HostSNI("cradlewise-rtsp.example.com")` router terminates
RTSPS to MediaMTX port 8554. Plain RTSP remains inside Docker between the
bridge, MediaMTX, and Traefik.

Reconfigure the existing Home Assistant config entry with the HTTPS and RTSPS
URLs. Update the existing Scrypted Rebroadcast/Prebuffer device's source URL in
place. Do not delete and recreate either integration/device; keeping the same
HA entry, Scrypted device, and HomeKit accessory preserves downstream identity
and client metadata.

`/health` is intentionally unauthenticated for container health checks. With
`CRADLEWISE_STATUS_TOKEN` configured, the state, snapshot, and command
endpoints require that bearer token; commands are disabled when no token is
configured. MediaMTX allows only the publisher credential to publish and only
the reader credential to consume the `cradlewise` path. The example containers
run without added Linux capabilities, with `no-new-privileges`, read-only root
filesystems, bounded resources, and rotated container logs. MediaMTX is pinned
by both version and digest.

The bridge returns HTTP 503 from `/health` when MQTT, WebRTC/video freshness,
or the active RTSP sink is unhealthy. It also rejects stale snapshots and marks
stale local/cloud state unavailable. A successful command response means the
APK-shaped desired-shadow update was queued for MQTT publication; the next
reported shadow update is the confirmation of the resulting device state.

## Published Bridge Image

CI builds and publishes the bridge image to GitHub Container Registry:

```text
ghcr.io/caffeineflo/cradlewise-local-bridge
```

Published tags include `main`, `latest`, the short git SHA, and release tags
such as `v0.1.0`. For a server deployment, prefer pulling a published tag and
recreating the bridge container deliberately rather than auto-deploying from CI.

## Local Development

Run tests:

```bash
uv run --extra test python -m pytest
```

Compile-check the Python files:

```bash
uv run python -m compileall cradlewise_local custom_components tests stream_local.py cradlewise_api.py
```

Run the bridge without Docker:

```bash
uv run cradlewise-local \
  --cradle-id 00000000-0000-4000-8000-000000000000 \
  --ip 192.0.2.10 \
  --output-url rtsp://127.0.0.1:8560/cradlewise
```

## Research Notes

The repo includes protocol notes and reverse-engineering references under `docs/`. The most useful starting points are:

- [Home Assistant Local Bridge](docs/process/home-assistant-local-bridge.md)
- [Wake Event Recording](docs/process/wake-event-recording.md)
- [Authentication & Certificates](docs/process/authentication.md)
- [Local Video Streaming](docs/api/local-streaming.md)
- [MQTT Topics & Shadow](docs/api/mqtt-topics.md)
- [REST API Endpoints](docs/api/rest-endpoints.md)
- [Community Implementations](docs/reference/community-implementations.md)

These notes are kept because they explain the compatibility decisions in the bridge, especially local MQTT/WebRTC signaling and the optional cloud state shape.

## Safety Notes

Don't commit `certs/`, `.env`, APKs, or decompiled app output. The repository ignore rules already exclude those paths.

The example uses bearer authentication over HTTP and RTSP credentials over the
LAN; it does not terminate TLS. Bind it to the intended host address and keep
the ports on a trusted network or behind an authenticated TLS proxy.

The Cradlewise API constants in `cradlewise_api.py` are derived from the Android app configuration. They may change when Cradlewise ships app/backend updates.
