# Android 2.60.12 compatibility review

Reviewed on October 11, 2026 against the previous 2.59.9 (216) analysis.
The current Google Play download supplied 2.60.12 (218) for the authorized
account's Pixel 9a / Android 15 / arm64 profile. The base APK and three splits
passed signature, package, version, and signer-continuity checks.

The [official listing](https://play.google.com/store/apps/details?id=com.cradlewise.nini.app)
showed an October 1, 2026 update. This is the latest binary offered to the
selected account/profile; staged rollouts and regional differences weren't
independently ruled out. APKs, decompiled code, private manifests, and detailed
comparison output stay in ignored local research directories.

## Changes that affect this implementation

The app moved its video implementation into `core/webrtc`, with separate local,
P2P, and Janus video-room branches. Local signaling still uses `/{cradleId}/room`
and the existing offer/answer/keepalive messages. But `LocalSignalingCodec`
accepts incoming candidates as either `ice` or `iceMsg`, and candidates can
use a stream name without a session ID.

The companion now handles both candidate fields. Sessionless candidates must
name its stream, while messages with an explicit stale session or another
stream name are rejected. The shared room topic also echoes outgoing candidates;
the companion filters candidates present in its own local SDP. SDP offers keep
the active-session and `[empty]` compatibility rules. Regression tests exercise
parsed UDP candidates through
the message dispatcher into the peer connection.

## App changes that don't require HA migration

| Workflow | Evidence and HA impact |
|----------|------------------------|
| Remote video | `WebRtcModule` negotiates with POST `/cradles/{cradleId}/videoRoom?deviceId=...`, falling back to GET. New response fields select P2P, Janus, or both. HA uses the local companion stream, so remote media remains a separate feature. |
| Cloud MQTT | `RemoteMqttConnectionV2` moves to AWS CRT MQTT 5. The existing endpoint, mTLS credentials, device client ID, port, QoS, topics, and payloads persist. No evidence establishes a requirement to migrate HA's MQTT client. |
| Certificate storage | `CertificateUtilsV3` stores encrypted PEM copies for the new Android client alongside its keystore. Certificate provisioning and response fields are unchanged; HA already uses its own PEM storage. |
| Streaming recovery | `ConnectionManagerV2` delegates to a branch coordinator and configures local/remote first-frame deadlines of 15/45 seconds. The companion retains its existing recovery behavior. |
| P2P discovery | The app adds `stun:52.73.136.109:3478` for remote P2P. The local companion continues to use host candidates without public ICE servers. |

## Unchanged interfaces

After excluding generated symbol-number differences, these recovered source
interfaces match the 2.59.9 baseline:

- `GetDeviceCertificatesUseCaseImpl`, `MqttBackendService`, and `DeviceInfoCert`:
  account certificate enrollment still uses pairedUsers/v3.
- `UdpBroadcasterV2` and `CradleLocalDiscoveryMonitorV2`: discovery ports,
  broadcast payloads, retry logic, and cached-IP workflow.
- `Topics`, `StateVariable`, `MqttMessage`, `TopicMessageParser`, and
  `LocalCacheController`: state/control names, shadow parsing, and cache handling.
- `CradleOnlineStatusMonitorV2` and the online-status response model: liveness
  remains distinct from cached state and broker connectivity.
- `FeatureRegistry` and feature conditions: role, subscription, and offline gates.
- The packaged AWS Amplify configuration: byte-identical to the baseline.

Normal desired-state controls, cloud state access, HA unique IDs, and certificate
repair don't need an APK-driven migration. The client's advertised registration
version remains unchanged because no new enrollment requirement was found.

## Review limits

Jadx 1.5.6 processed 42,104 classes and reported 521 decompilation errors.
Recovered protocol code supports the findings above, but some coroutine bodies
remain incomplete. Generated-name and literal comparisons served as search aids;
an unchanged route literal alone doesn't establish an unchanged HTTP workflow.

Verification uses offline protocol and resource-lifecycle tests. This review
didn't connect to the crib, publish controls, change live HA or HomeKit, or
deploy the companion. Earlier firmware, cipher, codec, and framerate observations
remain historical measurements.
