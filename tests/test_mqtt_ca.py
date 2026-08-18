import ipaddress
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from cradlewise_local.mqtt_ca import MqttCaError, validate_server_chain


def build_chain(host: str = "192.0.2.10") -> list[bytes]:
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
        leaf.public_bytes(serialization.Encoding.PEM),
        ca.public_bytes(serialization.Encoding.PEM),
    ]


def test_validate_server_chain_accepts_expected_greengrass_chain():
    ca = validate_server_chain(build_chain(), "192.0.2.10")

    assert ca.subject == ca.issuer


def test_validate_server_chain_rejects_wrong_host():
    with pytest.raises(MqttCaError, match="not valid for"):
        validate_server_chain(build_chain(), "192.0.2.11")
