from pathlib import Path

from cradlewise_client.local import LocalCredentials
from cradlewise_client.remote import REMOTE_MQTT_ENDPOINT, RemoteCradleClient
from test_local_client import FakeMqttClient


def _credentials(tmp_path: Path) -> LocalCredentials:
    for name in ("ca.pem", "client_cert.pem", "client_key.pem"):
        (tmp_path / name).write_text(name, encoding="utf-8")
    (tmp_path / "device_id").write_text("device-1", encoding="utf-8")
    return LocalCredentials.from_directory(tmp_path)


async def test_remote_client_uses_aws_endpoint_and_system_roots(tmp_path: Path):
    mqtt_client = FakeMqttClient()
    client = RemoteCradleClient(
        host=REMOTE_MQTT_ENDPOINT,
        cradle_id="cradle-1",
        credentials=_credentials(tmp_path),
        update_callback=lambda update: None,
        connection_callback=lambda connected: None,
        mqtt_client_factory=lambda **_kwargs: mqtt_client,
    )

    await client.async_start()

    assert (mqtt_client.connected_to[0], mqtt_client.tls_options.get("ca_certs")) == (
        REMOTE_MQTT_ENDPOINT,
        None,
    )
    await client.async_stop()
