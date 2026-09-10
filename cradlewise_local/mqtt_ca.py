"""Pin the rotating Greengrass v2 MQTT broker's long-lived core CA."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import tempfile
from pathlib import Path

from cradlewise_client.certificates import BrokerCertificateError as MqttCaError
from cradlewise_client.certificates import (
    validate_server_chain as validate_server_chain,
)
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

MQTT_PORT = 8883
PEM_CERTIFICATE = re.compile(
    rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
    re.DOTALL,
)


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
