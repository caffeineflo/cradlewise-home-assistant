# MQTT Topics & Device Shadow

**App version:** 2.55.5

## Connection Types

The app maintains two MQTT connections:

| Type | Broker | Port | Auth |
|------|--------|------|------|
| Local | `ssl://{crib_local_ip}:8883` | 8883 | Mutual TLS (X.509 client certs) |
| Remote | `a2bby18smixe1f-ats.iot.us-east-1.amazonaws.com` | 8883 | AWS IoT device certificates |

### Connection Parameters

| Parameter | Local | Remote |
|-----------|-------|--------|
| Clean session | false | -- |
| Connection timeout | 2s | -- |
| Keep-alive interval | 5s | 5s |
| Auto-reconnect | manual | false (manual) |
| QoS | 0 | 0 |
| Max retries | 3 | -- |

## Topics

### AWS IoT Shadow (Remote)

| Topic | Direction | Description |
|-------|-----------|-------------|
| `$aws/things/{cradleId}/shadow/update` | Publish | Send desired state changes |
| `$aws/things/{cradleId}/shadow/update/accepted` | Subscribe | Confirmation of accepted updates |
| `$aws/things/{cradleId}/shadow/update/rejected` | Subscribe | Rejection notifications |
| `$aws/things/{cradleId}/shadow/get` | Publish | Request current shadow document |
| `$aws/things/{cradleId}/shadow/get/accepted` | Subscribe | Receive shadow document |
| `$aws/things/{cradleId}/shadow/get/rejected` | Subscribe | Shadow get rejection |

### Cradle State & Monitoring

| Topic | Direction | Description |
|-------|-----------|-------------|
| `/{cradleId}/beacon` | Subscribe | Heartbeat/beacon messages |
| `/cradle/{cradleId}/cradle_state` | Subscribe | Detailed cradle state updates |
| `/{cradleId}/room` | Pub/Sub | WebRTC signaling (local video) |

### Firmware Updates

| Topic | Direction | Description |
|-------|-----------|-------------|
| `/{cradleId}/update_request/new` | Subscribe | New firmware update available |
| `/{cradleId}/update_request/progress` | Subscribe | Update progress notifications |
| `/{cradleId}/update_request/succeeded` | Subscribe | Update completed successfully |
| `/{cradleId}/update_request/failed` | Subscribe | Update failed |

### Remote Video (Janus)

| Topic | Direction | Description |
|-------|-----------|-------------|
| `/janus-server/{ip}/to-janus` | Publish | Send video requests to Janus |
| `/janus-server/{ip}/from-janus` | Subscribe | Receive video responses from Janus |

Current Janus server IP: `34.226.215.23`

## Device Shadow Structure

```json
{
  "id": "<cradleId>",
  "state": {
    "state": 1,
    "expectedResumeTime": 0.0,
    "info": {
      "opMode": 0,
      "status": {
        "cradle": { /* ServiceState */ },
        "updateAgent": { /* ServiceState */ },
        "connectivityReporter": { /* ServiceState */ }
      }
    }
  },
  "info": {
    "upSince": 1700000000.0,
    "nextMaintenance": 1700100000.0,
    "connectivity": {
      "ssid": "MyWiFiNetwork",
      "strength": -45,
      "frequency": 5180,
      "localIP": "192.0.2.10"
    }
  }
}
```

## Desired Shadow Controls

The Android app writes crib settings by publishing this wrapper to
`$aws/things/{cradleId}/shadow/update`:

```json
{
  "state": {
    "desired": {
      "bounceMode": 1
    }
  }
}
```

The local bridge command API mirrors the APK payload shapes for normal
soothing/settings controls:

| Area | Desired fields |
|------|----------------|
| Bounce | `actuator.on`, `actuator.disableBouncing`, `actuator.bounceSuperGentle`, `actuator.bounceAlwaysOn`, `actuator.bounceAlwaysOnIntensity`, `actuator.tapDetectionEnable`, `actuator.pushGestureEnable`, `actuator.amplitude`, `actuator.duration`, `bounceMode`, `bounceLevel`, `bounceSetting`, `responsivitySetting` |
| Music/sound | `music.play`, `music.volume`, `musicMode`, `musicLevel`, `musicDuration`, `volumeProfile` |
| Night light | `light.indicatorBrightness`, `light.indicatorBrightnessMode` |
| Sleep settings | `keepMusicOnDuringSleep`, `keepMusicOnDuringSleepLevel`, `keepBounceOnDuringSleep`, `keepBounceOnDuringSleepLevel`, `autoModeLockOn`, `autoModeLockDuration` |
| Limits/start recipe | `maxBounceLimit`, `maxVolumeLimit`, `startRecipeEnabled`, `startRecipeMusicLevel`, `startRecipeBounceLevel`, `startRecipeLockDuration` |
| Control | `control.adaptiveSoothingEnabled`, `control.crySensitivity` |

