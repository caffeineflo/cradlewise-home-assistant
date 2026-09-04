# Cradlewise

Cradlewise is an unofficial, local-first Home Assistant integration for the
Cradlewise smart crib. State and controls work without a video bridge. Cloud
fallback and live media are independent choices.

This project is based on interoperability research against the Cradlewise
Android app and crib firmware. It is not affiliated with or supported by
Cradlewise.

The current protocol surface is validated against Android app 2.55.5
(version code 204) and live crib firmware 0.2.73.

## Purpose and scope

This is an unofficial, independently developed interoperability project for
people who lawfully own or are authorized to use a Cradlewise crib. It connects
the crib's existing state, controls, and media interfaces to Home Assistant so
owners can use the basic functions of their hardware on their own network.

The project does not unlock subscription-gated features, bypass paid API
entitlements, access another user's crib or account, modify Cradlewise firmware,
disable manufacturer safety limits, or defeat device authentication. Users must
supply their own Cradlewise account and hardware.

Local-only mode uses the user's authenticated account once during setup to
identify the crib and provision its device certificate. It then discards the
email and password and performs no ongoing cloud polling. Cloud access after
setup is optional and uses only the user's authenticated account.

This repository contains independently written compatibility code. It does not
distribute Cradlewise application or firmware code, extracted APK contents,
user passwords, temporary cloud credentials, provisioned private keys, nursery
recordings, or other user data.

Contributions that add subscription or paywall circumvention, cross-account
access, firmware modification, safety-limit bypasses, or copied Cradlewise
application or firmware code are out of scope.

## Use at your own risk

This project is unofficial and is not approved, endorsed, or supported by
Cradlewise. Use it only with a crib and account you own or are authorized to
access, and at your own discretion and risk.

Cradlewise's [Terms of Service](https://cradlewise.com/legal/terms-of-service/)
currently restrict reverse engineering, decompiling, and attempts to obtain
non-public APIs. The terms also state that Cradlewise may restrict or suspend
access to its platform if it determines that they have been violated. Terms,
services, and enforcement may change, and the enforceability of particular
restrictions may vary by jurisdiction. You are responsible for reviewing the
terms and laws that apply to you.

As of September 3, 2026, the maintainers are not aware of any account or crib
being restricted specifically because this project was used. This is not a
guarantee. Cradlewise may change or discontinue the cloud services,
credentials, and protocols on which some connection modes depend. The project
maintainers cannot restore an account or crib's access to Cradlewise services.
This project does not provide legal advice. The software remains subject to the
warranty and liability terms in the [MIT License](LICENSE).

## Status

The supported release surface is intentionally small:

- Direct local MQTT state and controls over the crib's mTLS Greengrass broker
- Cradlewise AWS IoT MQTT state and controls for cloud fallback or cloud-only use
- Automatic local-first provider selection without retrying a command across
  providers
- Account reauthentication and in-place connection-mode changes
- 30 focused entities without media, or 31 with the optional camera
- 28 entities enabled by default without media; state-source and state-update
  diagnostics are opt-in
- An optional, separately deployed WebRTC-to-RTSP media companion
- Privacy-safe Home Assistant diagnostics with credentials and certificate
  material redacted

The official Cradlewise Data API is not required. It remains a possible future
analytics provider for users who want subscription-backed sleep history.

## Connection modes

| Mode | Local MQTT | Cradlewise cloud | Stored account password |
|---|---:|---:|---:|
| Automatic | Preferred | Fallback | Yes |
| Local only | Yes | Setup only | No |
| Cloud only | No | Yes | Yes |

All three modes use a device certificate provisioned through the same backend
flow as the Android app. Local-only setup uses the account once for discovery
and provisioning, then discards the email and password. Automatic and
cloud-only modes retain them in the Home Assistant config entry so temporary
AWS credentials can be renewed and the REST fallback can reauthenticate.

