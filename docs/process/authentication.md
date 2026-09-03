# Authentication & Certificate Provisioning

How the Cradlewise app authenticates with the backend and obtains the TLS
certificates needed for local MQTT connections. Our `fetch_certs.py` script
replicates this flow.

## Overview

```
User credentials
      |
      v
AWS Cognito SRP auth --> ID token
      |
      v
Cognito Identity Pool --> temporary AWS credentials
      |
      v
REST API (SigV4-signed) --> device certificates + config
      |
      v
S3 download (SigV4) --> client cert + client key PEM files
```

## Step 1: Cognito Authentication

The app uses AWS Cognito User Pools with SRP (Secure Remote Password) auth.

| Property | Value |
|----------|-------|
| User Pool ID | `us-east-1_hRGLsOxun` |
| Client ID | `4jnn2bbtroa3e6ra73dc8m8luh` |
| Identity Pool ID | `us-east-1:53b70db5-7440-4ecf-8dac-d6202eb6c1d2` |
| Region | `us-east-1` |

The runtime client supplies the app-client configuration required by Cognito
authentication.

**Flow:**

1. `Cognito.authenticate(email, password)` via SRP
2. Returns: `id_token`, `access_token`, `refresh_token`

## Step 2: AWS Temporary Credentials

The ID token is exchanged for temporary AWS credentials via the Cognito
Identity Pool.

1. `GetId` with `IdentityPoolId` and `Logins` (ID token keyed to the User Pool)
2. `GetCredentialsForIdentity` with the `IdentityId` and same `Logins`
3. Returns: `AccessKeyId`, `SecretKey`, `SessionToken` (temporary, ~1 hour)

These credentials allow SigV4-signed calls to the REST API and S3.

## Step 3: Get Account Info

```
GET /prod-latest/accounts?emailId={email}
```

Returns a list of baby profiles (accounts) with `baby_id` and `cradle_id`.
Most users have one baby profile, but the API supports multiple.

## Step 4: Fetch Device Certificates

```
POST /prod-latest/cradles/pairedUsers/v3
```

Request body:

```json
{
  "email_id": "user@example.com",
  "baby_id": 12345,
  "fcm_token": "...",
  "device": {
    "registration_date": "2026-02-15",
    "app_version": "2.55.5",
    "country": "US",
    "os": "android",
    "device_name": "...",
    "os_version": "34",
    "timezone": "America/New_York",
    "type": "phone",
    "resolution": "{1080,1920}"
  }
}
```

Response contains `device_config`:

| Field | Description |
|-------|-------------|
| `group_ca_cert` | Greengrass Group CA certificate (PEM string) |
| `s3_object_keys` | List of S3 keys for client cert and key files |
| `cradle_id` | Cradle UUID |
| `device_id` | Device UUID (used as MQTT client ID) |

The Android app identifies a registration as `Build.MODEL + "_" + Android ID`.
The Home Assistant client preserves that backend-compatible shape with a
randomly selected Android model identifier and random 16-character ID. It does
not expose a fixed `Home Assistant` device name in the Cradlewise device list.

## Step 5: Download Certs from S3

The S3 keys follow the pattern `{cradleId}/android/{deviceUuid}.pem`. Two
files are downloaded from the `cradlewise-device-certs` bucket:

1. **Client certificate** (saved as `client_cert.pem`)
2. **Client private key** (saved as `client_key.pem`)

The legacy Group CA cert from step 4 is saved as `ca.pem`. Newer Greengrass v2
firmware uses a separate broker core CA; pin it as `server_ca.pem` with
`cradlewise-pin-mqtt-ca` after provisioning the client credentials.

## Android App Device Telemetry

```
PUT /prod-latest/devices/{deviceId}
```

Body:
```json
{
  "device_name": "...",
  "os": "android"
}
```

The Android app makes this separate call after provisioning so it can register
its FCM push token and phone/network metadata. The Home Assistant client does
not need mobile push notifications and intentionally skips this call. MQTT
authorization comes from `pairedUsers/v3`, and both local and AWS IoT
connections have been verified without uploading the extra device telemetry.

## Device Registration Cleanup

The Android app lists registrations with:

```text
GET /prod-latest/babyProfiles/{babyId}/userDevices?email_id={email}
```

It removes selected registrations with:

```http
POST /prod-latest/babyProfiles/{babyId}/userDevices/remove
Content-Type: application/json

{"device_ids":["device-uuid"]}
```

The response is `{"removed_devices":["device-uuid"]}`. The Home Assistant
cleanup flow first verifies that its stored device ID is present in the
authenticated user's list, posts only that ID, and requires the response to
confirm the same ID. Cleanup is never performed during a normal integration
removal or certificate repair unless the user explicitly selects it.

## Certificate Details

The certificates are standard X.509:

| File | CN | Issuer | Validity |
|------|-----|--------|----------|
| `ca.pem` | `{awsAccountId}:{greengrassGroupId}` | Self-signed | ~80 years |
| `client_cert.pem` | `AWS IoT Certificate` | Amazon Root CA | ~25 years |
| `server_ca.pem` | `Greengrass Core CA` | Self-signed | Firmware-specific |
| `client_key.pem` | N/A (RSA 2048-bit private key) | N/A | N/A |

The API-provided CA is the legacy Greengrass Group CA. Legacy brokers present a
certificate signed by this CA with CN `{cradleId}_Core`. Greengrass v2 brokers
instead present a rotating certificate signed by a long-lived local core CA.

## What Happens on the Crib Side

The `pairedUsers/v3` endpoint on the backend:

1. Creates an AWS IoT "thing" with the device UUID as the thing name
2. Creates and attaches an X.509 certificate to the thing
3. Adds the thing to the Greengrass group as a connected device
4. Triggers a Greengrass group deployment (may take a few minutes)

Until the deployment completes, the crib's MQTT broker will reject connections
from the new device with "Not Authorized".

## File Layout

After `fetch_certs.py` completes:

```
certs/{cradle_id}/
  ca.pem           # Greengrass Group CA
  server_ca.pem    # Pinned Greengrass v2 core CA, when applicable
  client_cert.pem  # Device certificate
  client_key.pem   # Device private key (mode 0600)
  device_id        # Device UUID (used as MQTT client ID)
```

## Source Files (Decompiled)

- `com/cradlewise/nini/app/usecases/GetDeviceCertificatesUseCaseImpl.java` -- Orchestrates the full flow
- `com/cradlewise/nini/core/mqtt/utils/CertificateUtilsV3.java` -- Certificate storage/loading
- `com/cradlewise/nini/core/mqtt/api/model/GetDeviceCertV3Request.java` -- Request model
- `com/cradlewise/nini/core/mqtt/api/model/DeviceInfoCert.java` -- Device info sent during registration
