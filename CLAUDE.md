# Cradlewise Reverse Engineering Project

## What This Is

Reverse engineering and local integration tools for the Cradlewise smart crib. We decompile the Android app to understand protocols, then build Python scripts that replicate the app's local streaming functionality without depending on Cradlewise cloud services.

## Project Structure

```
.
+-- README.md                 # Project overview
+-- CLAUDE.md                 # This file -- instructions for Claude
+-- fetch_certs.py            # Downloads device certs from Cradlewise backend
+-- stream_local.py           # Local video streamer (WebRTC over MQTT)
+-- docs/
|   +-- api/
|   |   +-- rest-endpoints.md   # REST API endpoints (diffable)
|   |   +-- mqtt-topics.md      # MQTT topics and device shadow
|   |   +-- local-streaming.md  # WebRTC signaling protocol
|   |   +-- discovery.md        # UDP discovery protocol
|   |   +-- feature-gates.md    # Feature flags and conditions
|   |   +-- infrastructure.md   # AWS endpoints, servers, certs
|   +-- process/
|       +-- decompilation.md    # Step-by-step decompilation process
|       +-- authentication.md   # Cognito auth + cert provisioning flow
|       +-- local-streaming-setup.md  # How to run local video streaming
+-- certs/                      # Downloaded device certs (gitignored)
+-- xapk_extracted/             # Extracted XAPK contents (gitignored)
+-- decompiled/                 # jadx output (gitignored)
```

## Working Tools

### fetch_certs.py

Downloads device certificates needed for local MQTT connections. Authenticates
with Cradlewise's Cognito backend, discovers your cradle, and saves TLS certs
from S3. Also registers the device via `PUT /devices/{deviceId}`.

Requires: `boto3`, `requests`, `pycognito`

### stream_local.py

Connects to the crib over the local network and displays a live video feed.
Uses MQTT for WebRTC signaling and aiortc for the media transport. Displays
video via ffplay.

Requires: `paho-mqtt`, `aiortc`, `numpy`, `ffmpeg` (for ffplay)

## Updating for a New App Version

When a new Cradlewise app version is released:

1. Follow `docs/process/decompilation.md` to export and decompile the app from
   your own authorized installation
2. Run the analysis searches documented there
3. Update each file in `docs/api/` with any changes
4. Update the version number in `README.md`
5. Commit so `git diff` shows exactly what changed

## Key Facts

- **Package:** `com.cradlewise.nini.app`
- **App type:** Native Android (Kotlin + Jetpack Compose) -- NOT Flutter
- **Decompiler:** jadx (with --deobf flag)
- **APK source:** APK files exported from the researcher's own authorized installation
- **Crib software:** AWS Greengrass with Janus WebRTC gateway
- **Local MQTT:** `ssl://<crib_ip>:8883`, mutual TLS, no username/password
- **Video:** 1280x720 H264 Baseline @ ~10fps over DTLS-SRTP
- **Audio:** OPUS 48kHz mono (mic, max capture rate 8kHz) -- received but not yet consumed

## Analysis Approach

When analyzing a new version, search for these patterns in the decompiled source under `com/cradlewise/nini/`:

1. **REST endpoints:** Grep for `@GET`, `@POST`, `@PUT`, `@DELETE` annotations and `RestOptions`
2. **MQTT topics:** Grep for `subscribeToTopic`, `publishWithTopic`, `Topics.`, `$aws/things`
3. **Local streaming:** Look in `app/wireless/webrtc/` for WebRTC signaling
4. **Discovery:** Look in `core/mqtt/local/` for UDP broadcast code
5. **Feature gates:** Look in `core/featuregate/` for feature conditions
6. **URLs/domains:** Grep for `cradlewise.com`, `amazonaws.com`, hardcoded IPs
7. **Infrastructure:** Grep for STUN/TURN servers, AWS endpoints, Janus server IPs

## Important Directories in Decompiled Source

