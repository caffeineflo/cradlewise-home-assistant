# Home Assistant and Optional Media Companion

This project complements existing Cradlewise community projects:

- `jlamendo/ha-cradlewise` provides a `cradlewise` Home Assistant custom
  integration for cloud/API state, analytics, sensors, and binary sensors.
- `jlamendo/pycradlewise` provides the async REST/AWS IoT client used by that
  integration.
- `imaznation/cradlewise-bridge` provides a cloud Janus video/audio library.
- `Cradlewise-Org/cradlewise-api` documents the official read-only REST API
  for Nurture Plus beta tokens.

The Home Assistant integration is local-first and does not require a video
bridge. The optional companion uses the local Greengrass MQTT/WebRTC path that
`stream_local.py` proves and exposes an ordinary RTSP stream for Home
Assistant, go2rtc, or Scrypted.

## Naming

Use `cradlewise` for the Home Assistant custom component domain,
`cradlewise_client` for the media-free Python package, and `cradlewise_local`
for the optional bridge application. There is no built-in Home Assistant
integration with the `cradlewise` domain, and the earlier community repository
using it is not in the default HACS catalog.

## Runtime Shape

```
Home Assistant
  -> cradlewise-client
  -> local crib MQTT and/or Cradlewise AWS IoT MQTT
  -> state and controls

Optional media companion
  -> local MQTT/WebRTC over LAN
  -> RTSP audio/video output
  -> MediaMTX
  -> optional Home Assistant camera entity
```

Without the companion, Home Assistant talks directly to the local and/or cloud
MQTT providers and creates no camera entity. With the companion, its HTTP state
and command API becomes the local provider and its advertised RTSP URL creates
the camera. This prevents two consumers from competing for the companion's
local MQTT identity.

## Bridge Command

Run from this checkout while developing:

```bash
uv run cradlewise-local \
  --cradle-id 00000000-0000-4000-8000-000000000000 \
  --ip cradlewise.iot \
  --output-url rtsp://publisher:password@192.0.2.20:8560/cradlewise \
  --stream-url rtsp://reader:password@192.0.2.20:8560/cradlewise \
  --status-token replace-with-a-random-token
```

This publishes to a MediaMTX sidecar or another RTSP server. Direct RTSP publish
into Home Assistant's go2rtc add-on can fail with `Broken pipe`; MediaMTX has
been more reliable as a publisher target, and HA/go2rtc can then pull from it.

The bridge publishes audio by default. Use `--no-audio` to keep the original
video-only RTSP path if a client or downstream recorder has trouble with the
muxed audio stream.

The bridge subscribes to the same local shadow topics used by the Android app,
so normal state does not require a Cradlewise account password. Cloud polling
is an optional fallback:

```bash
CRADLEWISE_EMAIL=user@example.com
CRADLEWISE_PASSWORD=...
CRADLEWISE_STATE_POLL_INTERVAL=30
```

For file-backed secrets, leave the direct values unset or empty and configure:

```bash
CRADLEWISE_EMAIL_FILE=/run/secrets/cradlewise_email
CRADLEWISE_PASSWORD_FILE=/run/secrets/cradlewise_password
```

Do not set a non-empty direct value and its corresponding `_FILE` variable at
the same time. The bridge fails startup when both are configured, or when a
configured file is missing, unreadable, invalid UTF-8, or blank. File paths are
resolved inside the bridge process; mount them read-only into the container.
Only trailing CR/LF characters are removed from file contents.

Direct-value CLI flags exist for local development, but environment variables
are preferred for services so the password does not appear in process listings.

Do not add cloud credentials unless a field you need is unavailable locally.
The bridge keeps local and cloud documents separate, merges partial updates,
prefers fresh local shadow state, and marks stale data unavailable instead of
presenting an old value as current. It requests the current local shadow after
MQTT subscription setup and consumes the APK's get/update accepted and rejected
shadow response topics.

## MediaMTX Sidecar

The development/trusted-LAN stack in `examples/docker-compose.yaml` pins
MediaMTX 1.19.2 by digest as `cradlewise-mediamtx` and maps host port `8560` to
container RTSP port `8554`. It uses separate path-scoped publisher and reader
credentials and forces RTSP over TCP.

The bridge itself runs as `cradlewise-bridge` in the same stack. Only the
selected cradle's certificate directory is mounted read-only:

```text
certs/<cradle_id>/
```

and are never copied into the image.

The bridge requires the same cert layout as `stream_local.py`:

```
certs/<cradle_id>/
  ca.pem
  server_ca.pem  # Greengrass v2 firmware only
  client_cert.pem
  client_key.pem
  device_id
```

Both containers use read-only root filesystems, dropped Linux capabilities,
`no-new-privileges`, resource and process limits, and rotated JSON logs. The
bridge runs as an unprivileged user and receives a bounded `/tmp` tmpfs. The
MediaMTX image is pinned by version and digest, and its publisher and reader
accounts have separate permissions for the `cradlewise` path.

