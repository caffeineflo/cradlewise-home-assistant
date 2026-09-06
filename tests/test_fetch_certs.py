from pathlib import Path

from cradlewise_client.cloud import CradleAccount, ProvisionedCredentials

import fetch_certs


def test_fetch_certs_uses_shared_client_and_secure_materialization(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    account = CradleAccount(
        baby_id=42,
        cradle_id="cradle-1",
        name="Nursery Crib",
    )
    credentials = ProvisionedCredentials(
        device_id="device-1",
        client_certificate="certificate",
        client_private_key="private key",
        group_ca_certificate="group CA",
    )
    events = []

    class FakeCloudClient:
        def __init__(self, *, email, password):
            events.append(("created", email, password))

        def authenticate(self):
            events.append(("authenticated",))

        def list_accounts(self):
            return [account]

        def provision_credentials(self, selected, *, timezone, country):
            events.append(("provisioned", selected, timezone, country))
            return credentials

    def fake_materialize(directory, provisioned):
        events.append(("materialized", directory, provisioned))

    monkeypatch.setenv("CRADLEWISE_EMAIL", "parent@example.com")
    monkeypatch.setenv("CRADLEWISE_PASSWORD", "account password")
    monkeypatch.setattr(fetch_certs, "CloudAccountClient", FakeCloudClient)
    monkeypatch.setattr(fetch_certs, "materialize_credentials", fake_materialize)

    result = fetch_certs.main(
        [
            "--output-dir",
            str(tmp_path),
            "--timezone",
            "America/New_York",
            "--country",
            "US",
        ]
    )

    output = capsys.readouterr().out
    assert (result, events, "private key" in output) == (
        0,
        [
            ("created", "parent@example.com", "account password"),
            ("authenticated",),
            ("provisioned", account, "America/New_York", "US"),
            ("materialized", tmp_path / "cradle-1", credentials),
        ],
        False,
    )


def test_fetch_certs_rolls_back_registration_after_write_failure(
    tmp_path: Path,
    monkeypatch,
):
    account = CradleAccount(
        baby_id=42,
        cradle_id="cradle-1",
        name="Nursery Crib",
    )
    credentials = ProvisionedCredentials(
        device_id="device-1",
        client_certificate="certificate",
        client_private_key="private key",
        group_ca_certificate="group CA",
    )
    removed = []

    class FakeCloudClient:
        def __init__(self, **_kwargs):
            return None

        def authenticate(self):
            return None

        def list_accounts(self):
            return [account]

        def provision_credentials(self, selected, **_kwargs):
            return credentials

        def remove_user_devices(self, selected, device_ids):
            removed.append((selected, device_ids))
            return device_ids

    def fail_materialization(directory, _credentials):
        directory.mkdir(parents=True)
        (directory / "client_key.pem").write_text("partial", encoding="utf-8")
        raise OSError("disk full")

    monkeypatch.setenv("CRADLEWISE_EMAIL", "parent@example.com")
    monkeypatch.setenv("CRADLEWISE_PASSWORD", "account password")
    monkeypatch.setattr(fetch_certs, "CloudAccountClient", FakeCloudClient)
    monkeypatch.setattr(fetch_certs, "materialize_credentials", fail_materialization)

    result = fetch_certs.main(["--output-dir", str(tmp_path)])

    assert (result, removed, (tmp_path / "cradle-1").exists()) == (
        1,
        [(account, ["device-1"])],
        False,
    )
