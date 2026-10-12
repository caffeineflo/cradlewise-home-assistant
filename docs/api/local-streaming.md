# Local Video Streaming Protocol

**App version reviewed:** 2.60.12 (218), compared with 2.59.9 (216)
**Protocol:** WebRTC with MQTT signaling
**MQTT topic:** `/{cradleId}/room`

## Overview

Android 2.60.12 moves local signaling into `LocalStreamBranch` and
`LocalSignalingCodec` in `core/webrtc`. The MQTT room topic and the
`getOffer`, `sendResponse`, and five-second `keepAlive` exchange remain
compatible with the companion.

Local video streaming uses standard WebRTC for the media transport, with MQTT messages over the local broker as the signaling channel. No internet connection is required.

## Signaling Flow

```
App                              Crib (MQTT broker + WebRTC peer)
 |                                 |
 |-- MQTT connect ssl://ip:8883 -->|
 |                                 |
 |-- subscribe /{cradleId}/room -->|
 |                                 |
 |-- publish "getOffer" ---------->|
 |                                 |
 |<-- SDP offer -------------------|
 |                                 |
 |-- SDP answer ------------------>|
 |                                 |
 |<-- ICE candidates --------------|
 |-- ICE candidates -------------->|
 |                                 |
 |<======= WebRTC P2P video ======>|
 |                                 |
 |-- "keepAlive" (periodic) ------>|
 |                                 |
```

## Message Formats

### 1. getOffer (App -> Crib)

Initiates the video session. Published to `/{cradleId}/room`.

