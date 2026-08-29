"""Safe broker certificate discovery and credential materialization."""

from __future__ import annotations

import ipaddress
import socket
import ssl
from datetime import datetime, timezone
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import NameOID

from .cloud import ProvisionedCredentials
from .local import MQTT_PORT, LocalCredentials

MQTT_BROKER_COMMON_NAME = "aws.greengrass.clientdevices.mqtt.Moquette"
MQTT_CA_COMMON_NAME = "Greengrass Core CA"


class BrokerCertificateError(RuntimeError):
    """Raised when the local broker chain cannot be safely pinned."""


def fetch_server_chain(
    host: str,
    client_certificate_path: Path,
    client_private_key_path: Path,
    *,
    port: int = MQTT_PORT,
) -> list[bytes]:
    """Fetch the untrusted broker chain using the provisioned client identity."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.load_cert_chain(client_certificate_path, client_private_key_path)
    try:
        with socket.create_connection((host, port), timeout=10) as raw_socket:
            with context.wrap_socket(raw_socket, server_hostname=host) as tls_socket:
                chain = _unverified_chain(tls_socket)
    except BrokerCertificateError:
        raise
    except (OSError, ssl.SSLError) as exc:
        raise BrokerCertificateError(
            f"could not inspect local MQTT broker TLS: {exc}"
        ) from exc
    if len(chain) < 2:
        raise BrokerCertificateError(
            "local MQTT broker did not return a certificate chain"
        )
    return chain


def validate_server_chain(
    certificate_data: list[bytes],
    host: str,
    *,
    now: datetime | None = None,
) -> x509.Certificate:
    """Validate the expected Greengrass broker shape before trusting its CA."""
    certificates = [_load_certificate(value) for value in certificate_data]
    leaf = certificates[0]
    issuers = [
        certificate
        for certificate in certificates[1:]
        if certificate.subject == leaf.issuer
    ]
    if len(issuers) != 1:
        raise BrokerCertificateError(
            "local MQTT broker chain has no unique issuer for its leaf"
        )
    ca = issuers[0]
    if _common_name(leaf) != MQTT_BROKER_COMMON_NAME:
        raise BrokerCertificateError(
            "local MQTT broker certificate has an unexpected common name"
        )
    if _common_name(ca) != MQTT_CA_COMMON_NAME or ca.subject != ca.issuer:
        raise BrokerCertificateError(
            "local MQTT broker issuer is not a self-issued Greengrass Core CA"
        )
    try:
        constraints = ca.extensions.get_extension_for_class(x509.BasicConstraints)
    except x509.ExtensionNotFound as exc:
        raise BrokerCertificateError(
            "Greengrass Core CA is missing basic constraints"
        ) from exc
    if not constraints.value.ca:
        raise BrokerCertificateError(
            "Greengrass Core CA certificate is not marked as a CA"
        )

    current = now or datetime.now(timezone.utc)
    for certificate in (leaf, ca):
        if not (
            certificate.not_valid_before_utc
            <= current
            <= certificate.not_valid_after_utc
        ):
            raise BrokerCertificateError(
                "local MQTT broker chain contains an expired or future certificate"
            )
    try:
        leaf.verify_directly_issued_by(ca)
        ca.verify_directly_issued_by(ca)
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise BrokerCertificateError(
            "local MQTT broker chain signature validation failed"
        ) from exc

    try:
        alternative_names = leaf.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
    except x509.ExtensionNotFound as exc:
        raise BrokerCertificateError(
            "local MQTT broker certificate has no subject alternative name"
        ) from exc
    try:
        expected_ip = ipaddress.ip_address(host)
    except ValueError:
        valid_host = host in alternative_names.get_values_for_type(x509.DNSName)
    else:
        valid_host = expected_ip in alternative_names.get_values_for_type(
            x509.IPAddress
        )
    if not valid_host:
        raise BrokerCertificateError(
            f"local MQTT broker certificate is not valid for {host}"
        )
    return ca


def pin_server_ca(
    host: str,
    client_certificate_path: Path,
    client_private_key_path: Path,
) -> str:
    """Fetch, validate, and return the crib's current broker CA as PEM."""
    chain = fetch_server_chain(
        host,
        client_certificate_path,
        client_private_key_path,
    )
    ca = validate_server_chain(chain, host)
    return ca.public_bytes(serialization.Encoding.PEM).decode("ascii")


def materialize_credentials(
    directory: Path,
    credentials: ProvisionedCredentials,
    *,
    server_ca_certificate: str | None = None,
) -> LocalCredentials:
    """Write one runtime-only credential bundle for Paho MQTT."""
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    values = {
        "ca.pem": credentials.group_ca_certificate,
        "client_cert.pem": credentials.client_certificate,
        "client_key.pem": credentials.client_private_key,
        "device_id": credentials.device_id,
    }
    if server_ca_certificate is not None:
        values["server_ca.pem"] = server_ca_certificate
    for name, value in values.items():
        path = directory / name
        path.write_text(value, encoding="utf-8")
        path.chmod(0o600)
    return LocalCredentials.from_directory(directory)


def _load_certificate(value: bytes) -> x509.Certificate:
    if value.startswith(b"-----BEGIN"):
        return x509.load_pem_x509_certificate(value)
    return x509.load_der_x509_certificate(value)


def _unverified_chain(tls_socket: ssl.SSLSocket) -> list[bytes]:
    """Return the peer chain across supported Python SSL API versions."""
    get_chain = getattr(tls_socket, "get_unverified_chain", None)
    if get_chain is None:
        ssl_object = getattr(tls_socket, "_sslobj", None)
        get_chain = getattr(ssl_object, "get_unverified_chain", None)
    if get_chain is None:
        raise BrokerCertificateError(
            "Python does not support retrieving the broker chain"
        )
    return [_certificate_bytes(certificate) for certificate in get_chain()]


def _certificate_bytes(certificate: object) -> bytes:
    if isinstance(certificate, bytes):
        return certificate
    public_bytes = getattr(certificate, "public_bytes", None)
    if public_bytes is None:
        raise BrokerCertificateError(
            "Python returned an unsupported broker certificate object"
        )
    value = public_bytes()
    if isinstance(value, str):
        return value.encode("ascii")
    if isinstance(value, bytes):
        return value
    raise BrokerCertificateError(
        "Python returned an unsupported broker certificate encoding"
    )


def _common_name(certificate: x509.Certificate) -> str | None:
    values = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    return values[0].value if values else None