Home Assistant stores retained account credentials and all provisioned device
certificate material in its standard config-entry storage. This integration
does not add application-level encryption; masking the password in the setup
form only prevents it from being displayed while it is entered. Protect access
to `/config`, Home Assistant backups, and administrator accounts. Local-only
mode still retains the device private key required for authenticated local MQTT.
If the optional media companion is configured, its bearer token and stream URL
are stored in the same config entry's options.

Cloud only applies to state and controls. If the optional media companion is
configured, its local camera can remain available, but Home Assistant does not
read device state from it or send commands through it in Cloud only mode. It
polls only the companion's authenticated semantic health endpoint to report
camera availability accurately.

Automatic mode accepts a rediscovered local address only when the broker still
presents the pinned core CA. It never replaces a different CA unattended. If a
firmware update rotates that CA, use the integration's Reconfigure action to
revalidate and explicitly trust the broker's current CA. Local-only
reconfiguration does not store account credentials.

## Architecture

```text
Home Assistant integration
  -> cradlewise-client (state, controls, discovery, certificate provisioning)
     -> local crib MQTT, preferred in Automatic mode
     -> Cradlewise AWS IoT MQTT, fallback or Cloud-only mode
     -> low-rate Cradlewise REST state fallback

Optional media companion
  -> local crib MQTT/WebRTC
  -> H264 passthrough and AAC audio
  -> MediaMTX or another RTSP server
  -> optional Home Assistant camera entity
```

`packages/cradlewise-client/` is a media-free Python distribution. The
`custom_components/cradlewise/` package is the HACS integration. The existing
`cradlewise_local/` application owns the optional video companion and its
container-facing status API. The integration never starts WebRTC or processes
nursery audio/video unless the consumer separately deploys and configures that
companion.

When the media companion is configured, it owns the local MQTT identity used
for WebRTC signaling and local state. Home Assistant does not open a competing
local MQTT session. Automatic mode can still keep the independent AWS IoT
provider ready as fallback. Cloud only can use the companion's camera without
using its local state or command path.

## Home Assistant installation

Add the repository to HACS directly:

