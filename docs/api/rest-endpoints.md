# REST API Endpoints

**App version reviewed:** 2.60.12 (218), compared with 2.59.9 (216)
**Base URL:** AWS API Gateway (us-east-1)
**Client auth:** SigV4 using temporary AWS credentials obtained through Cognito
**HTTP client:** OkHttp via AWS Amplify (30s socket timeout, 65.5s connection timeout)

## Cradle Operations

| Method | Path | Description |
|--------|------|-------------|
| GET | `/cradles/{cradleId}/onlineStatus` | Get cradle online status (v1) |
| GET | `/cradles/{cradleId}/onlineStatus/v2` | Get cradle online status (v2) |
| GET | `/cradles/{cradleId}/babyProfile/v2` | Fetch baby profile for cradle |
| POST | `/cradles/{cradleId}/babyProfile/v2` | Update baby profile with location data |
| GET | `/cradles/{cradleId}/state` | Get cloud-backed cradle state/shadow payload |
| GET | `/cradles/{cradleId}/videoRoom` | Get Janus video room configuration |
| POST | `/cradles/{cradleId}/videoRoom?deviceId={deviceId}` | Negotiate remote P2P/Janus streaming; GET with the same query is the fallback |
| GET | `/cradles/{cradleId}/firmwareData` | Get firmware update data |
| POST | `/cradles/{cradleId}/firmware/update` | Initiate firmware update |
| POST | `/cradles/{cradleId}/calibration/status` | Update calibration status |
| POST | `/cradles/pairedUsers/v3` | Get paired users for cradle |
| GET | `/cradles/{cradleId}/pairedStatus` | Get cradle paired status |

### Remote video negotiation in 2.60.12

`WebRtcModule` adds a POST-first negotiation flow on the existing `videoRoom`
path. The body is `{}` or includes `pending_outcomes` from previous app video
sessions. The response adds `stream_strategy` (`both`, `janus_only`, or
`p2p_only`), `pp_topic_pub`, `pp_topic_sub`, `pp_grace_period_secs`,
`quality_window_secs`, `pp_decision_reason`, and `pp_keep_alive_seconds`.

These fields support the app's remote streaming race. HA's camera uses the
local companion RTSP stream, so this review doesn't add remote media or
session-outcome uploads. Account discovery, pairedUsers/v3 certificate
provisioning, online status, and normal cloud state/control paths remain
compatible.

### Online status is not shadow freshness

`onlineStatus` returns separate `is_cradle_alive` and
`is_cradle_service_alive` booleans. Both must be true for the client to treat
the crib service as online. HA checks these flags every 60 seconds in modes
with account credentials and expires cloud command eligibility after 90
seconds without a positive status check or operational MQTT event.

`onlineStatus/v2` contains a JSON-encoded `state_message` and its report time.
That message, like `/state`, can be cached. Fetching it successfully is not
proof that the crib is currently alive. V2 remains useful for local IP
discovery. MQTT `cradle_state` messages are parsed separately from the shadow:
offline, reboot, recovery, and firmware-update modes are not active operation.

## Baby Profile

| Method | Path | Description |
|--------|------|-------------|
| GET | `/babyProfiles/{babyId}` | Get baby profile details |
| POST | `/babyProfiles/{babyId}` | Create baby profile |
| GET | `/babyProfiles/{babyId}/users/{emailId}` | Get user access for baby |
| PUT | `/babyProfiles/{babyId}/users/{emailId}/v2` | Modify caregiver access |
| DELETE | `/babyProfiles/{babyId}/users/{emailId}` | Delete caregiver access |
| GET | `/babyProfiles/{babyId}/userDevices?email_id={email}` | Get an account's registered devices for a baby |
| POST | `/babyProfiles/{babyId}/userDevices/remove` | Remove exact device IDs with `{"device_ids":[...]}`; returns `{"removed_devices":[...]}` |
| POST | `/babyProfiles/{babyId}/invites/v2` | Generate invite codes |

## Sleep Tracks

| Method | Path | Description |
|--------|------|-------------|
| GET | `/babyProfiles/{babyId}/sleepTracks` | Get baby sleep tracks |
| GET | `/babyProfiles/{babyId}/sleepTracks/default` | Get default sleep track |
| POST | `/babyProfiles/{babyId}/sleepTracks` | Add sleep track |
| PUT | `/babyProfiles/{babyId}/sleepTracks/{trackId}` | Modify sleep track |
| DELETE | `/babyProfiles/{babyId}/sleepTracks/{trackId}` | Delete sleep track |

## Messaging & Notifications

| Method | Path | Description |
|--------|------|-------------|
| GET | `/babyProfiles/{babyId}/inboxMessages/v2` | Get inbox messages (paginated) |
| PUT | `/babyProfiles/{babyId}/inboxMessages/{messageId}` | Edit inbox message |
| GET | `/babyProfiles/{babyId}/timelineMessages/v2` | Get timeline messages |
| GET | `/users/{babyId}/notificationSettings/v2` | Get notification settings |
| POST | `/users/{babyId}/notificationSettings/v2` | Update notification settings |

## Configuration & Content

| Method | Path | Description |
|--------|------|-------------|
| GET | `/babyProfiles/{babyId}/featureConfig` | Get feature flags/config |
| GET | `/babyProfiles/{babyId}/quickTips` | Get quick tips by category |
| GET | `/babyProfiles/{babyId}/quickTipsSections` | Get quick tips sections |
| POST | `/babyProfiles/{babyId}/tipsAndTricks/status` | Update tips & tricks status |
| GET | `/babyProfiles/{babyId}/tipsAndTricks` | Get tips & tricks content |

## Users & Devices

| Method | Path | Description |
|--------|------|-------------|
| POST | `/users/access` | Check user access to baby profile |
| GET | `/users/{emailId}` | Get user details |
| GET | `/devices/{deviceId}` | Get device information |
| POST | `/devices/{deviceId}` | Update device (FCM token, etc.) |

## Analytics

| Method | Path | Description |
|--------|------|-------------|
| POST | `/analytics` | Send app analytics data |
| POST | `/babyProfiles/{babyId}/events` | Log pairing events |
| POST | `/babyProfiles/{babyId}/feedback` | Submit user feedback |

## Certificates & Device Registration

| Method | Path | Description |
|--------|------|-------------|
| POST | `/cradles/pairedUsers/v3` | Provision device certs (creates IoT thing + Greengrass enrollment) |
| PUT | `/devices/{deviceId}` | Register device name and metadata after cert provisioning |
| GET | `/accounts?emailId={email}` | Get baby profiles and cradle IDs for an account |

## Source Files

- `com/cradlewise/nini/core/commons/api/CommonsBackendService.java`
- `com/cradlewise/nini/features/subscriptions/api/BackendService.java`
- `com/cradlewise/nini/features/videohistory/BackendService.java`
- `com/cradlewise/nini/feature/videomoments/api/BackendService.java`
- `com/cradlewise/nini/app/aws/AwsBackendService.java`
- `com/cradlewise/nini/app/model/RemoveDevicesRequest.java`
- `com/cradlewise/nini/app/model/RemoveDevicesResponse.java`
- `com/cradlewise/nini/app/di/WebRtcModule.kt` (recovered as Java)
- `com/cradlewise/nini/core/commons/api/model/VideoRoomResponse.java`
