#!/usr/bin/env python3
"""
Local Cradlewise video stream player.

Connects to the crib's local MQTT broker, performs WebRTC signaling,
and displays the video feed via ffplay.

Usage:
    .venv/bin/python3 stream_local.py --cradle-id <uuid>            # auto-discover
    .venv/bin/python3 stream_local.py --cradle-id <uuid> --ip 192.0.2.10  # manual IP
"""

import argparse
import asyncio
import concurrent.futures
import json
import logging
import random
import signal
import socket
import ssl
import subprocess
import time
import uuid
from pathlib import Path

import paho.mqtt.client as mqtt
from aiortc import (
    RTCConfiguration,
    RTCPeerConnection,
    RTCSessionDescription,
)
from aiortc.rtcdtlstransport import RTCCertificate
from aiortc.sdp import candidate_from_sdp
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import rsa
from paho.mqtt.enums import CallbackAPIVersion


def _make_rsa_certificate():
    """Generate an RTCCertificate backed by an RSA key.

    aiortc hardcodes ECDSA-only cipher suites in _create_ssl_context.
    The crib's Janus server uses RSA and rejects ECDSA-only ClientHellos.
    We generate an RSA cert AND monkey-patch the SSL context to include
    RSA cipher suites.
    """
    from aiortc.rtcdtlstransport import generate_certificate

    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    cert = generate_certificate(key)
    rsa_cert = RTCCertificate(key=key, cert=cert)

    # Patch _create_ssl_context to offer RSA cipher suites
    original_create = rsa_cert._create_ssl_context

    def patched_create(srtp_profiles):
        ctx = original_create(srtp_profiles)
        ctx.set_cipher_list(b"HIGH:!aNULL:!MD5")
        return ctx

    rsa_cert._create_ssl_context = patched_create
    return rsa_cert


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("stream_local")

MQTT_PORT = 8883
KEEPALIVE_INTERVAL_S = 5
DEVICE_ID = uuid.uuid4().hex[:16]

DISCOVERY_UDP_PORT = 5055
DISCOVERY_TCP_TIMEOUT_S = 2
DISCOVERY_BROADCASTS_PER_ATTEMPT = 5
DISCOVERY_MAX_ATTEMPTS = 3


def discover_crib(cradle_id=None):
    """Discover crib IP via the Cradlewise UDP broadcast protocol.

    Sends a UDP broadcast to port 5055 with a TCP callback port.
    The crib connects back to our TCP server and sends its cradle ID.
    We extract the crib's IP from the incoming TCP socket.

    Returns (ip, cradle_id) on success, raises RuntimeError on failure.
    """
    for attempt in range(1, DISCOVERY_MAX_ATTEMPTS + 1):
        log.info("Discovery attempt %d/%d...", attempt, DISCOVERY_MAX_ATTEMPTS)

        # Open a TCP server on a random port for the crib to connect back to
        tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcp_port = random.randint(10000, 60000)
        tcp_server.bind(("0.0.0.0", tcp_port))
        tcp_server.listen(1)
        tcp_server.settimeout(DISCOVERY_TCP_TIMEOUT_S)

        # Send UDP broadcast
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        broadcast_msg = json.dumps(
            {
                "cradlewise_mobile_port": str(tcp_port),
                "device_id": DEVICE_ID,
            }
        ).encode()

        for i in range(DISCOVERY_BROADCASTS_PER_ATTEMPT):
            udp_sock.sendto(broadcast_msg, ("255.255.255.255", DISCOVERY_UDP_PORT))
        log.info(
            "Sent %d broadcasts on UDP port %d (callback TCP port %d)",
            DISCOVERY_BROADCASTS_PER_ATTEMPT,
            DISCOVERY_UDP_PORT,
            tcp_port,
        )
        udp_sock.close()

        # Wait for the crib to connect back
        try:
            client_sock, addr = tcp_server.accept()
            crib_ip = addr[0]
            log.info("TCP connection from %s", crib_ip)

            with client_sock:
                data = client_sock.recv(4096)
            tcp_server.close()

            if data:
                try:
                    info = json.loads(data.decode())
                    if not isinstance(info, dict):
                        log.warning("Non-object TCP response: %s", data[:100])
                        continue
                    found_cradle_id = info.get("cradleId", "")
                    log.info(
                        "Discovered crib: ip=%s cradle_id=%s",
                        crib_ip,
                        found_cradle_id,
                    )

                    if cradle_id and found_cradle_id != cradle_id:
                        log.warning(
                            "Cradle ID mismatch: expected %s, got %s",
                            cradle_id,
                            found_cradle_id,
                        )
                        continue

                    return crib_ip, found_cradle_id or cradle_id
                except (json.JSONDecodeError, UnicodeDecodeError):
                    log.warning("Non-JSON TCP response: %s", data[:100])
            else:
                log.info("Crib connected but sent no data, using IP %s", crib_ip)
                return crib_ip, cradle_id

        except TimeoutError:
            log.info("No response on attempt %d", attempt)
            tcp_server.close()
            continue
        except OSError as exc:
            log.warning("Discovery error on attempt %d: %s", attempt, exc)
            tcp_server.close()
            continue

    raise RuntimeError(
        f"Crib discovery failed after {DISCOVERY_MAX_ATTEMPTS} attempts. "
        "Make sure you're on the same WiFi network as the crib, "
        "or pass --ip manually."
    )


