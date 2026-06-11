# REST API Endpoints

**App version:** 2.55.5
**Base URL:** AWS API Gateway (us-east-1)
**Auth:** AWS Cognito JWT tokens in Authorization header
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
| GET | `/cradles/{cradleId}/firmwareData` | Get firmware update data |
| POST | `/cradles/{cradleId}/firmware/update` | Initiate firmware update |
| POST | `/cradles/{cradleId}/calibration/status` | Update calibration status |
| POST | `/cradles/pairedUsers/v3` | Get paired users for cradle |
| GET | `/cradles/{cradleId}/pairedStatus` | Get cradle paired status |

## Baby Profile

| Method | Path | Description |
|--------|------|-------------|
| GET | `/babyProfiles/{babyId}` | Get baby profile details |
| POST | `/babyProfiles/{babyId}` | Create baby profile |
| GET | `/babyProfiles/{babyId}/users/{emailId}` | Get user access for baby |
| PUT | `/babyProfiles/{babyId}/users/{emailId}/v2` | Modify caregiver access |
| DELETE | `/babyProfiles/{babyId}/users/{emailId}` | Delete caregiver access |
| GET | `/babyProfiles/{babyId}/userDevices` | Get user devices for baby |
| POST | `/babyProfiles/{babyId}/userDevices/remove` | Remove user devices |
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
