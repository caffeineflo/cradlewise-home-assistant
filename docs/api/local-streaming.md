# Local Video Streaming Protocol

**App version:** 2.55.5
**Protocol:** WebRTC with MQTT signaling
**MQTT topic:** `/{cradleId}/room`

## Overview

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

| Type | URL | Credentials |
|------|-----|-------------|
| STUN | `stun:stun.l.google.com:19302` | None |
| TURN | `turn:ec2-34-226-215-23.compute-1.amazonaws.com:3478` | user: `user`, password: `root` |

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

Verified by successfully streaming from a real crib:

| Property | Value |
|----------|-------|
| Resolution | 1280x720 |
| Codec | H264 (payload type 97) |
| Profile | Baseline (`42e01f`) |
| Framerate | ~10 fps (`a=framerate:10` in SDP) |
| Audio codec | Opus 48kHz/2ch (payload type 96) |
| RTP packet size | ~1188 bytes typical |

## Session Management

- **Session ID:** Epoch timestamp in milliseconds (string), generated fresh per `startVideo()` call
- **Session validation:** App checks that received `sessionId` matches its own. An `[empty]` sessionId from the crib is treated as valid (older firmware compatibility).
- **Restart logic:** If the PeerConnection enters FAILED, CLOSED, or DISCONNECTED state, the app calls `restartVideo()` which resets and re-initiates the flow.
- **Frame timeout:** If no video frames are received within 15 seconds of stream start, the app triggers a restart.

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

- Range: 0.0 to 40.0
- Controlled via WebRTC audio track

## Source Files

- `com/cradlewise/nini/app/wireless/webrtc/LocalWebRtc.java`
- `com/cradlewise/nini/app/wireless/webrtc/LocalWebRtcMessage.java`
- `com/cradlewise/nini/app/wireless/webrtc/WebRtcController.java`
- `com/cradlewise/nini/app/wireless/webrtc/WebRtcConstants.java`
- `com/cradlewise/nini/app/wireless/webrtc/RemoteWebrtc.java`