The base Compose example publishes plaintext ports `8088` and `8560` and is
only for development or a trusted LAN. The HTTP server binds to loopback by
default; Compose explicitly binds it inside the container and requires a
bearer token. Docker's loopback `/live` probe does not need the token, while
remote `/live`, `/health`, `/info`, `/state`, `/metrics`, `/snapshot.jpg`, and `/command`
requests require it. Stale snapshots are rejected, and commands are unavailable
when no bearer token is configured.

The API process remains available during a local crib outage. Local MQTT,
WebRTC, and RTSP are recreated with bounded backoff while cloud state polling
continues. `/state` exposes `bridge.last_error` and
`bridge.reconnect_attempts`; `/health` stays at `503` until fresh video reaches
the RTSP sink.

### Verified Production TLS Topology

The site-specific production Compose configuration lives with the host's
existing Traefik stack rather than in this repository. It uses Traefik's
`https` entrypoint on port 443 for both protocols:

- An HTTP router with `Host("cradlewise-api.example.com")` terminates HTTPS and
  forwards to `cradlewise-bridge:8080`.
- A TCP router with `HostSNI("cradlewise-rtsp.example.com")` terminates RTSPS
  and forwards to `cradlewise-mediamtx:8554`.

Traefik, `cradlewise-bridge`, and `cradlewise-mediamtx` share the external
private Docker network named exactly `cradlewise-proxy`; set
`traefik.docker.network=cradlewise-proxy` on both routed services. The
site-specific Compose file omits both `ports` blocks, so host ports `8088` and
`8560` are not published. The bridge still publishes plain RTSP to MediaMTX by
service name, and Traefik forwards plain RTSP after TLS termination, but those
connections remain inside Docker. Keep the API bearer token, MediaMTX reader
credentials, and the existing Traefik local-only HTTP middleware in place. The
runnable repository example remains the plaintext development/trusted-LAN
stack described above.

Use these client URLs:

```text
https://cradlewise-api.example.com/state
rtsps://cradlewise-reader:<password>@cradlewise-rtsp.example.com:443/cradlewise
```

Set `CRADLEWISE_STREAM_URL` in that production bridge deployment to the RTSPS
reader URL. `/info` returns it only to authenticated clients so Home Assistant
can configure its camera without asking the user for a separate media URL.

Configure this companion through the Cradlewise integration's Configure action
using its HTTPS API URL. The authenticated `/info` contract supplies the RTSPS
reader URL. Update an existing Scrypted Rebroadcast/Prebuffer source URL in
place rather than replacing that Scrypted device or HomeKit accessory.

## Home Assistant Component

Install the repository through HACS as a custom integration, restart HA, then
add "Cradlewise" from Devices & Services. Choose Automatic, Local only, or
Cloud only. Account authentication discovers the paired crib and provisions
the mTLS device identity used by both local and AWS IoT MQTT.

Local-only setup discards the email and password after provisioning. Automatic
and cloud-only modes retain them in the config entry for REST fallback and AWS
credential renewal. Diagnostics redact the account, broker address, device ID,
certificate material, companion URL, stream URL, and bearer token.

Cloud only governs state and controls, not the independent media choice. A
configured companion camera remains available, but the integration ignores
companion state and does not route commands through it in Cloud only mode. It
polls only authenticated `/health` for camera availability.

Add or remove video through the integration's Configure action. The companion
URL is optional and its `/info` response supplies the stable cradle ID and
RTSP(S) reader URL. The integration rejects a companion for another cradle.
Non-private companion destinations require HTTPS. Plain HTTP is accepted only
when every resolved address is private, loopback, or link-local and the user
explicitly accepts the trusted-LAN exposure of the bearer token and snapshots.

If using Home Assistant's YAML `ffmpeg` camera platform directly, force RTSP
over TCP. The default UDP pull produced intermittent `camera_proxy` 500s during
smoke testing:

```yaml
- platform: ffmpeg
  name: Cradlewise Camera
  input: -rtsp_transport tcp -i rtsps://cradlewise-reader:<password>@cradlewise-rtsp.example.com:443/cradlewise
```

The optional camera uses HA's normal `stream_source()` path. Remote companion
requests require `Authorization: Bearer <token>`. The camera sends the bearer
token to the snapshot endpoint only when it has the same origin as the
configured companion URL.

Use Reconfigure to change connection mode, account credentials, or the local
crib address without replacing the config entry. A changed local address is
accepted only after the broker certificate chain and IP SAN are validated and
the existing Greengrass CA is confirmed. Automatic rediscovery never replaces
a different pinned CA. Reconfigure explicitly revalidates and trusts the
broker's current core CA, including a firmware-driven CA change at the same
address. Do not edit Home Assistant storage files.

Home Assistant raises a Repair when the stored client certificate is missing,
invalid, expired, not valid yet, or expires within 30 days. Reprovisioning
keeps the config entry, device identity, unique ID, and entity IDs unchanged.
If local broker validation fails, the newly created registration is removed
and the existing configuration is kept. Removing the prior registration after
a successful repair is an explicit opt-in.

