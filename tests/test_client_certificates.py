import ipaddress
import socket
import ssl
import stat
from datetime import datetime, timedelta, timezone

import pytest
from cradlewise_client.certificates import (
    BrokerCertificateError,
    _unverified_chain,
    fetch_server_chain,
    materialize_credentials,
    validate_server_chain,
)
from cradlewise_client.cloud import ProvisionedCredentials
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def _chain(host: str = "192.0.2.10") -> list[bytes]:
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Greengrass Core CA")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf = (
        x509.CertificateBuilder()
        .subject_name(
            x509.Name(
                [
                    x509.NameAttribute(
                        NameOID.COMMON_NAME,
                        "aws.greengrass.clientdevices.mqtt.Moquette",
                    )
                ]
            )
        )
        .issuer_name(ca_name)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=10))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(host))]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    return [
        leaf.public_bytes(serialization.Encoding.DER),
        ca.public_bytes(serialization.Encoding.DER),
    ]


def test_validate_server_chain_accepts_der_from_python_ssl():
    ca = validate_server_chain(_chain(), "192.0.2.10")

    assert ca.subject == ca.issuer


def test_validate_server_chain_rejects_wrong_host():
    with pytest.raises(BrokerCertificateError, match="not valid for"):
        validate_server_chain(_chain(), "192.0.2.11")


def test_fetch_server_chain_requires_tls_1_2_or_newer(monkeypatch, tmp_path):
    class Context:
        check_hostname = True
        verify_mode = ssl.CERT_REQUIRED
        minimum_version = ssl.TLSVersion.MINIMUM_SUPPORTED

        @staticmethod
        def load_cert_chain(_certificate, _private_key):
            return None

    context = Context()

    def fail_connection(*_args, **_kwargs):
        raise OSError("offline")

    monkeypatch.setattr(ssl, "SSLContext", lambda _protocol: context)
    monkeypatch.setattr(socket, "create_connection", fail_connection)

    with pytest.raises(BrokerCertificateError, match="could not inspect"):
        fetch_server_chain("192.0.2.10", tmp_path / "cert", tmp_path / "key")

    assert context.minimum_version is ssl.TLSVersion.TLSv1_2


def test_materialize_credentials_prefers_pinned_server_ca(tmp_path):
    credentials = materialize_credentials(
        tmp_path,
        ProvisionedCredentials(
            device_id="device-1",
            client_certificate="certificate",
            client_private_key="private-key",
            group_ca_certificate="group-ca",
        ),
        server_ca_certificate="server-ca",
    )

    assert credentials.ca_path == tmp_path / "server_ca.pem"


def test_materialize_credentials_restricts_directory_and_file_permissions(tmp_path):
    materialize_credentials(
        tmp_path,
        ProvisionedCredentials(
            device_id="device-1",
            client_certificate="certificate",
            client_private_key="private-key",
            group_ca_certificate="group-ca",
        ),
    )

    file_modes = {
        path.name: stat.S_IMODE(path.stat().st_mode)
        for path in tmp_path.iterdir()
        if path.is_file()
    }
    assert (stat.S_IMODE(tmp_path.stat().st_mode), file_modes) == (
        0o700,
        {
            "ca.pem": 0o600,
            "client_cert.pem": 0o600,
            "client_key.pem": 0o600,
            "device_id": 0o600,
        },
    )


def test_unverified_chain_supports_the_python_310_private_ssl_api():
    class LegacyCertificate:
        def public_bytes(self) -> str:
            return "-----BEGIN CERTIFICATE-----\nlegacy\n-----END CERTIFICATE-----\n"

    class LegacySslObject:
        @staticmethod
        def get_unverified_chain() -> list[LegacyCertificate]:
            return [LegacyCertificate()]

    class LegacySocket:
        _sslobj = LegacySslObject()

    assert _unverified_chain(LegacySocket()) == [
        b"-----BEGIN CERTIFICATE-----\nlegacy\n-----END CERTIFICATE-----\n"
    ]


def test_unverified_chain_rejects_an_unsupported_ssl_runtime():
    with pytest.raises(BrokerCertificateError, match="does not support"):
        _unverified_chain(object())
