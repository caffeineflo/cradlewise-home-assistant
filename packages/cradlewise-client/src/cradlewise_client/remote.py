"""Cradlewise AWS IoT MQTT provider."""

from __future__ import annotations

import ssl

from paho.mqtt import client as mqtt

from .local import LocalCradleClient

REMOTE_MQTT_ENDPOINT = "a2bby18smixe1f-ats.iot.us-east-1.amazonaws.com"


class RemoteCradleClient(LocalCradleClient):
    """Connect to the Cradlewise AWS IoT shadow with provisioned device certs."""

    def _configure_tls(self, client: mqtt.Client) -> None:
        """Use public system roots for the AWS IoT endpoint."""
        client.tls_set(
            certfile=str(self.credentials.client_cert_path),
            keyfile=str(self.credentials.client_key_path),
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )
