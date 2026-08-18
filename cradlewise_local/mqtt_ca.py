"""Pin the rotating Greengrass v2 MQTT broker's long-lived core CA."""

from __future__ import annotations

import argparse
import ipaddress
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import NameOID

MQTT_PORT = 8883
MQTT_BROKER_COMMON_NAME = "aws.greengrass.clientdevices.mqtt.Moquette"
MQTT_CA_COMMON_NAME = "Greengrass Core CA"
PEM_CERTIFICATE = re.compile(
    rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
    re.DOTALL,
)


class MqttCaError(RuntimeError):
    """Raised when a broker CA cannot be fetched or safely pinned."""


def _common_name(certificate: x509.Certificate) -> str | None:
    values = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    return values[0].value if values else None


def fetch_server_chain(
    host: str,
    client_cert: Path,
    client_key: Path,
    *,
    port: int = MQTT_PORT,
) -> list[bytes]:
    """Fetch the broker certificate chain without accepting it as trusted."""
    command = [
        "openssl",
        "s_client",
        "-connect",
        f"{host}:{port}",
        "-cert",
        str(client_cert),
        "-key",
        str(client_key),
        "-showcerts",
        "-no-CAfile",
        "-no-CApath",
    ]
    try:
        result = subprocess.run(
            command,
            input=b"",
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MqttCaError(f"could not inspect MQTT TLS chain: {exc}") from exc
    certificates = PEM_CERTIFICATE.findall(result.stdout)
    if len(certificates) < 2:
        detail = result.stderr.decode(errors="replace").strip().splitlines()
        suffix = f": {detail[-1]}" if detail else ""
        raise MqttCaError(f"MQTT broker did not return a certificate chain{suffix}")
    return certificates


def validate_server_chain(
    certificate_pems: list[bytes],
    host: str,
    *,
    now: datetime | None = None,
) -> x509.Certificate:
    """Validate the expected Greengrass v2 broker shape before trusting its CA."""
    certificates = [x509.load_pem_x509_certificate(pem) for pem in certificate_pems]
    leaf = certificates[0]
    issuers = [
        certificate
        for certificate in certificates[1:]
        if certificate.subject == leaf.issuer
    ]
    if len(issuers) != 1:
        raise MqttCaError("MQTT broker chain has no unique issuer for its leaf")
    ca = issuers[0]

    if _common_name(leaf) != MQTT_BROKER_COMMON_NAME:
        raise MqttCaError("MQTT broker certificate has an unexpected common name")
    if _common_name(ca) != MQTT_CA_COMMON_NAME or ca.subject != ca.issuer:
        raise MqttCaError("MQTT broker issuer is not a self-issued Greengrass Core CA")
    try:
        constraints = ca.extensions.get_extension_for_class(x509.BasicConstraints)
    except x509.ExtensionNotFound as exc:
        raise MqttCaError("Greengrass Core CA is missing basic constraints") from exc
    if not constraints.value.ca:
        raise MqttCaError("Greengrass Core CA certificate is not marked as a CA")

    current = now or datetime.now(timezone.utc)
    for certificate in (leaf, ca):
        if (
            not certificate.not_valid_before_utc
            <= current
            <= certificate.not_valid_after_utc
        ):
            raise MqttCaError(
                "MQTT broker chain contains an expired or future certificate"
            )
    try:
        leaf.verify_directly_issued_by(ca)
        ca.verify_directly_issued_by(ca)
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise MqttCaError("MQTT broker chain signature validation failed") from exc

    try:
        expected_ip = ipaddress.ip_address(host)
    except ValueError:
        expected_ip = None
    try:
        alternative_names = leaf.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
    except x509.ExtensionNotFound as exc:
        raise MqttCaError(
            "MQTT broker certificate has no subject alternative name"
        ) from exc
    if expected_ip is not None:
        valid_host = expected_ip in alternative_names.get_values_for_type(
            x509.IPAddress
        )
    else:
        valid_host = host in alternative_names.get_values_for_type(x509.DNSName)
    if not valid_host:
        raise MqttCaError(f"MQTT broker certificate is not valid for {host}")
    return ca


def write_pinned_ca(certificate: x509.Certificate, output: Path, replace: bool) -> bool:
    """Atomically write a new CA, refusing an unapproved pin replacement."""
    pem = certificate.public_bytes(serialization.Encoding.PEM)
    if output.exists():
        existing = x509.load_pem_x509_certificate(output.read_bytes())
        if existing.fingerprint(hashes.SHA256()) == certificate.fingerprint(
            hashes.SHA256()
        ):
            return False
        if not replace:
            raise MqttCaError(
                f"{output} already contains a different CA; rerun with --replace "
                "after verifying the crib firmware change"
            )

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as temporary:
            temporary.write(pem)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, output)
    finally:
        if temporary_name is not None and os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect and pin a Cradlewise Greengrass v2 MQTT server CA"
    )
    parser.add_argument("--ip", required=True, help="Current crib IPv4 or IPv6 address")
    parser.add_argument("--certs-dir", required=True, type=Path)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    chain = fetch_server_chain(
        args.ip,
        args.certs_dir / "client_cert.pem",
        args.certs_dir / "client_key.pem",
    )
    ca = validate_server_chain(chain, args.ip)
    output = args.certs_dir / "server_ca.pem"
    changed = write_pinned_ca(ca, output, args.replace)
    fingerprint = ca.fingerprint(hashes.SHA256()).hex(":")
    action = "Pinned" if changed else "Already pinned"
    print(f"{action} {output} (SHA-256 {fingerprint})")


if __name__ == "__main__":
    main()
