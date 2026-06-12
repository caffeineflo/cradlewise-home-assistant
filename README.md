# Cradlewise Local

Cradlewise Local bridges a Cradlewise smart crib into Home Assistant with a local audio/video stream and optional cloud-backed state sensors.

The bridge connects to the crib over the LAN using the local Greengrass MQTT/WebRTC path, publishes an ordinary RTSP stream, and exposes a small HTTP status API. The Home Assistant custom integration creates a camera entity from that RTSP stream and maps bridge/device state into sensors and binary sensors.

## Status

This is early software. It works in a live Home Assistant setup, but it still needs more mileage before a public HACS release.

Working now:

- Local H264 video bridged to RTSP
- Crib audio muxed into the same RTSP stream as AAC mono
- Home Assistant camera entity
- Bridge health, MQTT, WebRTC, and media counters
- Optional cloud state polling for baby presence, sleep phase/state, bouncing, music, light, and selected crib settings

Still planned:

- Home Assistant controls for selected crib actions
- Sleep analytics entities
- Packaged releases and HACS release workflow
- More fixture coverage for alternate Cradlewise payload shapes

## Architecture

```text
Cradlewise crib
  -> local MQTT/WebRTC over LAN
  -> cradlewise-local bridge
  -> RTSP audio/video
  -> MediaMTX or another RTSP server
  -> Home Assistant camera
```

Cloud polling is optional. If you set `CRADLEWISE_EMAIL` and `CRADLEWISE_PASSWORD`, the bridge also polls Cradlewise's REST API for richer device state and exposes it through `/state`. Without those credentials, local audio/video and bridge health still work.

## Home Assistant Installation

Until this has a tagged HACS release, install it as a custom repository:

1. In HACS, add this repository as a custom repository.
2. Choose category `Integration`.
3. Install `Cradlewise Local`.
4. Restart Home Assistant.
5. Add `Cradlewise Local` from Settings -> Devices & services.

The integration asks for:

- Cradle ID
- RTSP stream URL, for example `rtsp://192.0.2.20:8560/cradlewise`
- Optional bridge status URL, for example `http://192.0.2.20:8088/state`
- Optional snapshot URL if you expose snapshots separately

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

Copy `.env.example` to `.env` and fill in your cradle ID, crib IP, and optional cloud credentials:

```bash
cp .env.example .env
```

Run the example bridge stack:

```bash
docker compose --env-file .env -f examples/docker-compose.yaml up -d --build
```

The example exposes:

- RTSP: `rtsp://<host>:8560/cradlewise`
- Bridge state: `http://<host>:8088/state`
- Bridge health: `http://<host>:8088/health`

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
- [Authentication & Certificates](docs/process/authentication.md)
- [Local Video Streaming](docs/api/local-streaming.md)
- [MQTT Topics & Shadow](docs/api/mqtt-topics.md)
- [REST API Endpoints](docs/api/rest-endpoints.md)
- [Community Implementations](docs/reference/community-implementations.md)

These notes are kept because they explain the compatibility decisions in the bridge, especially local MQTT/WebRTC signaling and the optional cloud state shape.

## Safety Notes

Don't commit `certs/`, `.env`, APKs, or decompiled app output. The repository ignore rules already exclude those paths.

The Cradlewise API constants in `cradlewise_api.py` are derived from the Android app configuration. They may change when Cradlewise ships app/backend updates.