The APK also contains methods for setup/diagnostic/privacy actions, including
calibration start, hardware self-test, breath torso/keepalive data, time zone
writes, upload-data toggles, wrong-status reporting, and max-sound preview.
Those are documented as intentional non-HA controls until the behavior and
user-facing safety implications are reviewed separately.

## APK State Mapping Audit

Mapped enum/value tables:

| APK source | Values |
|------------|--------|
| `babySleepPhaseV2.eventValue` | `0=away`, `1=awake`, `2=stirring`, `3=stirring`, `4=sleep`, `5=awake`, `6=stirring` |
| Sleep event classification | `0=away`, `1=awake`, `2=awake`, `3=stirring`, `4=sleep`, `5=sleep`; other values stay `unknown (<value>)` |
| `CalibrateCradle` | `0=idle`, `1=ongoing`, `2=stopping` |
| `CalibrationType` | `0=full`, `1=partial` |
| `CradleMode` | APK values are `Normal` for bassinet, `Crib`, and `Calib`; raw mode strings are preserved |
| `UserActionForObstruction` | APK values are `Ignored`, `Done`, and `Not_Done`; raw strings are preserved |
| Sound ambience | `0=light rain`, `1=heavy rain`, `2=waves`, `3=fan` |
| Sound color | `0=white`, `1=pink`, `2=brown` |
| Cry sensitivity control | APK UI maps `Minimum=0`, `Low=1`, `Moderate=2`, `High=4`, `Maximum=6` |

Mapped reported/shadow groups include baby presence/sleep, sleep phase
timestamps, baby needs/help, crib helping, loud sound, sleep schedule/window,
rocking/obstruction, cradle mode, bounce/actuator state, music/sound/lullabies,
light, device status, WiFi score and parsed WiFi stats, breath status,
keep-on-during-sleep settings, auto mode lock, start recipe, calibration
status/history, firmware/update status, app settings, meta versions/timezone,
and selected control flags.

Intentionally raw numeric states:

- `operationState`
- `deployState`
- top-level reported shadow `state`
- `sequenceId`
- `lullabies.action`
- breath `state` and `reason`
- control bit/score fields such as `bnaAlertControl` and `videoServiceBitMask`

Intentionally not exposed as HA entities or controls:

- Identifiers already present in the raw bridge response, such as `baby_id` and
  cradle UUID, to avoid unnecessary identifying data in HA history.
- Large or nested debug structures such as `monitor.localPeers` and complete
  `rawShadow`; the bridge keeps raw state for troubleshooting.
- The bridge exposes normalized `device_state.source` and `updated_at`
  diagnostics as HA sensors so it is visible whether HA is reading fresh local
  MQTT state or the cloud fallback.
- APK `StateVariable` constants that were not present in the live shadow during
  audit and have no clear automation value yet: `amplitudeProfile`,
  `attentionRequired`, `autoAmplitude`, `autoMood`, auto play/rocking event
  flags, `autoVolume`, `aws`, `babySafety`, bounce/movement multiplier fields,
  `interventionBegan`, `interventionEnd`, `pauseMusicOnStopGesture`,
  `recordEventMask`, `stopGesture`, `terminatedProcesses`, and timestamp/debug
  markers.
- Setup, diagnostic, privacy, and destructive desired writes: calibration
  start/terminate, hardware self-test, breath coordinate publishing, forced
  time zone writes, upload-data privacy toggles, wrong-status reporting,
  firmware commands, system reboot, and system shutdown.

### Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `id` | String | Cradle identifier |
| `state.state` | Int | 1 = Online/Active |
| `state.expectedResumeTime` | Float | Timestamp for expected resume |
| `state.info.opMode` | Int | Operating mode |
| `state.info.status` | Object | Service states (cradle, updateAgent, connectivityReporter) |
| `info.upSince` | Double | Epoch timestamp when device came online |
| `info.nextMaintenance` | Double | Scheduled maintenance timestamp |
| `info.connectivity.ssid` | String | Connected WiFi network name |
| `info.connectivity.strength` | Integer | WiFi signal strength (dBm) |
| `info.connectivity.frequency` | Integer | WiFi frequency (MHz) |
| `info.connectivity.localIP` | String | Device's local IP address |

## Connection Priority

1. App attempts **local MQTT** first when on WiFi
2. Falls back to **remote MQTT** (AWS IoT) if local fails
3. `MqttManager` coordinates switching between connections
4. Cached IPs stored via `MqttRepository.saveIp(cradleId, ip)` for faster reconnection

## Source Files

- `com/cradlewise/nini/core/mqtt/MqttManager.java`
- `com/cradlewise/nini/core/mqtt/local/LocalMqttConnectionV2.java`
- `com/cradlewise/nini/core/mqtt/remote/RemoteMqttConnectionV2.java`
- `com/cradlewise/nini/core/mqtt/utils/Topics.java`
- `com/cradlewise/nini/core/mqtt/utils/MqttConstantsV2Kt.java`
- `com/cradlewise/nini/core/mqtt/api/model/Connectivity.java`
- `com/cradlewise/nini/core/mqtt/api/model/CradleStateMessage.java`
