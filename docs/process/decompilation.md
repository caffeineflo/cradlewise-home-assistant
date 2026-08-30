# Decompilation Process

Use this process only with APK files lawfully obtained from your own authorized
installation of the Cradlewise app. Do not obtain app binaries from third-party
APK mirrors or commit them to this repository.

## Prerequisites

```bash
# Install Android Debug Bridge
brew install android-platform-tools

# Install jadx (Java decompiler)
brew install jadx

# Optional: apktool for resource extraction
brew install apktool
```

## Step 1: Prepare Your Authorized Installation

Install the Cradlewise app through its official distribution channel on an
Android device that you own or control and are authorized to use. Enable USB
debugging, connect the device, and confirm that ADB can see it:

```bash
adb devices
```

Continue only when the device appears as `device`, not `unauthorized`.

## Step 2: Export the Installed APK Set

```bash
cd /path/to/cradlewise
mkdir -p xapk_extracted
adb shell pm path com.cradlewise.nini.app \
  | sed 's/^package://' \
  | tr -d '\r' \
  | while IFS= read -r apk; do adb pull "$apk" xapk_extracted/; done
```

Android installs the app as a base APK plus optional architecture, language,
and density splits. Confirm that the export includes `base.apk`:

```bash
find xapk_extracted -maxdepth 1 -name '*.apk' -print
```

Check the version:
```bash
adb shell dumpsys package com.cradlewise.nini.app | grep -m 1 'versionName='
```

## Step 3: Decompile with jadx

```bash
jadx --deobf xapk_extracted/base.apk -d decompiled
```

The `--deobf` flag renames obfuscated symbols for readability. This produces ~29,000 classes. Some decompilation errors (75 in v2.55.5) are normal.

Output structure:
```
decompiled/
  sources/           # Java source files
    com/cradlewise/  # App code (what we care about)
    ...              # Third-party libraries
  resources/         # Android resources
```

## Step 4: Verify App Type

Check if it's Flutter (it's not, but verify for future versions):

```bash
# Look for Flutter artifacts
find xapk_extracted -name '*.apk' -exec unzip -l {} \; | grep -iE 'flutter|libapp|dart'

# Check native libraries across the installed APK set
find xapk_extracted -name '*.apk' -exec unzip -l {} \; | grep '\.so'
```

If `libflutter.so` and `libapp.so` are present, the app has been rewritten in Flutter and you'll need `blutter` instead of jadx.

## Step 5: Analysis Searches

Run these searches against the decompiled source to find key components:

### REST API endpoints
```bash
# Retrofit annotations
grep -rn '@GET\|@POST\|@PUT\|@DELETE\|@PATCH' decompiled/sources/com/cradlewise/

# AWS Amplify RestOptions
grep -rn 'RestOptions' decompiled/sources/com/cradlewise/
```

### MQTT topics
```bash
grep -rn 'subscribeToTopic\|publishWithTopic\|Topics\.' decompiled/sources/com/cradlewise/
grep -rn '\$aws/things' decompiled/sources/com/cradlewise/
```

### Local streaming / WebRTC
```bash
grep -rn 'getOffer\|keepAlive\|sdpOffer\|sdpAnswer\|iceCandidate' decompiled/sources/com/cradlewise/
```

### Discovery protocol
```bash
grep -rn '5055\|UdpBroadcast\|broadcast.*port\|cradlewise_mobile_port' decompiled/sources/com/cradlewise/
```

### Infrastructure (URLs, IPs, endpoints)
```bash
grep -rn 'cradlewise\.com\|amazonaws\.com\|stun:\|turn:' decompiled/sources/com/cradlewise/
grep -rn '34\.226\|a2bby18' decompiled/sources/com/cradlewise/
```

### Feature gates
```bash
grep -rn 'AppFeature\|FeatureConfig\|NeedInternet\|NeedNetwork\|AvailableOffline' decompiled/sources/com/cradlewise/
```

### Device shadow structure
```bash
grep -rn 'CradleStateMessage\|Connectivity\|localIP\|opMode\|upSince' decompiled/sources/com/cradlewise/
```

## Step 6: Key Directories

Focus analysis on these paths under `decompiled/sources/com/cradlewise/nini/`:

| Directory | Contents |
|-----------|----------|
| `core/mqtt/` | MQTT connection management |
| `core/mqtt/local/` | Local MQTT, UDP discovery |
| `core/mqtt/remote/` | AWS IoT MQTT |
| `core/mqtt/api/model/` | MQTT message models |
| `app/wireless/webrtc/` | WebRTC streaming |
| `core/featuregate/` | Feature flag system |
| `core/commons/api/` | REST API services |
| `features/subscriptions/` | Subscription management |
| `app/Constants.java` | App constants |

## Cleanup

The extracted and decompiled files are large (~500MB+). Add to `.gitignore`:

```
xapk_extracted/
decompiled/
*.xapk
*.apk
```

Only commit the documentation in `docs/`.

## Updating for a New Version

1. Delete or move old extracted/decompiled dirs
2. Re-run steps 1-5 with the updated authorized installation
3. Compare findings against existing docs in `docs/api/`
4. Update docs and commit -- `git diff` shows what changed
