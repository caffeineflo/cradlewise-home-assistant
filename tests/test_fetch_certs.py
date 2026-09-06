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
        (directory / "device_id").write_text("device-1", encoding="utf-8")
        events.append(("materialized", directory.parent, provisioned))

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
    assert (
        result,
        events,
        "private key" in output,
        (tmp_path / "cradle-1" / "device_id").read_text(encoding="utf-8"),
    ) == (
        0,
        [
            ("created", "parent@example.com", "account password"),
            ("authenticated",),
            ("provisioned", account, "America/New_York", "US"),
            ("materialized", tmp_path, credentials),
        ],
        False,
        "device-1",
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
        directory.mkdir(parents=True, exist_ok=True)
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


def test_fetch_certs_preserves_existing_bundle_after_write_failure(
    tmp_path: Path,
    monkeypatch,
):
    account = CradleAccount(42, "cradle-1", "Nursery Crib")
    credentials = ProvisionedCredentials(
        "device-2",
        "certificate",
        "private key",
        "group CA",
    )
    output_directory = tmp_path / "cradle-1"
    output_directory.mkdir()
    old_device_id = output_directory / "device_id"
    old_device_id.write_text("device-1", encoding="utf-8")
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
            removed.extend(device_ids)
            return device_ids

    def fail_materialization(directory, _credentials):
        (directory / "device_id").write_text("device-2", encoding="utf-8")
        raise OSError("disk full")

    monkeypatch.setenv("CRADLEWISE_EMAIL", "parent@example.com")
    monkeypatch.setenv("CRADLEWISE_PASSWORD", "account password")
    monkeypatch.setattr(fetch_certs, "CloudAccountClient", FakeCloudClient)
    monkeypatch.setattr(fetch_certs, "materialize_credentials", fail_materialization)

    result = fetch_certs.main(["--output-dir", str(tmp_path)])

    assert (result, old_device_id.read_text(encoding="utf-8"), removed) == (
        1,
        "device-1",
        ["device-2"],
    )
