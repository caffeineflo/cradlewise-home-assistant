import asyncio
from pathlib import Path

import cradlewise_local.cloud_state as cloud_state
from cradlewise_local.cloud_state import CradlewiseCloudStateClient
from cradlewise_local.config import BridgeConfig
from cradlewise_local.status import BridgeStatusStore


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise cloud_state.requests.HTTPError(f"HTTP {self.status_code}")


def write_cert_set(path: Path) -> None:
    path.mkdir(parents=True)
    for name in ("ca.pem", "client_cert.pem", "client_key.pem", "device_id"):
        (path / name).write_text("test")


def test_cloud_state_client_reauthenticates_on_forbidden(monkeypatch):
    auth_calls = []
    responses = [
        FakeResponse(403, {}),
        FakeResponse(200, {"babyPresent": True}),
    ]

    def fake_authenticate(email, password):
        auth_calls.append((email, password))
        return object(), f"token-{len(auth_calls)}"

    monkeypatch.setattr(cloud_state, "authenticate", fake_authenticate)
    monkeypatch.setattr(
        cloud_state,
        "get_aws_credentials",
        lambda id_token: (f"creds-for-{id_token}", {}),
    )
    monkeypatch.setattr(
        cloud_state,
        "sign_request",
        lambda method, url, credentials: {"Authorization": str(credentials)},
    )
    monkeypatch.setattr(
        cloud_state.requests,
        "get",
        lambda url, headers, timeout: responses.pop(0),
    )

    client = CradlewiseCloudStateClient(
        email="user@example.com",
        password="secret",
    )

    assert client.get_cradle_state("cradle-1") == {"babyPresent": True}
    assert len(auth_calls) == 2


def test_cloud_state_poller_updates_device_state(monkeypatch, tmp_path):
    certs_dir = tmp_path / "certs"
    write_cert_set(certs_dir)

    class FakeCloudStateClient:
        def __init__(self, email, password):
            self.email = email
            self.password = password

        def get_cradle_state(self, cradle_id):
            return {"babyPresent": True, "babySleepPhaseV2": {"eventValue": 4}}

    async def run_once():
        config = BridgeConfig.from_values(
            cradle_id="cradle-1",
            certs_dir=certs_dir,
            output_url="rtsp://127.0.0.1:8554/cradlewise",
            cloud_email="user@example.com",
            cloud_password="secret",
            cloud_state_poll_interval=60,
        )
        store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
        task = asyncio.create_task(cloud_state.poll_cloud_state(config, store))

        try:
            for _ in range(20):
                await asyncio.sleep(0.01)
                if store.snapshot()["device_state"]["baby_present"] is True:
                    break
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

        return store.snapshot()["device_state"]

    monkeypatch.setattr(
        cloud_state,
        "CradlewiseCloudStateClient",
        FakeCloudStateClient,
    )

    device_state = asyncio.run(run_once())

    assert device_state["baby_present"] is True
    assert device_state["sleep_phase"] == "sleep"
    assert device_state["source"] == "cloud"