Normal config-entry removal does not call the Cradlewise cloud. The Configure
menu has a separate destructive action that verifies the stored device ID in
the authenticated account, removes exactly that registration, confirms the
response, and then removes the Home Assistant entry. Its confirmation warns
that deleting the entities can also discard Apple Home metadata tied to them.

### Entity Surface

Without media, a fresh install creates 30 entities. Adding the companion adds
only the camera, for 31 total. The default surface is limited to useful
dashboards, alerts, and common controls:

- 10 binary sensors: baby present, baby needs attention/help, crib helping,
  light on, loud sound, lower breath-rate alert, obstruction, ineffective
  rocking, and bridge health
- 7 sensors: sleep state, sleep phase, ambient temperature, breath rate,
  bounce time remaining, music time remaining, and music mood
- 5 numbers: bounce level, bounce amplitude, bounce duration, music level, and
  music volume
- 3 selects: bounce mode, music mode, and music duration
- 3 switches: actuator, music, and adaptive soothing
- 1 optional camera

State source and state update time are disabled by default. Raw shadow
documents, calibration internals, upload privacy flags, debug controls, recipe
internals, firmware actions, and duplicate cross-domain values are not created
at all.

### Control Contract

Writable entities publish desired-shadow fragments matching the shapes and
value sets found in the decompiled Android app. Discrete values are selects:
music duration is Off, 60, or 180 minutes, while bounce and music mode are Auto
or Manual.

Bounce amplitude, bounce duration, and music volume also honor the current
limits reported by the crib. Music play/volume commands include the complete
current `soundSynth` object required by the APK contract instead of publishing
a destructive partial replacement. All controls become unavailable when the
device state is stale or no selected command provider is connected.

Automatic mode selects one publisher for each command: a connected local
provider first, then AWS IoT. It never retries an ambiguous command through a
second provider after publication, because a timeout does not prove that the
crib failed to apply the first update.

A successful command response means the desired update was validated and
queued for MQTT publication. It does not claim the physical crib already
applied it; the following reported-shadow state refresh is the confirmation.

Setup, diagnostic, privacy-sensitive, and destructive APK actions remain
unexposed: calibration start/termination, hardware self-test, breath torso or
keepalive publishing, time-zone writes, upload-data privacy toggles,
wrong-status reporting, firmware commands, and system reboot/shutdown.

## Optional Wake Event Recording

The repo includes an optional native Home Assistant `camera.record` automation
for wake events. Camera preload keeps HA's bounded HLS segment lookback ready,
and the automation writes clips only to authenticated local media storage. It
requests 120 seconds before and 120 seconds after the trigger. It uses single
mode, so a trigger during an active recording does not create an overlapping
file; the active clip still covers that later event.

Use `docs/process/wake-event-recording.md` if you want Home Assistant to store a
clip when the baby is present and Cradlewise reports a wake or attention event.
The included retention automation runs at startup and daily, deleting event
MP4 files older than 14 days. There is no custom Python recorder, second
ffmpeg process, public `/config/www` gallery, or duplicate rolling buffer.

## Verified Smoke Test

On 2026-06-10, the local bridge published to MediaMTX and a separate client
read the stream successfully:

```text
codec_name=h264
width=1280
height=720
avg_frame_rate=10/1
```

On 2026-06-11, the bridge was updated and live-verified to mux the crib's
WebRTC audio track into the same RTSP output by resampling decoded audio frames
to 48 kHz mono PCM and encoding AAC in ffmpeg:

```text
codec_name=h264
width=1280
height=720
avg_frame_rate=10/1

codec_name=aac
sample_rate=48000
channels=1
```

The HA custom camera still returned a 1280x720 JPEG through
`camera_proxy` after audio was enabled.

On 2026-06-22, the bridge was changed to pass the crib's H264 video through
instead of decoding BGR frames and re-encoding with ffmpeg. The bridge still
decodes locally for snapshots, but the RTSP video track is copied from the
depacketized WebRTC H264 access units:

```text
codec_name=h264
profile=Constrained Baseline
width=1280
height=720
avg_frame_rate=10/1

codec_name=aac
sample_rate=48000
channels=1
```

For Scrypted/HomeKit, use the Rebroadcast/Prebuffer plugin with `FFmpeg (TCP)`
as the RTSP parser for this stream. Scrypted's direct RTSP parser can complete
DESCRIBE/SETUP/PLAY against MediaMTX and still time out waiting for parsed
media; the ffmpeg parser reads the same URL reliably.

The HA integration also creates a deliberately small default state surface and
selected APK-backed controls. Advanced configuration and diagnostic entities
are disabled by default. The bridge normalizes useful local shadow and live
state into `/state`; cloud data is only a fallback.

## Later Layers

- Add capability-driven official Data API analytics for users who opt in.
- Package the optional media companion as a guided Home Assistant App install.
- Add retention settings only if the fixed 14-day policy needs to become
  user-configurable.
