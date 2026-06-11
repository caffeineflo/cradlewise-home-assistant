# Decompilation Process

Step-by-step guide for downloading, extracting, and decompiling the Cradlewise APK.

## Prerequisites

```bash
# Install Rust (if not already installed)
brew install rustup && rustup-init -y

# Install apkeep (EFF's APK downloader)
cargo install apkeep

# Install jadx (Java decompiler)
brew install jadx

# Optional: apktool for resource extraction
brew install apktool
```

## Step 1: Download the APK

```bash
cd /path/to/cradlewise
apkeep -a com.cradlewise.nini.app .
```

This downloads from APKPure (no credentials needed). The result is typically an `.xapk` file (split APK bundle).

## Step 2: Extract the XAPK

```bash
mkdir -p xapk_extracted
unzip -o com.cradlewise.nini.app.xapk -d xapk_extracted
```

Contents:
- `com.cradlewise.nini.app.apk` -- Base APK (the one we want)
- `config.arm64_v8a.apk` -- Native libraries (contains `libjingle_peerconnection_so.so`)
- `config.*.apk` -- Language/density splits
- `manifest.json` -- Version info and permissions

Check the version:
```bash
cat xapk_extracted/manifest.json | python3 -m json.tool | grep version
```

## Step 3: Decompile with jadx

```bash
jadx --deobf xapk_extracted/com.cradlewise.nini.app.apk -d decompiled
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
unzip -l xapk_extracted/com.cradlewise.nini.app.apk | grep -iE 'flutter|libapp|dart'

# Check native libs in the arm64 split
unzip -l xapk_extracted/config.arm64_v8a.apk | grep '\.so'
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
2. Re-run steps 1-5
3. Compare findings against existing docs in `docs/api/`
4. Update docs and commit -- `git diff` shows what changed
