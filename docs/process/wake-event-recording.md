# Wake Event Recording

The Cradlewise integration can use Home Assistant's native `camera.record`
action to save short wake-event clips. No helper script, background process,
extra FFmpeg process, or public web gallery is required. One short daily shell
command deletes expired media; it does not supervise a process.

Each recording requests two minutes of HLS lookback plus two minutes after the
trigger. Home Assistant writes the resulting MP4 directly under `/media`, where
it remains behind Home Assistant authentication.

## Requirements

- The optional Cradlewise media companion is configured and its camera entity
  provides a working stream.
- Home Assistant's Stream integration is loaded.
- **Preload stream** is enabled for the Cradlewise camera entity. Lookback is
  available only while an HLS stream is already active.
- The bridge publishes the baby and sleep state entities used by the
  automation from the crib's local MQTT shadow.
- `/media/cradlewise-wake/events` exists and is writable by Home Assistant.

The example uses readable sample entity IDs. Before importing it, replace the
camera, sleep-state, sleep-phase, baby-present, attention, and help entity IDs
with those assigned by your Home Assistant instance. Entity IDs are based on
the crib name chosen in your Cradlewise account and can differ between homes.

## Install

1. Open the Cradlewise camera entity in Home Assistant and enable **Preload
   stream**.
2. Create the destination directory once from the Terminal & SSH App:

   ```bash
   mkdir -p /media/cradlewise-wake/events
   ```

3. Add `examples/home-assistant/wake-recorder/automations.yaml` through the
   automation editor or merge it into `/config/automations.yaml`.
4. Merge `examples/home-assistant/wake-recorder/shell_commands.yaml` into your
   existing `shell_command` configuration.
5. Run `ha core check`. Restart Core once to load the shell command, then
   reload automations. Later automation-only edits need only an automation
   reload.
6. After enabling preload or restarting Home Assistant, allow at least two
   minutes for the lookback buffer to fill before expecting a complete
   pre-trigger window.

Recordings appear under Local Media in Home Assistant and on disk at:

```text
/media/cradlewise-wake/events
```

Do not copy these clips to `/config/www` or serve them through `/local`.
Home Assistant does not protect `/local` files with authentication.

## Dashboard Card

The optional wake-clips card lists recordings through Home Assistant's
authenticated media-source API. Its JavaScript is a static dashboard resource,
but the MP4 files remain under `/media` and each playback URL is signed by Home
Assistant for the logged-in session.

1. Copy the card module into Home Assistant:

   ```bash
   cp examples/home-assistant/wake-recorder/cradlewise-wake-card.js \
     /config/www/cradlewise-wake-card.js
   ```

2. Add `/local/cradlewise-wake-card.js?v=1` as a JavaScript module under
   **Settings > Dashboards > Resources**.
3. Add this card to the dashboard:

   ```yaml
   type: custom:cradlewise-wake-clips-card
   title: Wake Clips
   media_content_id: media-source://media_source/local/cradlewise-wake/events
   limit: 8
   refresh_seconds: 300
   ```

The card refreshes every five minutes and shows the eight newest clips first.
Changing the card JavaScript later requires incrementing the `?v=1` resource
version so browsers do not keep an old cached copy.

## Trigger Behavior

The example starts a recording only when the baby is present and one of these
events happens:

- `sensor.your_crib_sleep_phase` changes from `sleep` to `awake`
- `sensor.your_crib_sleep_phase` changes from `sleep` to `stirring`
- `sensor.your_crib_sleep_state` changes from `Light sleep` to `Quite Awake`
- `sensor.your_crib_sleep_state` changes from `Light sleep` to `Active Awake`
- `sensor.your_crib_sleep_state` changes from `Deep sleep` to `Quite Awake`
- `sensor.your_crib_sleep_state` changes from `Deep sleep` to `Active Awake`
- `binary_sensor.your_crib_baby_needs_attention` turns on
- `binary_sensor.your_crib_baby_needs_help` turns on

The six stable state anchors for this workflow are:

- `binary_sensor.your_crib_baby_present`
- `binary_sensor.your_crib_baby_needs_attention`
- `binary_sensor.your_crib_baby_needs_help`
- `binary_sensor.your_crib_loud_sound_detected`
- `sensor.your_crib_sleep_phase`
- `sensor.your_crib_sleep_state`

`loud_sound_detected` intentionally remains informational and does not start a
recording. This preserves the existing trigger behavior and avoids creating a
clip for every detected sound.

The sleep phase values come from the Cradlewise Android app mapping:
`0=away`, `1=awake`, `2=stirring`, `3=stirring`, `4=sleep`,
`5=awake`, and `6=stirring`.

There is no night-only filter. Leaving the clock out captures both overnight
wakeups and nap wakeups.

The automation uses `mode: single`, so another trigger during an active
two-minute recording does not start an overlapping recording. The existing
clip still covers that later trigger's point in time.

## Lookback Limitations

`lookback: 120` is a request to Home Assistant, not a guaranteed frame-exact
duration. The actual pre-roll depends on the HLS stream already being active
and having enough buffered media. The actual total duration can also vary by a
few seconds at stream segment boundaries.

Verify after installation that recordings contain audio, approximately two
minutes before the trigger, and approximately two minutes after it. If preload
is disabled or the stream recently restarted, Home Assistant can still record
the post-trigger portion but may have little or no lookback.

## Retention And Privacy

The retention automation runs at Home Assistant startup and at 03:15 each day.
It deletes matching Cradlewise MP4 files older than 14 days. HA recorder
database purge settings do not remove media files, so keep this automation
enabled or replace it with another explicit storage policy.

Also review whether `/media` is included in Home Assistant or VM backups.
Keeping many clips can increase both live disk use and backup size.