def discover_crib_cloud(
    cradle_id,
    email=None,
    password=None,
    allow_interactive=True,
):
    """Discover crib IP via the Cradlewise cloud API.

    Authenticates with Cognito, then queries the onlineStatus endpoint
    which returns the crib's last-reported local IP.

    Returns the IP string, or raises RuntimeError on failure.
    """
    try:
        from cradlewise_api import (
            authenticate,
            get_aws_credentials,
            get_cradle_ip,
            get_credentials_interactive,
        )
    except ImportError as exc:
        raise RuntimeError("cradlewise_api module not found") from exc

    log.info("Cloud discovery: authenticating...")
    if bool(email) != bool(password):
        raise RuntimeError("Cloud discovery requires both email and password")
    if not email or not password:
        if not allow_interactive:
            raise RuntimeError("Cloud discovery credentials are not configured")
        email, password = get_credentials_interactive()
    _, id_token = authenticate(email, password)
    credentials, _ = get_aws_credentials(id_token)

    log.info("Cloud discovery: querying crib IP...")
    ip = get_cradle_ip(cradle_id, credentials)
    if not ip:
        raise RuntimeError("Cloud API returned no local IP for this cradle")

    log.info("Cloud discovery: found IP %s", ip)
    return ip


def discover_crib_race(
    cradle_id,
    *,
    email=None,
    password=None,
    allow_interactive=True,
):
    """Resolve the crib by UDP and, when configured, cloud lookup.

    Credentialed non-interactive lookups race in parallel. Interactive CLI
    discovery tries UDP first so a losing cloud prompt cannot remain active.
    """
    if allow_interactive and not (email and password):
        errors = []
        try:
            result = discover_crib(cradle_id)
            ip, _ = result
            return ip
        except Exception as exc:
            errors.append(f"UDP: {exc}")
            log.warning("UDP discovery failed: %s", exc)
        try:
            return discover_crib_cloud(
                cradle_id,
                email,
                password,
                allow_interactive=True,
            )
        except Exception as exc:
            errors.append(f"cloud: {exc}")
            log.warning("Cloud discovery failed: %s", exc)
        raise RuntimeError(f"Crib discovery failed: {'; '.join(errors)}")

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    futures = {executor.submit(discover_crib, cradle_id): "UDP"}
    if (email and password) or allow_interactive:
        cloud_future = executor.submit(
            discover_crib_cloud,
            cradle_id,
            email,
            password,
            allow_interactive,
        )
        futures[cloud_future] = "cloud"

    errors = []
    try:
        for future in concurrent.futures.as_completed(futures, timeout=30):
            method = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                errors.append(f"{method}: {exc}")
                log.warning("%s discovery failed: %s", method, exc)
                continue

            for other_future in futures:
                if other_future is not future:
                    other_future.cancel()
            if isinstance(result, tuple):
                ip, _ = result
                return ip
            return result
    except concurrent.futures.TimeoutError:
        pending_methods = [
            method for future, method in futures.items() if not future.done()
        ]
        errors.append(f"timed out waiting for {', '.join(pending_methods)}")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    detail = "; ".join(errors) or "no discovery method returned an address"
    raise RuntimeError(f"Crib discovery failed: {detail}")


