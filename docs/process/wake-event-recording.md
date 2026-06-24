# Wake Event Recording

The Home Assistant integration can be paired with a small helper script to
record wake events with pre-roll. This is optional and runs entirely inside
Home Assistant; the core `cradlewise_local` integration still only provides
camera, state, and control entities.

The recorder keeps a rolling buffer of short transport-stream segments. When
Home Assistant sees a wake event, it copies the last two minutes of buffer,
records until the wake condition clears, waits another two minutes, and writes
one MP4 clip.

## Requirements

- Home Assistant can read the Cradlewise RTSP stream.
- The `cradlewise_local` integration is configured with a bridge status URL.
- `ffmpeg` is available in the Home Assistant Core environment.
- The bridge publishes baby/sleep state through `/state`. That requires cloud
  state polling in the bridge if the local MQTT state is not enough for your
  device.

## Install

Copy the helper script into Home Assistant:

```bash
scp examples/home-assistant/wake-recorder/cradlewise_wake_recorder.py \
  root@homeassistant.local:/config/cradlewise_wake_recorder.py
```

Add the shell commands from
`examples/home-assistant/wake-recorder/shell_commands.yaml` to your
`/config/shell_commands.yaml`.

Set the stream and status URLs in both shell commands:

```yaml
CRADLEWISE_WAKE_STREAM_URL="rtsp://192.0.2.20:8560/cradlewise"
CRADLEWISE_WAKE_STATUS_URL="http://192.0.2.20:8088/state"
```

Add the automations from
`examples/home-assistant/wake-recorder/automations.yaml` to your
`/config/automations.yaml`.

Check and restart Home Assistant:

```bash
ha core check
ha core restart
```

After restart, the startup automation should create files under:

```text
/media/cradlewise-wake/buffer
```

Wake clips are written to:

```text
/media/cradlewise-wake/events
```

The helper also writes a small gallery page with the latest eight clips:

```text
/config/www/cradlewise-wake/index.html
```

In Home Assistant, that page is available at:

```text
/local/cradlewise-wake/index.html
```

## Trigger Behavior

The example starts a wake recording only when the baby is present in the crib
and one of these events happens:

- `sensor.cradlewise_local_sleep_phase` changes from `sleep` to `awake`
- `sensor.cradlewise_local_sleep_phase` changes from `sleep` to `stirring`
- `sensor.cradlewise_local_sleep_state` changes from `Light sleep` to `Quite Awake`
- `sensor.cradlewise_local_sleep_state` changes from `Light sleep` to `Active Awake`
- `sensor.cradlewise_local_sleep_state` changes from `Deep sleep` to `Quite Awake`
- `sensor.cradlewise_local_sleep_state` changes from `Deep sleep` to `Active Awake`
- `binary_sensor.cradlewise_local_baby_needs_attention` turns on
- `binary_sensor.cradlewise_local_baby_needs_help` turns on

The sleep phase values come from the Cradlewise Android app mapping:
`0=away`, `1=awake`, `2=stirring`, `3=stirring`, `4=sleep`,
`5=awake`, and `6=stirring`.

There is no night-only filter in the example. If you only want overnight clips,
add a time condition to the automation. Leaving the clock out also captures nap
wakeups.

## Tuning

The default pre-roll and post-roll are both two minutes. Override them in the
shell commands:

```yaml
CRADLEWISE_WAKE_PRE_SECONDS="120"
CRADLEWISE_WAKE_POST_SECONDS="120"
```

Available environment variables:

| Variable | Default | Purpose |
|---|---:|---|
| `CRADLEWISE_WAKE_STREAM_URL` | required | RTSP stream URL |
| `CRADLEWISE_WAKE_STATUS_URL` | required | Bridge `/state` URL |
| `CRADLEWISE_WAKE_BASE_DIR` | `/media/cradlewise-wake` | Clip and buffer directory |
| `CRADLEWISE_WAKE_GALLERY_DIR` | `/config/www/cradlewise-wake` | HA-served gallery directory |
| `CRADLEWISE_WAKE_SEGMENT_SECONDS` | `5` | Rolling buffer segment length |
| `CRADLEWISE_WAKE_PRE_SECONDS` | `120` | Seconds before the wake trigger |
| `CRADLEWISE_WAKE_POST_SECONDS` | `120` | Seconds after the wake clears |
| `CRADLEWISE_WAKE_BUFFER_RETENTION_SECONDS` | `900` | Maximum buffer retention |
| `CRADLEWISE_WAKE_POLL_SECONDS` | `5` | Status polling interval during events |
| `CRADLEWISE_WAKE_MAX_EVENT_SECONDS` | `14400` | Safety cap for one event |

## Notes

The buffer process opens the RTSP stream continuously. That is acceptable for a
powered crib camera, but users should still watch CPU, disk, and network usage
after enabling it.

The helper stores temporary `.ts` segments in the buffer directory and final
`.mp4` clips in the events directory. It also writes a small JSON sidecar for
each final clip with the event timestamp, pre-roll/post-roll settings, and stop
reason.

## Dashboard Card

Add a webpage card to a Home Assistant dashboard:

```yaml
type: iframe
title: Cradlewise Wake Clips
url: /local/cradlewise-wake/index.html
aspect_ratio: 62%
```

The page refreshes itself every five minutes and is regenerated whenever the
recorder writes a new clip.
