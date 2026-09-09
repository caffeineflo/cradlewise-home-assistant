"""Offline smoke test run inside each final bridge image, without test dependencies."""

import importlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from stream_local import _make_rsa_certificate


def main() -> None:
    assert os.getuid() == 10001
    for module in ("aiortc", "boto3", "cryptography.x509", "cradlewise_local"):
        importlib.import_module(module)
    assert _make_rsa_certificate().getFingerprints()
    assert all(shutil.which(tool) is None for tool in ("pip", "uv", "uvx"))
    assert importlib.util.find_spec("pip") is None
    assert importlib.util.find_spec("ensurepip") is None

    # Invalid synthetic certificates exercise the real supervisor's failure path.
    # Docker runs this with --network none; no account or crib is contacted.
    with tempfile.TemporaryDirectory() as directory:
        for name in ("ca.pem", "client_cert.pem", "client_key.pem", "device_id"):
            Path(directory, name).write_text("offline-smoke-fixture", encoding="utf-8")
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "cradlewise_local",
                "--cradle-id",
                "offline-smoke-fixture",
                "--ip",
                "127.0.0.1",
                "--certs-dir",
                directory,
                "--output-url",
                "rtsp://127.0.0.1:8554/offline",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            deadline = time.monotonic() + 10
            while True:
                if process.poll() is not None:
                    raise RuntimeError("bridge exited before its API became live")
                try:
                    with urllib.request.urlopen(
                        "http://127.0.0.1:8080/live", timeout=1
                    ) as response:
                        assert response.status == 200
                    break
                except urllib.error.URLError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.1)
            try:
                urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=1)
            except urllib.error.HTTPError as error:
                assert error.code == 503
            else:
                raise AssertionError("an offline crib must not report healthy media")
        finally:
            process.terminate()
            try:
                output, _ = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                output, _ = process.communicate()
                raise RuntimeError(
                    f"bridge did not stop on SIGTERM: {output}"
                ) from None
            print(output)
        assert process.returncode == 0


if __name__ == "__main__":
    main()