```json
{
  "command": "getOffer",
  "direction": "play",
  "streamInfo": {
    "applicationName": "live",
    "sessionId": "<epoch_ms_string>",
    "streamName": "<deviceId>"
  },
  "userData": {
    "param1": "value1"
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `command` | String | `"getOffer"` |
| `direction` | String | `"play"` (receive video from crib) |
| `streamInfo.applicationName` | String | Always `"live"` |
| `streamInfo.sessionId` | String | Epoch milliseconds as string (unique per session) |
| `streamInfo.streamName` | String | Mobile device ID |
| `userData.param1` | String | `"value1"` (static) |

### 2. SDP Offer (Crib -> App)

Crib responds with a WebRTC SDP offer on the same topic.

```json
{
  "command": null,
  "direction": null,
  "sdp": {
    "sdp": "<SDP offer string>",
    "type": "offer"
  },
  "streamInfo": {
    "applicationName": "live",
    "sessionId": "<same_session_id>",
    "streamName": "<deviceId>"
  }
}
```

### 3. SDP Answer (App -> Crib)

App responds with SDP answer. The app uses `WebRtcController.sendCloudDescription()` for remote or publishes directly for local.

```json
{
  "sdp": {
    "sdp": "<SDP answer string>",
    "type": "answer"
  },
  "streamInfo": {
    "applicationName": "live",
    "sessionId": "<same_session_id>",
    "streamName": "<deviceId>"
  }
}
```

### 4. ICE Candidate (Bidirectional)

ICE candidates exchanged in both directions on the same topic.

```json
{
  "streamInfo": {
    "applicationName": "live",
    "sessionId": "<same_session_id>",
    "streamName": "<deviceId>"
  },
  "iceMsg": {
    "sdpMid": "<media_id>",
    "candidate": "<ICE candidate SDP string>",
    "sdpMLineIndex": 0
  }
}
```

### 5. keepAlive (App -> Crib, periodic)

Sent periodically to maintain the stream.

```json
{
  "direction": "play",
  "command": "keepAlive",
  "streamInfo": {
    "applicationName": "live",
    "sessionId": "<same_session_id>",
    "streamName": "<deviceId>"
  },
  "userData": {
    "param1": "value1"
  }
}
```

## ICE Configuration

`LocalSignalingCodec` accepts both `ice` and `iceMsg` candidate objects.
Candidates can omit `streamInfo.sessionId` and identify their destination
with `streamInfo.streamName`. SDP offers still require the active session ID
or the legacy `[empty]` marker. The companion accepts sessionless ICE only
when the stream name matches its own; explicit stale session IDs and other
stream names are rejected. Candidates echoed from the companion's own local
SDP are ignored because both signaling directions share the room topic.

| Type | URL | Credentials |
|------|-----|-------------|
| STUN | `stun:stun.l.google.com:19302` | None |
| TURN | `turn:ec2-34-226-215-23.compute-1.amazonaws.com:3478` | App-embedded credentials (redacted) |

Note: For local streaming, STUN/TURN are unnecessary. The ICE candidates resolve to local addresses directly. Our `stream_local.py` uses an empty `iceServers` list.

## DTLS-SRTP (Verified)

The crib's Janus WebRTC gateway uses RSA for its DTLS certificate. Clients
must offer RSA-compatible cipher suites in the DTLS ClientHello.

| Property | Observed Value |
|----------|----------------|
| DTLS version | 1.2 |
| Server cert CN | `{cradleId}_Core` |
| Server cert key type | RSA |
| Negotiated SRTP profile | `SRTP_AES128_CM_SHA1_80` |
| SDP setup role | Offer: `actpass`, Answer: `active` (client) |

**Important:** aiortc defaults to ECDSA certificates and hardcodes ECDSA-only
cipher suites. The crib sends a fatal DTLS `handshake_failure` alert (0x0228)
if only ECDSA ciphers are offered. You must generate an RSA certificate and
override the cipher list. See `stream_local.py` for the workaround.

## Observed Video Parameters

Verified by earlier streaming from a real crib; not remeasured during the
2.60.12 APK review:

| Property | Value |
|----------|-------|
| Resolution | 1280x720 |
| Codec | H264 (payload type 97) |
| Profile | Baseline (`42e01f`) |
| Framerate | ~10 fps (`a=framerate:10` in SDP) |
| Audio codec | Opus 48kHz/2ch (payload type 96) |
| RTP packet size | ~1188 bytes typical |

The RTSP bridge should preserve the video bitstream. The current bridge
depacketizes WebRTC H264 access units, starts publishing at an SPS/PPS/IDR sync
point, and uses ffmpeg `-c:v copy` for the RTSP video track. Audio is still
decoded from WebRTC Opus, resampled to mono 48 kHz PCM, and encoded to AAC for
RTSP consumers.

## Session Management

- **Session ID:** The companion uses an epoch timestamp in milliseconds (string); the 2.60.12 start coroutine wasn't fully recovered.
- **Session validation:** App checks that received `sessionId` matches its own. An `[empty]` sessionId from the crib is treated as valid (older firmware compatibility).
- **Restart logic:** The 2.60.12 app delegates branch recovery to `WebRtcCoordinator`; the companion retains its existing watchdog and MQTT reconnect grace period.
- **Frame timeout:** The app configures 15 seconds for local video and 45 seconds for its aggregate remote-video branch.

## Streaming States

```
Unit -> None -> Initiated -> Connecting -> Connected -> Closed
                    |                          |
                    +---- restart --------------+
```

| State | Description |
|-------|-------------|
| Unit | Initial/unset |
| None | No streaming active |
| Initiated | getOffer sent |
| Connecting | SDP exchange in progress |
| Connected | WebRTC media flowing |
| Closed | Session ended |

## Streaming Events

| Event | Description |
|-------|-------------|
| NotStreaming | No video |
| Buffering | Video buffering |
| LongBuffering | Extended buffering (triggers UI indicator) |
| Streaming | Video actively streaming |

## Volume Control

- Local app audio gain: `LocalStreamBranch.MAX_AUDIO_GAIN` is 10.0 in 2.60.12 (the legacy controller used a 0.0 to 40.0 range).
- Controlled via WebRTC audio track

This is phone playback gain, separate from the crib's `soundSynth.volume`.

## Source Files

- `com/cradlewise/nini/core/webrtc/branch/LocalStreamBranch.java`
- `com/cradlewise/nini/core/webrtc/signaling/LocalSignalingCodec.java`
- `com/cradlewise/nini/core/webrtc/coordinator/WebRtcCoordinator.java`
- `com/cradlewise/nini/app/wireless/ConnectionManagerV2.java`
- `com/cradlewise/nini/app/wireless/webrtc/WebRtcConstants.java`