[![Open your Home Assistant instance and add this repository to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=caffeineflo&repository=cradlewise-home-assistant&category=integration)

The button adds this repository to HACS. It does not download or configure the
integration.

If the redirect is unavailable, add the repository manually:

1. Open HACS and select the three-dot menu in the top-right corner.
2. Select **Custom repositories**.
3. Enter `https://github.com/caffeineflo/cradlewise-home-assistant`.
4. Select **Integration** as the type and click **Add**.

After the repository is added:

1. Open `Cradlewise` in HACS, select **Download**, and restart Home Assistant.
2. Open Settings -> Devices & services -> Add Integration -> Cradlewise.
3. Choose Automatic, Local only, or Cloud only.
4. Sign in once so the integration can discover the crib and provision its
   device certificate.

The account step explains exactly which credentials the selected mode retains.
Provisioning creates a device registration whose name follows the Android app's
`model_random-id` shape instead of identifying Home Assistant. The integration
doesn't register for Firebase push notifications and sends the empty-token state
used by the Android app before Firebase supplies a token. It stores the returned
device ID and certificate material, not that display name.

To add video later, open the integration's Configure action, select **Configure
optional media companion**, and enter the companion URL and bearer token.
HTTPS is required for any non-private destination. HTTP is accepted only when
every resolved address is private, loopback, or link-local and you explicitly
accept the plaintext trusted-LAN connection. Leaving the URL blank removes the
camera and does not affect state, controls, device identity, or other entities.

Home Assistant creates a Repair if the provisioned client certificate is
missing, malformed, expired, not valid yet, or within 30 days of expiration.
The repair provisions and validates a replacement without changing the config
entry, integration device, or entity IDs. Removing the previous registration
after successful repair is optional and off by default.

Removing the integration normally leaves its provisioned device registration
in the Cradlewise account. To remove both deliberately, open **Configure**,
select **Remove cloud registration and integration**, review the Apple Home
identity warning, and confirm. The action authenticates, verifies that the
stored device ID belongs to the configured account and crib, removes exactly
that registration, confirms the API response, and only then deletes the Home
Assistant entry. It does not unpair or reset the crib.

Another community integration already uses the `cradlewise` domain. Home
Assistant cannot load two integrations with the same domain, so remove
`jlamendo/ha-cradlewise` before installing this repository. This project keeps
the canonical domain because it is not replacing a built-in integration and
the other repository is not in the default HACS catalog.

Each HACS release depends on the separately versioned `cradlewise-client`
package. Tag CI publishes the matching client version to PyPI after validation
and before it creates the full GitHub release.

See [Release Process](docs/process/releasing.md) for the guarded PyPI and HACS
release sequence.

Existing pre-release users should follow
[Migrating From `cradlewise_local`](docs/process/migrating-from-cradlewise-local.md)
to validate both integrations side by side and preserve referenced entity IDs.

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

Cribs running newer Greengrass v2 firmware present a rotating MQTT broker
certificate signed by a separate, long-lived core CA. Pin that CA once from
the same trusted LAN as the crib:

```bash
uv run cradlewise-pin-mqtt-ca \
  --ip <crib_ip> \
  --certs-dir certs/<cradle_id>
```

The command validates the broker identity, certificate signatures, validity
period, and crib IP before writing `server_ca.pem`. It refuses to replace a
different existing pin unless you pass `--replace` after verifying the crib's
firmware-driven CA change.

That creates:

```text
certs/<cradle_id>/
  ca.pem
  server_ca.pem  # Greengrass v2 firmware only
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

Official sleep analytics are independent of the account-password cloud
fallback. Nurture Plus users can request a read-only Data API token from
Cradlewise and set `CRADLEWISE_DATA_API_TOKEN`, or mount it through
`CRADLEWISE_DATA_API_TOKEN_FILE`. The bridge polls the two sleep endpoints every
15 minutes by default, which stays well below the documented rate limit. The
results remain available through the companion status API for advanced or
legacy consumers. The HACS integration does not create analytics entities yet;
capability-driven Data API analytics remain a future, explicit opt-in and do
not affect local streaming, device state, or controls.

Run the development/trusted-LAN example bridge stack:

```bash
docker compose --env-file .env -f examples/docker-compose.yaml up -d
```

The example exposes:

- RTSP: `rtsp://<reader>:<password>@<host>:8560/cradlewise`
- Authenticated bridge state: `http://<host>:8088/state`
- Authenticated bridge discovery: `http://<host>:8088/info`
- Authenticated bridge health for remote monitors: `http://<host>:8088/health`

These direct plaintext ports are for development or a trusted LAN. The verified
site-specific production configuration lives with the host's existing Traefik
stack rather than in this repository and publishes neither `8088` nor `8560`.
The bridge, MediaMTX, and Traefik join the external private Docker network named
`cradlewise-proxy`. Traefik uses its existing `https` entrypoint on port 443: an
HTTP `Host("cradlewise-api.example.com")` router terminates HTTPS to bridge port
8080, while a TCP `HostSNI("cradlewise-rtsp.example.com")` router terminates
RTSPS to MediaMTX port 8554. Plain RTSP remains inside Docker between the
bridge, MediaMTX, and Traefik.

Add the companion through the Cradlewise integration's Configure action using
the HTTPS API URL. Its authenticated `/info` response supplies the RTSPS URL.
Update an existing Scrypted Rebroadcast/Prebuffer device's source URL in place
if Scrypted also consumes the stream. Do not recreate an existing Scrypted or
HomeKit accessory just to change its source URL.

The status server binds to loopback by default. The Compose example explicitly
binds it inside the container and requires `CRADLEWISE_STATUS_TOKEN`. Loopback
container liveness checks can call `/live` without a token; remote liveness, health,
info, state, metrics, snapshot, and command requests require the bearer token.
Commands are disabled when no token is configured. MediaMTX allows only the
publisher credential to publish and only the reader credential to consume the
`cradlewise` path. The example containers run without added Linux capabilities,
with `no-new-privileges`, read-only root filesystems, bounded resources, and
rotated container logs. MediaMTX is pinned by both version and digest.

The bridge returns HTTP 200 from `/live` while its API process is available and
HTTP 503 from `/health` when MQTT, WebRTC/video freshness, or the active RTSP
sink is unhealthy. It also rejects stale snapshots and marks
stale local/cloud state unavailable. A successful command response means the
APK-shaped desired-shadow update was queued for MQTT publication; the next
reported shadow update is the confirmation of the resulting device state.

### Optional observability

Observability is local and opt-in. `CRADLEWISE_METRICS_ENABLED=true` exposes an
authenticated, label-free `/metrics` endpoint for any Prometheus-compatible
scraper. Metrics are never pushed and contain no cradle ID, IP address, baby
state, account data, or credentials. `CRADLEWISE_ERROR_REPORTING_DSN` or its
file-backed equivalent enables fatal-exception reporting to a destination the
consumer owns, including Bugsink, GlitchTip, or Sentry. Without a DSN the SDK
is not initialized and sends nothing. The project does not bundle a metrics
database, dashboard, hosted telemetry account, or maintainer-controlled DSN.

See [Private Observability](docs/process/observability.md) for configuration,
privacy guarantees, and monitor examples.

## Published Bridge Image

The release workflow publishes the optional bridge image to GitHub Container
Registry:

```text
ghcr.io/caffeineflo/cradlewise-local-bridge
```

Published tags include the release tag, its semantic version aliases, and the
short git SHA. For a server deployment, pull a published release version and
recreate the bridge container deliberately rather than auto-deploying from CI.
The example Compose file uses `CRADLEWISE_BRIDGE_VERSION=0.2.0`. Select the
version matching the integration release you installed.

## Local Development

Run tests:

```bash
uv run --extra test python -m pytest
```

Compile-check the Python files:

```bash
uv run python -m compileall cradlewise_local custom_components packages tests stream_local.py cradlewise_api.py
```

Run the bridge without Docker:

```bash
uv run cradlewise-local \
  --cradle-id 00000000-0000-4000-8000-000000000000 \
  --ip 192.0.2.10 \
  --output-url rtsp://127.0.0.1:8560/cradlewise \
  --stream-url rtsp://reader:password@127.0.0.1:8560/cradlewise
```

Build a local development image when changing bridge code:

```bash
docker build -t cradlewise-local-bridge:dev .
```

## Research Notes

The repo includes protocol notes and reverse-engineering references under `docs/`. The most useful starting points are:

- [Home Assistant Local Bridge](docs/process/home-assistant-local-bridge.md)
- [Private Observability](docs/process/observability.md)
- [Wake Event Recording](docs/process/wake-event-recording.md)
- [Authentication & Certificates](docs/process/authentication.md)
- [Local Video Streaming](docs/api/local-streaming.md)
- [MQTT Topics & Shadow](docs/api/mqtt-topics.md)
- [REST API Endpoints](docs/api/rest-endpoints.md)
- [Community Implementations](docs/reference/community-implementations.md)

These notes are kept because they explain the compatibility decisions in the bridge, especially local MQTT/WebRTC signaling and the optional cloud state shape.

## Safety Notes

This integration is not a medical device or a substitute for adult supervision,
the crib's built-in safety features, or the official Cradlewise app. Crib
firmware and physical safety controls remain authoritative.

Don't commit `certs/`, `.env`, APKs, or decompiled app output. The repository ignore rules already exclude those paths.

The example uses bearer authentication over HTTP and RTSP credentials over the
LAN; it does not terminate TLS. Bind it to the intended host address and keep
the ports on a trusted network or behind an authenticated TLS proxy.

The Cradlewise API constants in `cradlewise_api.py` are derived from the Android app configuration. They may change when Cradlewise ships app/backend updates.

This project is not affiliated with or endorsed by Cradlewise. Cradlewise and
related marks belong to their respective owners.
