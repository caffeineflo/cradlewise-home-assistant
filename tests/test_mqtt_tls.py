from pathlib import Path

from stream_local import CribStreamer, mqtt_server_ca_path


class FakeMqttClient:
    def __init__(self, **_kwargs):
        self.tls_options = None
        self.insecure_calls = 0

    def tls_set(self, **kwargs):
        self.tls_options = kwargs

    def tls_insecure_set(self, _enabled):
        self.insecure_calls += 1


def build_streamer(tmp_path: Path, monkeypatch) -> tuple[CribStreamer, FakeMqttClient]:
    (tmp_path / "device_id").write_text("device-1")
    client = FakeMqttClient()
    monkeypatch.setattr("stream_local.mqtt.Client", lambda **_kwargs: client)
    streamer = CribStreamer("192.0.2.10", "cradle-1", tmp_path)
    streamer._setup_mqtt()
    return streamer, client


def test_mqtt_prefers_pinned_greengrass_v2_ca(tmp_path: Path):
    (tmp_path / "ca.pem").write_text("legacy")
    pinned = tmp_path / "server_ca.pem"
    pinned.write_text("current")

    assert mqtt_server_ca_path(tmp_path) == pinned


def test_mqtt_uses_provisioned_ca_without_pinned_ca(tmp_path: Path):
    provisioned = tmp_path / "ca.pem"
    provisioned.write_text("legacy")

    assert mqtt_server_ca_path(tmp_path) == provisioned


def test_pinned_ca_keeps_hostname_verification_enabled(tmp_path: Path, monkeypatch):
    (tmp_path / "server_ca.pem").write_text("current")

    _streamer, client = build_streamer(tmp_path, monkeypatch)

    assert (Path(client.tls_options["ca_certs"]), client.insecure_calls) == (
        tmp_path / "server_ca.pem",
        0,
    )


def test_legacy_ca_disables_only_hostname_verification(tmp_path: Path, monkeypatch):
    (tmp_path / "ca.pem").write_text("legacy")

    _streamer, client = build_streamer(tmp_path, monkeypatch)

    assert (Path(client.tls_options["ca_certs"]), client.insecure_calls) == (
        tmp_path / "ca.pem",
        1,
    )
