import json
import socket
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

import stream_local

pytestmark = pytest.mark.enable_socket


def test_silent_discovery_callback_times_out_and_releases_worker(monkeypatch):
    original_socket = socket.socket
    callback_ports = []
    broadcast = threading.Event()

    class DiscoverySocket(original_socket):
        def sendto(self, data, address):
            callback_ports.append(int(json.loads(data)["cradlewise_mobile_port"]))
            broadcast.set()
            return len(data)

    monkeypatch.setattr(stream_local.socket, "socket", DiscoverySocket)
    monkeypatch.setattr(stream_local, "DISCOVERY_TCP_TIMEOUT_S", 0.1)
    monkeypatch.setattr(stream_local, "DISCOVERY_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(stream_local, "_discovery_bind_address", lambda: "127.0.0.1")
    with ThreadPoolExecutor(max_workers=1) as executor:
        task = executor.submit(stream_local.discover_crib, "synthetic-crib")
        assert broadcast.wait(2)
        with original_socket() as silent_peer:
            silent_peer.connect(("127.0.0.1", callback_ports[0]))
            with pytest.raises(RuntimeError, match="discovery failed"):
                task.result(timeout=2)
    with original_socket() as probe:
        assert probe.connect_ex(("127.0.0.1", callback_ports[0])) != 0
