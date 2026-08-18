# Local Streaming Setup

How to set up and run the local video stream from a Cradlewise crib.

## Prerequisites

- Python 3.10+
- ffmpeg (for ffplay video display)
- Network access to the crib (same LAN or routed)
- Your Cradlewise account credentials

```bash
# Install ffmpeg (macOS)
brew install ffmpeg

# Create Python venv and install dependencies
cd /path/to/cradlewise
python3 -m venv .venv
.venv/bin/pip install boto3 requests pycognito paho-mqtt aiortc numpy
```

## Step 1: Fetch Device Certificates (One-Time)

```bash
.venv/bin/python3 fetch_certs.py
```

Enter your Cradlewise email and password when prompted (or set
`CRADLEWISE_EMAIL` and `CRADLEWISE_PASSWORD` environment variables).

The script will:

1. Authenticate with Cognito
2. Look up your baby profile and cradle ID
3. Download device certificates from S3
4. Save them to `certs/{cradle_id}/`

Output looks like:

```
Authenticating as you@example.com...
Cognito auth successful.
AWS credentials obtained.
Selected: BabyName (baby_id=12345, cradle_id=405c26b8-...)
Device config received for cradle: 405c26b8-...
  Saved CA cert: certs/405c26b8-.../ca.pem
  Saved: certs/405c26b8-.../client_cert.pem
  Saved: certs/405c26b8-.../client_key.pem
  Saved device ID: certs/405c26b8-.../device_id
```

**Note:** After the first run, the Greengrass deployment on the crib may take
a few minutes to propagate. If MQTT gives "Not Authorized", wait and retry.

You only need to do this once. The certificates are valid for decades.

### Greengrass v2 broker CA

Newer crib firmware uses a Greengrass v2 core CA instead of the older group CA
returned during device provisioning. Its MQTT leaf certificate rotates, so do
not pin the leaf and do not disable certificate verification. Pin the
long-lived core CA while connected to the trusted crib LAN:

```bash
uv run cradlewise-pin-mqtt-ca \
  --ip <crib_ip> \
  --certs-dir certs/<cradle_id>
```

This creates `server_ca.pem`. The streamer prefers it over `ca.pem` and enables
normal hostname/IP verification. A different existing pin is never replaced
unless you explicitly pass `--replace` after confirming a firmware-driven CA
change.

## Step 2: Find Your Crib's IP

If the crib is on the same subnet, `stream_local.py` can discover it
automatically via UDP broadcast. If it's on a different VLAN, you need
the IP.

Ways to find it:

- **Router/DHCP admin:** Look for a device named `cradlewise.iot` or similar
- **UniFi:** Check the client list for the crib's MAC address
- **ARP table:** `arp -a | grep -i cradlewise`
- **MQTT shadow:** The `info.connectivity.localIP` field in the device shadow

## Step 3: Stream Video

```bash
# Auto-discover (same subnet only)
.venv/bin/python3 stream_local.py --cradle-id <cradle_id>

# Manual IP (works cross-VLAN)
.venv/bin/python3 stream_local.py --cradle-id <cradle_id> --ip <crib_ip>

# Verbose output (for debugging)
.venv/bin/python3 stream_local.py --cradle-id <cradle_id> --ip <crib_ip> -v
```

An ffplay window will open showing the live video feed.

**Example:**
```bash
.venv/bin/python3 stream_local.py \
  --cradle-id 00000000-0000-4000-8000-000000000000 \
  --ip 192.0.2.10
```

## What Happens

```
1. UDP discovery (or use --ip)
2. MQTT connect to ssl://<ip>:8883 (mutual TLS)
3. Subscribe to /<cradleId>/room
4. Publish "getOffer" to start WebRTC session
5. Receive SDP offer from crib (H264 video + Opus audio)
6. Create and send SDP answer
7. Exchange ICE candidates
8. DTLS-SRTP handshake
9. Receive video frames -> decode H264 -> display in ffplay
```

Typical output:

```
16:41:55 INFO    Connecting to 192.0.2.10:8883 (client_id=911ea165-...)...
16:41:55 INFO    MQTT connected
16:41:55 INFO    Sent getOffer (session 1771191715790)
16:41:55 INFO    Received SDP offer (1284 bytes)
16:41:55 INFO    Sent SDP answer
16:41:56 INFO    Connection state: connected
16:41:56 INFO    Video resolution: 1280x720
16:41:56 INFO    ffplay started (pid 66647)
16:42:26 INFO    Frames received: 300
```

## Video Specs

| Property | Value |
|----------|-------|
| Resolution | 1280x720 |
| Codec | H264 Baseline (profile 42e01f) |
| Framerate | ~10 fps |
| Transport | DTLS-SRTP (SRTP_AES128_CM_SHA1_80) |
| Audio | Opus 48kHz from WebRTC; the bridge converts it to AAC for RTSP |

## Troubleshooting

### "Not Authorized" on MQTT connect

- **First run?** Wait a few minutes for the Greengrass deployment to propagate
  after `fetch_certs.py`, then try again.
- **`self-signed certificate in certificate chain`?** Run
  `cradlewise-pin-mqtt-ca` for Greengrass v2 firmware. Re-running
  `fetch_certs.py` alone can still return the legacy group CA.
- **Client cert expired?** Re-run `fetch_certs.py` to get fresh credentials.
- **Wrong cradle ID?** Check `certs/` directory for the correct UUID.

### UDP discovery fails

- The crib must be on the same broadcast domain (subnet). If it's on a
  different VLAN, use `--ip` instead.
- Make sure your firewall allows UDP broadcast on port 5055.

### DTLS handshake failed

- This was a major issue during development. The fix (RSA cert + broad cipher
  list) is already built into `stream_local.py`. If you see this on a new
  aiortc version, the cipher list override in `_make_rsa_certificate()` may
  need updating.

### H264 decode errors at start

- Normal. The first few frames after connecting fail to decode because we
  join mid-GOP (need to wait for a keyframe). Video starts after a few
  seconds.

### ffplay not found

- Install ffmpeg: `brew install ffmpeg`

### No video frames received

- Check that the crib is powered on and the camera is active.
- Try with `-v` flag to see detailed WebRTC and ICE negotiation.
- Verify your Mac can reach the crib: `ping <crib_ip>`