def _stream_info(session_id):
    return {
        "applicationName": "live",
        "sessionId": session_id,
        "streamName": DEVICE_ID,
    }


def _user_data():
    return {"param1": "value1"}


class CribStreamer:
    def __init__(self, ip, cradle_id, certs_dir):
        self.ip = ip
        self.cradle_id = cradle_id
        self.certs_dir = Path(certs_dir)
        self.topic = f"/{cradle_id}/room"
        self.session_id = str(int(time.time() * 1000))

        # The MQTT client ID must be the device UUID (the IoT "thing name").
        # LocalMqttConnectionV2.java line 522 uses the deviceId from
        # SharedPreferences, which is the UUID assigned during cert provisioning.
        device_id_path = Path(certs_dir) / "device_id"
        if device_id_path.exists():
            self.device_id = device_id_path.read_text().strip()
        else:
            log.error("Missing %s -- re-run fetch_certs.py", device_id_path)
            raise SystemExit(1)
        self.mqtt_client_id = self.device_id

        self._loop = None
        self._queue = None
        self._mqtt = None
        self._pc = None
        self._ffplay = None
        self._keepalive_task = None
        self._track_tasks = set()
        self._fatal_future = None
        self._shutting_down = False
        self._frame_count = 0

    # -- MQTT layer --

    def _setup_mqtt(self):
        client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=self.mqtt_client_id,
            clean_session=False,
            protocol=mqtt.MQTTv311,
        )
        client.tls_set(
            ca_certs=str(self.certs_dir / "ca.pem"),
            certfile=str(self.certs_dir / "client_cert.pem"),
            keyfile=str(self.certs_dir / "client_key.pem"),
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )
        # Crib's cert won't match the IP as hostname
        client.tls_insecure_set(True)

        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect
        self._mqtt = client

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            log.info("MQTT connected to %s:%d (flags=%s)", self.ip, MQTT_PORT, flags)
            self._handle_mqtt_connected()
            result, _ = client.subscribe(self.topic)
            if result != mqtt.MQTT_ERR_SUCCESS:
                self._signal_fatal_threadsafe(
                    RuntimeError(f"MQTT signaling subscribe failed with rc={result}")
                )
                return
            # Only send getOffer if we don't already have a peer connection
            if self._pc is None:
                try:
                    self._publish(_get_offer_msg(self.session_id))
                except RuntimeError as exc:
                    self._signal_fatal_threadsafe(exc)
                    return
                log.info("Sent getOffer (session %s)", self.session_id)
            else:
                log.info(
                    "Reconnected -- peer connection already exists, skipping getOffer"
                )
        else:
            log.error("MQTT connect failed: %s", reason_code)
            self._signal_fatal_threadsafe(
                RuntimeError(f"MQTT connect failed: {reason_code}")
            )

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        log.warning("MQTT disconnected: reason_code=%s flags=%s", reason_code, flags)
        self._handle_mqtt_disconnected()
        if reason_code != 0 and not self._shutting_down:
            self._signal_fatal_threadsafe(
                RuntimeError(f"MQTT disconnected: {reason_code}")
            )

    def _handle_mqtt_connected(self):
        return None

    def _handle_mqtt_disconnected(self):
        return None

    def _on_message(self, client, userdata, message):
        if self._loop and self._queue:
            self._loop.call_soon_threadsafe(
                self._enqueue_message, bytes(message.payload)
            )

    def _enqueue_message(self, payload):
        try:
            self._queue.put_nowait(payload)
        except asyncio.QueueFull:
            self._signal_fatal(
                RuntimeError("MQTT signaling queue overflowed; restarting stream")
            )

    def _signal_fatal(self, error):
        if self._fatal_future is not None and not self._fatal_future.done():
            self._fatal_future.set_exception(error)

    def _signal_fatal_threadsafe(self, error):
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._signal_fatal, error)

    def _start_owned_task(self, coroutine, name):
        task = asyncio.create_task(coroutine, name=name)
        self._track_tasks.add(task)

        def task_done(completed):
            self._track_tasks.discard(completed)
            if completed.cancelled():
                return
            error = completed.exception()
            if error is not None:
                self._signal_fatal(error)

        task.add_done_callback(task_done)
        return task

    def _publish(self, payload):
        data = json.dumps(payload)
        log.debug("MQTT TX: %s", data[:200])
        result = self._mqtt.publish(self.topic, data)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            raise RuntimeError(f"MQTT signaling publish failed with rc={result.rc}")

    # -- WebRTC signaling --

    async def _handle_offer(self, msg):
        if self._pc is not None:
            log.warning(
                "Ignoring duplicate SDP offer for active session %s", self.session_id
            )
            return
        sdp_obj = msg.get("sdp", {})
        sdp_str = sdp_obj.get("sdp", "")
        stream_info = msg.get("streamInfo")
        user_data = msg.get("userData")

        log.info("Received SDP offer (%d bytes)", len(sdp_str))
        log.debug("SDP offer:\n%s", sdp_str[:500])

        # No STUN/TURN needed on LAN.
        pc = RTCPeerConnection(
            configuration=RTCConfiguration(iceServers=[]),
        )
        self._pc = pc
        # Replace the default ECDSA certificate with an RSA one.
        # The crib's Janus server uses RSA and rejects ECDSA-only
        # DTLS ClientHellos with a handshake_failure alert.
        pc._RTCPeerConnection__certificates = [_make_rsa_certificate()]

        @pc.on("track")
        async def on_track(track):
            log.info("Track received: %s", track.kind)
            self._prepare_track(track)
            self._start_owned_task(
                self._handle_track(track), f"cradlewise-{track.kind}-consumer"
            )

        @pc.on("connectionstatechange")
        async def on_conn_state():
            state = pc.connectionState
            log.info("Connection state: %s", state)
            self._handle_webrtc_connection_state(state)
            if (
                state in ("failed", "closed", "disconnected")
                and not self._shutting_down
            ):
                log.error("WebRTC connection %s", state)
                self._signal_fatal(RuntimeError(f"WebRTC connection {state}"))

        @pc.on("iceconnectionstatechange")
        async def on_ice_state():
            state = pc.iceConnectionState
            log.info("ICE connection state: %s", state)
            self._handle_ice_connection_state(state)
            if (
                state in ("failed", "closed", "disconnected")
                and not self._shutting_down
            ):
                self._signal_fatal(RuntimeError(f"ICE connection {state}"))

        # Set remote description (the offer from the crib)
        await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp_str, type="offer"))
        log.info("Remote description set")

        # Create and set our answer
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        log.info("Local description set (answer, %d bytes)", len(answer.sdp))
        log.debug("SDP answer:\n%s", answer.sdp[:500])

        si = stream_info or _stream_info(self.session_id)
        ud = user_data or _user_data()

        # Send the SDP answer WITHOUT candidates (the app uses trickle ICE)
        self._publish(
            {
                "command": "sendResponse",
                "direction": "play",
                "sdp": {"sdp": answer.sdp, "type": "answer"},
                "streamInfo": si,
                "userData": ud,
            }
        )
        log.info("Sent SDP answer")

        # Extract gathered ICE candidates from localDescription and send
        # them individually via MQTT iceMsg (trickle ICE, matching the app)
        local_sdp = pc.localDescription.sdp
        for line in local_sdp.splitlines():
            if line.startswith("a=candidate:"):
                candidate_str = line[2:]  # strip "a="
                # Skip localhost
                if "127.0.0.1" in candidate_str:
                    continue
                self._publish(
                    {
                        "streamInfo": si,
                        "iceMsg": {
                            "sdpMid": "video0",
                            "candidate": candidate_str,
                            "sdpMLineIndex": 0,
                        },
                    }
                )
                log.info("Sent ICE candidate: %s", candidate_str[:80])

        # Start keepalive timer
        self._keepalive_task = self._start_owned_task(
            self._keepalive_loop(), "cradlewise-keepalive"
        )

    async def _handle_ice(self, msg):
        ice = msg.get("ice", {})
        candidate_str = ice.get("candidate", "")
        sdp_mid = ice.get("sdpMid", "0")
        sdp_m_line_index = ice.get("sdpMLineIndex", 0)

        # The app filters for TCP only, but aiortc/aioice only supports UDP.
        # Accept UDP candidates and skip TCP ones.
        if "TCP" in candidate_str.upper():
            log.debug("Skipping TCP ICE candidate (aiortc only supports UDP)")
            return

        if not self._pc:
            log.warning("ICE candidate received but no peer connection yet")
            return

        log.info("Adding ICE candidate: %s", candidate_str[:80])

        # Strip "candidate:" prefix if present
        raw = candidate_str
        if raw.startswith("candidate:"):
            raw = raw[len("candidate:") :]

        candidate = candidate_from_sdp(raw)
        candidate.sdpMid = sdp_mid
        candidate.sdpMLineIndex = (
            int(sdp_m_line_index) if sdp_m_line_index is not None else 0
        )
        await self._pc.addIceCandidate(candidate)

    # -- Keepalive --

    async def _keepalive_loop(self):
        while True:
            await asyncio.sleep(KEEPALIVE_INTERVAL_S)
            self._publish(
                {
                    "direction": "play",
                    "command": "keepAlive",
                    "streamInfo": _stream_info(self.session_id),
                    "userData": _user_data(),
                }
            )
            log.debug("keepAlive sent")

    # -- Video output --

    async def _handle_track(self, track):
        if track.kind == "video":
            await self._consume_video(track)
        elif track.kind == "audio":
            log.info("Audio track received (not displayed)")

    def _prepare_track(self, track):
        return None

    def _handle_webrtc_connection_state(self, state):
        return None

    def _handle_ice_connection_state(self, state):
        return None

    async def _consume_video(self, track):
        log.info("Waiting for first video frame...")

        frame = await track.recv()
        img = frame.to_ndarray(format="bgr24")
        h, w = img.shape[:2]
        log.info("Video resolution: %dx%d", w, h)

        cmd = [
            "ffplay",
            "-f",
            "rawvideo",
            "-pixel_format",
            "bgr24",
            "-video_size",
            f"{w}x{h}",
            "-framerate",
            "15",
            "-window_title",
            "Cradlewise Local Stream",
            "-loglevel",
            "warning",
            "-",
        ]
        self._ffplay = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        log.info("ffplay started (pid %d)", self._ffplay.pid)

        try:
            self._ffplay.stdin.write(img.tobytes())
            self._frame_count = 1

            while True:
                frame = await track.recv()
                img = frame.to_ndarray(format="bgr24")
                self._ffplay.stdin.write(img.tobytes())
                self._frame_count += 1
                if self._frame_count % 300 == 0:
                    log.info("Frames received: %d", self._frame_count)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("Video consumer stopped: %s", exc)
            raise
        finally:
            if self._ffplay:
                self._ffplay.terminate()

    # -- Message dispatch --

    def _session_matches(self, msg):
        stream_info = msg.get("streamInfo")
        received_session_id = (
            stream_info.get("sessionId") if isinstance(stream_info, dict) else None
        )
        return received_session_id in {self.session_id, "[empty]"}

    async def _process_messages(self):
        while True:
            raw = await self._queue.get()
            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                log.warning("Invalid JSON from MQTT: %s", raw[:100])
                continue
            if not isinstance(msg, dict):
                log.warning("Ignored non-object MQTT signaling payload")
                continue

            direction = msg.get("direction")
            command = msg.get("command")
            stream_info = msg.get("streamInfo")
            received_session_id = (
                stream_info.get("sessionId") if isinstance(stream_info, dict) else None
            )
            session_matches = self._session_matches(msg)

            # SDP offer from the crib
            if direction == "publish" and command == "sendOffer":
                if not session_matches:
                    log.warning(
                        "Ignored SDP offer for session %r (active %s)",
                        received_session_id,
                        self.session_id,
                    )
                elif self._pc is None:
                    await self._handle_offer(msg)
                else:
                    log.warning("Ignored duplicate SDP offer for active session")
            # Fallback: any message with an SDP offer we haven't handled
            elif msg.get("sdp", {}).get("type") == "offer" and self._pc is None:
                if session_matches:
                    await self._handle_offer(msg)
            # ICE candidate from the crib (uses "ice" field)
            elif msg.get("ice"):
                if session_matches:
                    await self._handle_ice(msg)
                else:
                    log.debug("Ignored ICE candidate for stale session")
            else:
                log.debug(
                    "MQTT RX (ignored): command=%s direction=%s keys=%s",
                    command,
                    direction,
                    list(msg.keys()),
                )

    # -- Main --

    async def run(self):
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue(maxsize=512)
        self._fatal_future = self._loop.create_future()

        message_task = None
        mqtt_loop_started = False
        try:
            self._setup_mqtt()
            log.info(
                "Connecting to %s:%d (client_id=%s)...",
                self.ip,
                MQTT_PORT,
                self.mqtt_client_id,
            )
            self._mqtt.connect(self.ip, MQTT_PORT, keepalive=5)
            self._mqtt.loop_start()
            mqtt_loop_started = True
            message_task = asyncio.create_task(
                self._process_messages(), name="cradlewise-signaling"
            )
            done, _ = await asyncio.wait(
                {message_task, self._fatal_future},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if self._fatal_future in done:
                self._fatal_future.result()
            message_task.result()
        finally:
            log.info("Shutting down...")
            self._shutting_down = True
            if message_task is not None:
                message_task.cancel()
                await asyncio.gather(message_task, return_exceptions=True)
            if self._fatal_future is not None and not self._fatal_future.done():
                self._fatal_future.cancel()
            if self._keepalive_task:
                self._keepalive_task.cancel()
            for task in tuple(self._track_tasks):
                task.cancel()
            await asyncio.gather(*self._track_tasks, return_exceptions=True)
            if self._pc:
                await self._pc.close()
                self._pc = None
            if self._mqtt is not None:
                self._mqtt.disconnect()
                if mqtt_loop_started:
                    self._mqtt.loop_stop()
            if self._ffplay:
                self._ffplay.terminate()


def _get_offer_msg(session_id):
    return {
        "command": "getOffer",
        "direction": "play",
        "streamInfo": _stream_info(session_id),
        "userData": _user_data(),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Stream video from a Cradlewise crib over the local network"
    )
    parser.add_argument("--ip", help="Crib's local IP (auto-discovered if omitted)")
    parser.add_argument("--cradle-id", required=True, help="Cradle UUID")
    parser.add_argument(
        "--certs-dir",
        help="Certificate directory (default: certs/<cradle-id>)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    certs_dir = args.certs_dir or f"certs/{args.cradle_id}"
    certs_path = Path(certs_dir)
    for name in ("ca.pem", "client_cert.pem", "client_key.pem"):
        if not (certs_path / name).exists():
            log.error("Missing certificate: %s/%s", certs_dir, name)
            log.error("Run fetch_certs.py first to download device certificates.")
            raise SystemExit(1)

    crib_ip = args.ip
    cradle_id = args.cradle_id

    if not crib_ip:
        log.info("No --ip provided, discovering crib (UDP + cloud API)...")
        try:
            crib_ip = discover_crib_race(cradle_id)
        except RuntimeError as exc:
            log.error("%s", exc)
            raise SystemExit(1)
    else:
        log.info("Using provided IP: %s", crib_ip)

    streamer = CribStreamer(crib_ip, cradle_id, certs_dir)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def cancel_tasks():
        for task in asyncio.all_tasks(loop):
            task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, cancel_tasks)

    try:
        loop.run_until_complete(streamer.run())
    except asyncio.CancelledError:
        log.info("Stream stopped by signal")
    except KeyboardInterrupt:
        log.info("Stream interrupted")
    finally:
        loop.close()


if __name__ == "__main__":
    main()
