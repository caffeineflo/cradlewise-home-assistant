# Infrastructure & External Services

**App version:** 2.55.5

## AWS Services

### IoT Core (MQTT)

| Property | Value |
|----------|-------|
| Endpoint | `a2bby18smixe1f-ats.iot.us-east-1.amazonaws.com` |
| Region | us-east-1 |
| Protocol | MQTT over TLS |
| Port | 8883 |
| Auth | X.509 device certificates |

### API Gateway (REST)

| Property | Value |
|----------|-------|
| Region | us-east-1 |
| Auth | Cognito JWT |
| Client | AWS Amplify + OkHttp |
| Socket timeout | 30,000ms |
| Connection timeout | 65,536ms |

### Cognito (Auth)

| Property | Value |
|----------|-------|
| Service | AWS Cognito |
| User Pool ID | `us-east-1_hRGLsOxun` |
| Client ID | `4jnn2bbtroa3e6ra73dc8m8luh` |
| Client Secret | Embedded client configuration; literal value omitted |
| Identity Pool ID | `us-east-1:53b70db5-7440-4ecf-8dac-d6202eb6c1d2` |
| Auth flow | Email/password via SRP -> JWT tokens |
| Storage | AWSCognitoLegacyCredentialStore |

### S3 (Storage)

| Property | Value |
|----------|-------|
| Usage | Video content, audio files, baby profile images, device certificates |
| Cert bucket | `cradlewise-device-certs` |
| Cert key pattern | `{cradleId}/android/{deviceUuid}.pem` |
| Upload | TransferUtility (multipart) |

### SNS (Push Notifications)

| Property | Value |
|----------|-------|
| Platform | Firebase Cloud Messaging (FCM) |
| Operations | CreatePlatformEndpoint, Subscribe, Unsubscribe |

### Polly (Text-to-Speech)

| Property | Value |
|----------|-------|
| Usage | Speech synthesis tasks |
| Operations | StartSpeechSynthesisTask |

## WebRTC Infrastructure

### ICE Servers

| Type | URL | Username | Password |
|------|-----|----------|----------|
| STUN | `stun:stun.l.google.com:19302` | -- | -- |
| TURN | `turn:ec2-34-226-215-23.compute-1.amazonaws.com:3478` | App-embedded credential (redacted) | App-embedded credential (redacted) |

### Janus WebRTC Gateway (Remote Streaming)

| Property | Value |
|----------|-------|
| Server IP | `34.226.215.23` |
| MQTT topic (send) | `/janus-server/34.226.215.23/to-janus` |
| MQTT topic (recv) | `/janus-server/34.226.215.23/from-janus` |

### Remote WebRTC State Machine

```
JanusClientConfigReceived
  -> CreateSessionPublished
    -> SessionCreated
      -> AttachPluginPublished
        -> AttachPluginSuccess
          -> WatchRequestPublished
            -> JanusIceCandidateReceived
              -> JanusIceCandidateCompleted
                -> SdpOfferReceived
```

## Local Crib Services

| Service | Protocol | Port |
|---------|----------|------|
| MQTT broker | TLS (ssl://) | 8883 |
| UDP discovery | UDP broadcast | 5055 |
| TCP discovery callback | TCP | 10000-60000 (random) |

### Local MQTT Certificate Chain (Verified)

| Certificate | CN | Signed By | Purpose |
|-------------|-----|-----------|---------|
| Legacy group CA (`ca.pem`) | `{awsAccountId}:{greengrassGroupId}` | Self-signed | Validates legacy broker cert |
| Greengrass v2 core CA (`server_ca.pem`) | `Greengrass Core CA` | Self-signed | Validates rotating v2 broker cert |
| Client cert (`client_cert.pem`) | `AWS IoT Certificate` | Amazon Root CA | Client authentication |
| Legacy broker cert (crib) | `{cradleId}_Core` | Group CA | Server identity |
| Greengrass v2 broker cert | `aws.greengrass.clientdevices.mqtt.Moquette` | Greengrass Core CA | Server identity with crib IP SAN |

- Client key is RSA 2048-bit
- Certificates provisioned via `/cradles/pairedUsers/v3` API (see `docs/process/authentication.md`)
- Stored on Android in a keystore at `{filesDir}/certificates/{cradleId}_keystore_name`
- On disk (our scripts): PEM files in `certs/{cradleId}/`
- MQTT client ID must match the device UUID ("thing name") -- Greengrass enforces this
- TLS v1.2 and no ALPN. Legacy certificates require hostname verification to
  be disabled because their CN is not a hostname. Greengrass v2 uses the
  separately pinned `server_ca.pem` and verifies the configured crib IP
  against the broker certificate SAN.

## Third-Party Services

### Firebase

| Service | Usage |
|---------|-------|
| FCM | Push notifications |
| Performance | Network request monitoring (`FirebasePerfUrlConnection`) |
| Analytics | App analytics |

### Sentry

| Service | Usage |
|---------|-------|
| Error tracking | Crash reporting and performance monitoring |

### Amplitude

| Property | Value |
|----------|-------|
| API Key | `82d3524e945f9465e0206ff0cac6c06e` |
| Usage | Product analytics |

### Intercom

| Usage | In-app messaging and support |

## Hardcoded URLs

### Cradlewise Content

| URL | Purpose |
|-----|---------|
| `https://help-center.cradlewise.com/en/` | FAQ/Help Center |
| `https://cradlewise.com/legal/privacy-policy-m` | Privacy Policy |
| `https://cradlewise.com/legal/terms-of-service-m` | Terms of Service |
| `https://assets.cradlewise.com/ebooks/user-manual-V11.pdf` | User manual |
| `https://cradlewise.com/product/gift-card` | Gift card |
| `https://cradlewise.com/products?ref=app&utm_source=app...` | Shop |
| `https://private.cradlewise.com/baby-profile-images/{imageId}` | Profile images |
| `https://mobile-app-assets.cradlewise.com/onboardingEducationAnimations/Card1.mp4` | Onboarding videos |

### YouTube

| URL | Purpose |
|-----|---------|
| `https://www.youtube.com/watch?v=weInpoCMVLg` | Product content |
| YouTube API Key: present in the APK; value intentionally redacted | |

## Android Permissions

```
BLUETOOTH_CONNECT, BLUETOOTH_SCAN, BLUETOOTH, BLUETOOTH_ADMIN
ACCESS_COARSE_LOCATION, ACCESS_FINE_LOCATION
INTERNET, ACCESS_NETWORK_STATE, ACCESS_WIFI_STATE
READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE
MODIFY_AUDIO_SETTINGS, READ_PHONE_STATE, VIBRATE
POST_NOTIFICATIONS
FOREGROUND_SERVICE, FOREGROUND_SERVICE_MEDIA_PLAYBACK
WAKE_LOCK, CAMERA, RECORD_AUDIO
RECEIVE_BOOT_COMPLETED, REORDER_TASKS
```

## Source Files

- `com/cradlewise/nini/app/wireless/webrtc/WebRtcConstants.java`
- `com/cradlewise/nini/core/mqtt/remote/RemoteMqttConnectionV2.java`
- `com/cradlewise/nini/core/mqtt/local/LocalMqttConnectionV2.java`
- `com/cradlewise/nini/core/mqtt/utils/CertificateUtilsV3.java`
