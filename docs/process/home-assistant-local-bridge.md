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
API for bridge health, media counters, local MQTT state, and optional
cloud-backed baby/sleep/music/light state.

## Bridge Command

Run from this checkout while developing:

```bash
uv run cradlewise-local \
  --cradle-id 00000000-0000-4000-8000-000000000000 \
  --ip cradlewise.iot \
  --output-url rtsp://192.0.2.20:8560/cradlewise
```

This publishes to a MediaMTX sidecar or another RTSP server. Direct RTSP publish
into Home Assistant's go2rtc add-on can fail with `Broken pipe`; MediaMTX has
been more reliable as a publisher target, and HA/go2rtc can then pull from it.

The bridge publishes audio by default. Use `--no-audio` to keep the original
video-only RTSP path if a client or downstream recorder has trouble with the
muxed audio stream.

Cloud state is optional. Set both environment variables in the bridge
container:

```bash
CRADLEWISE_EMAIL=user@example.com
CRADLEWISE_PASSWORD=...
CRADLEWISE_STATE_POLL_INTERVAL=30
```

Equivalent CLI flags exist for local development, but environment variables are
preferred for services so the password does not appear in process listings.

Without cloud credentials, local video/audio and bridge health still work. The
community-compatible baby/sleep/music/light entities stay `unknown` until
`GET /cradles/{cradle_id}/state` can be polled.

## MediaMTX Sidecar

The example stack in `examples/docker-compose.yaml` runs
`bluenviron/mediamtx:latest` as `cradlewise-mediamtx` and maps host port `8560`
to container RTSP port `8554`.

The bridge itself runs as `cradlewise-bridge` in the same stack. Certs are
mounted from the local `certs/` directory:

```text
certs/
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

## Home Assistant Component

Copy `custom_components/cradlewise_local` into HA's `/config/custom_components/`
directory, restart HA, then add "Cradlewise Local" from Devices & Services.

For the stream URL, use the RTSP URL that HA can read:

```text
rtsp://192.0.2.20:8560/cradlewise
```

If using Home Assistant's YAML `ffmpeg` camera platform directly, force RTSP
over TCP. The default UDP pull produced intermittent `camera_proxy` 500s during
smoke testing:

```yaml
- platform: ffmpeg
  name: Cradlewise Local
  input: -rtsp_transport tcp -i rtsp://192.0.2.20:8560/cradlewise
```

The custom component is intentionally thin. It gives HA a normal camera entity
through `stream_source()` and reads all non-camera state from the bridge
`/state` endpoint.

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

The HA integration also creates bridge/media entities and a
community-compatible state surface. As of 2026-06-11, the deployed integration
loads those entities successfully; the cloud-backed state entities are expected
to report `unknown` until cloud credentials are added to the bridge.

## Later Layers

- Add controls for selected Cradlewise actions after the state surface is
  validated.
- Add analytics entities for daily sleep/awake/nap/soothe metrics.
- Verify HA recording behavior with the muxed audio stream.
- Add snapshots and recording retention after the RTSP bridge is stable.

## Entity Map To Revisit

Use the existing community names as the compatibility baseline where the same
concept exists:

- Binary sensors: online, baby present, baby needs attention/help, crib helping,
  bouncing, music playing, light on, loud sound, sleep schedule/window, charging.
- Sensors: sleep state/phase, cradle mode, bounce mode/setting/amplitude,
  responsivity setting, music mode/mood/volume, light intensity, sleep/wake
  times, firmware, daily sleep/awake/nap/soothe metrics.

The current implementation includes the bridge/media entities plus the
baby/sleep/music/light/device-status surface. Firmware and analytics entities
still need a dedicated source and tests.