- `com/cradlewise/nini/core/mqtt/` -- MQTT connection management (local + remote)
- `com/cradlewise/nini/core/mqtt/local/` -- Local MQTT, UDP discovery
- `com/cradlewise/nini/core/mqtt/remote/` -- AWS IoT MQTT
- `com/cradlewise/nini/core/mqtt/api/model/` -- MQTT message models (shadow, state)
- `com/cradlewise/nini/app/wireless/webrtc/` -- WebRTC streaming (local + remote)
- `com/cradlewise/nini/core/featuregate/` -- Feature flag system
- `com/cradlewise/nini/core/commons/api/` -- REST API services
- `com/cradlewise/nini/features/subscriptions/` -- Subscription management
- `com/cradlewise/nini/app/usecases/GetDeviceCertificatesUseCaseImpl.java` -- Cert provisioning flow

## Pitfalls and Gotchas

### DTLS cipher suites (critical)

aiortc hardcodes ECDSA-only cipher suites in `RTCCertificate._create_ssl_context()`.
The crib's Janus server uses RSA and sends a fatal `handshake_failure` alert if no
RSA ciphers are offered. The fix in `stream_local.py`:

1. Generate an RSA 2048-bit certificate (not the default ECDSA)
2. Override `set_cipher_list` to `HIGH:!aNULL:!MD5` (includes RSA suites)

Without this, DTLS silently fails with an empty SSL.Error.

### MQTT client ID

The MQTT client ID for local connections must be the **device UUID** (the IoT
"thing name" assigned during cert provisioning), not the cradle ID. The
decompiled `LocalMqttConnectionV2.java` confirms this. Greengrass enforces
strict client ID matching.

### Greengrass deployment lag

After running `fetch_certs.py` for the first time, the Greengrass deployment on
the crib may take some time to propagate. If you get "Not Authorized" on MQTT,
wait a few minutes and try again.

### Cross-VLAN discovery

UDP discovery (port 5055) uses broadcast and won't work across VLANs. If the
crib is on a different subnet, use `--ip` to specify the crib's IP directly.

## What Works / What Doesn't

| Capability | Status | Notes |
|---|---|---|
| Cert provisioning | Working | `fetch_certs.py` -- run once per device |
| UDP discovery | Working | Same-subnet only; use `--ip` cross-VLAN |
| Local MQTT connection | Working | Mutual TLS, device UUID as client ID |
| WebRTC signaling | Working | getOffer/sendResponse/ICE via MQTT |
| DTLS-SRTP | Working | Requires RSA cert + broad cipher list (aiortc workaround) |
| Video bridge | Working | H264 720p passthrough to RTSP |
| Audio bridge | Working | OPUS input muxed into RTSP as AAC mono |
| Device shadow / state | Working | Bridge normalizes APK-backed shadow/live state into `/state` |
| Two-way audio | Unknown | App has volume control; needs investigation |
| Crib controls (bounce, etc.) | Working, bounded | Normal soothing/settings controls publish APK-shaped desired shadow fragments |
| APK/debug actions | Intentionally not exposed | Calibration start, hardware self-test, breath coordinate publishing, time zone writes, privacy upload toggles, and wrong-status reporting need separate review before HA exposure |

## Home Assistant Integration

This repo now includes a Home Assistant custom component. Key considerations:

- HA uses the bridge RTSP stream for the camera and the bridge HTTP API for
  state/commands.
- The MQTT connection could integrate with HA's MQTT support, but the mutual TLS with device-specific certs is non-standard
- Cert provisioning (fetch_certs.py) would need to become a config flow
- Packaged add-on/config-flow certificate provisioning remains future work.
- Sleep analytics entities remain future work.

## Tools Required

- `adb` (install via `brew install android-platform-tools`)
- `jadx` (install via `brew install jadx`)
- `apktool` (install via `brew install apktool` -- optional, for resources)
- Python 3.10+ with venv (for fetch_certs.py and stream_local.py)
- `ffmpeg` (install via `brew install ffmpeg` -- provides ffplay for video display)
