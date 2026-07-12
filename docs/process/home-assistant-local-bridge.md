# Home Assistant Local Bridge

This project intentionally stays separate from existing Cradlewise community
projects:

- `jlamendo/ha-cradlewise` provides a `cradlewise` Home Assistant custom
  integration for cloud/API state, analytics, sensors, and binary sensors.
- `jlamendo/pycradlewise` provides the async REST/AWS IoT client used by that
  integration.
- `imaznation/cradlewise-bridge` provides a cloud Janus video/audio library.
- `Cradlewise-Org/cradlewise-api` documents the official read-only REST API
  for Nurture Plus beta tokens.

Our first scope is different: use the local Greengrass MQTT/WebRTC path that
`stream_local.py` already proves, then expose an ordinary RTSP stream for
Home Assistant/go2rtc.

## Naming

Use `cradlewise_local` for both the Python package and Home Assistant custom
component domain so users can install it alongside `ha-cradlewise` later.

## First Runtime Shape

```
Cradlewise crib
  -> local MQTT/WebRTC over LAN
  -> cradlewise-local bridge
  -> RTSP audio/video output
  -> MediaMTX
  -> go2rtc / Home Assistant camera entity
```

The Home Assistant camera entity only needs an `rtsp://` source. HA can then
use its normal stream component for HLS, recording, and ffmpeg snapshots.

The bridge also exposes a small HTTP status API. The HA integration polls that
API for bridge health, local MQTT state, and normalized
baby/sleep/music/light state from the crib's local shadow.

## Bridge Command

Run from this checkout while developing:

```bash
uv run cradlewise-local \
  --cradle-id 00000000-0000-4000-8000-000000000000 \
  --ip cradlewise.iot \
  --output-url rtsp://publisher:password@192.0.2.20:8560/cradlewise \
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
only for development or a trusted LAN. `/health` is unauthenticated so Docker
can probe it and returns 200 only while MQTT, WebRTC/video freshness, and the
active RTSP sink are healthy; it returns 503 otherwise. When a bearer token is
configured, `/state`, `/snapshot.jpg`, and `/command` require it. Stale
snapshots are rejected, and commands are unavailable when no bearer token is
configured.

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

Reconfigure the existing Home Assistant config entry with those URLs and
update the existing Scrypted Rebroadcast/Prebuffer source URL in place. Do not
delete/re-add the HA entry or Scrypted device; retaining them preserves the
existing entity, Scrypted, and HomeKit accessory identities.

## Home Assistant Component

Copy `custom_components/cradlewise_local` into HA's `/config/custom_components/`
directory, restart HA, then add "Cradlewise Local" from Devices & Services.

For the stream URL, use the RTSP reader credential:

```text
rtsps://cradlewise-reader:<password>@cradlewise-rtsp.example.com:443/cradlewise
```

If using Home Assistant's YAML `ffmpeg` camera platform directly, force RTSP
over TCP. The default UDP pull produced intermittent `camera_proxy` 500s during
smoke testing:

```yaml
- platform: ffmpeg
  name: Cradlewise Local
  input: -rtsp_transport tcp -i rtsps://cradlewise-reader:<password>@cradlewise-rtsp.example.com:443/cradlewise
```

The custom component gives HA a normal camera entity through `stream_source()`
and reads non-camera state from the bridge `/state` endpoint. Configure the
same bearer token in the bridge and config entry. `/health` stays
unauthenticated for health checks; `/state`, `/snapshot.jpg`, and `/command`
require `Authorization: Bearer <token>` when a token is configured. Commands
are disabled when no token is configured.

The config flow validates the RTSP and HTTP URL schemes, bearer access, and the
bridge's cradle ID. Reconfigure an existing entry through Devices & Services
when changing credentials or URLs; do not edit Home Assistant storage files.
The camera sends the bearer token to the snapshot endpoint only when it has the
same origin as the configured bridge status URL.

### Entity Surface

With a bridge status URL configured, a fresh install creates 107 entities: 29
enabled and 78 disabled by default. Without the status endpoint, only the
camera is created. The default surface is intentionally limited to the
entities that are useful for dashboards and automations:

- 10 binary sensors: baby present, baby needs attention/help, crib helping,
  light on, loud sound, lower breath-rate alert, obstruction, ineffective
  rocking, and bridge health
- 7 sensors: sleep state, sleep phase, ambient temperature, breath rate,
  bounce time remaining, music time remaining, and music mood
- 5 numbers: bounce level, bounce amplitude, bounce duration, music level, and
  music volume
- 3 selects: bounce mode, music mode, and music duration
- 3 switches: actuator, music, and adaptive soothing
- 1 camera

The 78 disabled entities hold advanced configuration or detailed diagnostics,
including MQTT/WebRTC state, raw sleep classifications, WiFi details,
calibration and firmware state, recipe settings, sound synthesizer details,
and less common crib controls. Enable one deliberately from the entity
registry when it serves a real dashboard or automation. The read-only firmware
update entity reports installed/offered versions but cannot install firmware.

The version 2.1 config-entry migration removes any matching entries from a set
of 112 obsolete duplicate or wrong-domain entity keys and disables the 78
advanced entities. It keys the migration by integration unique ID, not by a
user-editable entity ID, so retained entity identities remain stable.

### Control Contract

Writable entities publish desired-shadow fragments matching the shapes and
value sets found in the decompiled Android app. Discrete values are selects:
music duration is Off, 60, or 180 minutes; responsivity is 2, 4, 6, 8, or 10;
recipe levels are Off, Gentle, or Level 1 through Level 4; and recipe lock
duration is 10, 20, or 30 minutes.

Bounce amplitude, bounce duration, and music volume also honor the current
limits reported by the crib. Music play/volume commands include the complete
current `soundSynth` object required by the APK contract instead of publishing
a destructive partial replacement. All controls become unavailable when the
device state is stale or the local MQTT publisher is disconnected.

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

- Add analytics entities for daily sleep/awake/nap/soothe metrics.
- Package certificate provisioning and bridge deployment as a guided install.
- Add retention settings only if the fixed 14-day policy needs to become
  user-configurable.
