from pathlib import Path

import pytest
from cradlewise_client.cloud import CradleAccount, ProvisionedCredentials

import fetch_certs


def _credentials(device_id: str = "device-2") -> ProvisionedCredentials:
    return ProvisionedCredentials(
        device_id,
        "certificate",
        "private key",
        "group CA",
    )


def _run_refresh(tmp_path: Path, monkeypatch, removed: list[str]) -> int:
    account = CradleAccount(42, "cradle-1", "Nursery Crib")

    class FakeCloudClient:
        def __init__(self, **_kwargs):
            return None

        def authenticate(self):
            return None

        def list_accounts(self):
            return [account]

        def provision_credentials(self, selected, **_kwargs):
            return _credentials()

        def remove_user_devices(self, selected, device_ids):
            removed.extend(device_ids)
            return device_ids

    monkeypatch.setenv("CRADLEWISE_EMAIL", "parent@example.com")
    monkeypatch.setenv("CRADLEWISE_PASSWORD", "account password")
    monkeypatch.setattr(fetch_certs, "CloudAccountClient", FakeCloudClient)
    return fetch_certs.main(["--output-dir", str(tmp_path)])


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

    def fake_materialize(directory, provisioned, **_kwargs):
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

    def fail_materialization(directory, _credentials, **_kwargs):
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

    def fail_materialization(directory, _credentials, **_kwargs):
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


def test_fetch_certs_preserves_backup_when_install_and_restore_fail(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    output_directory = tmp_path / "cradle-1"
    output_directory.mkdir()
    (output_directory / "device_id").write_text("device-1", encoding="utf-8")
    removed = []

    def fake_materialize(directory, _credentials, **_kwargs):
        (directory / "device_id").write_text("device-2", encoding="utf-8")

    real_replace = Path.replace

    def fail_install_and_restore(path, target):
        target = Path(target)
        if path.name.startswith(".cradle-1-staging-"):
            raise OSError("install failed")
        if path.name == "credentials" and target == output_directory:
            raise OSError("restore failed")
        return real_replace(path, target)

    monkeypatch.setattr(fetch_certs, "materialize_credentials", fake_materialize)
    monkeypatch.setattr(Path, "replace", fail_install_and_restore)

    result = _run_refresh(tmp_path, monkeypatch, removed)

    backups = list(tmp_path.glob(".cradle-1-backup-*/credentials/device_id"))
    output = capsys.readouterr().out
    assert (
        result,
        removed,
        output_directory.exists(),
        len(backups),
        backups[0].read_text(encoding="utf-8"),
        "Previous credentials remain at" in output,
    ) == (1, ["device-2"], False, 1, "device-1", True)


def test_fetch_certs_keeps_registration_when_backup_cleanup_fails(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    output_directory = tmp_path / "cradle-1"
    output_directory.mkdir()
    (output_directory / "device_id").write_text("device-1", encoding="utf-8")
    removed = []

    def fake_materialize(directory, _credentials, **_kwargs):
        (directory / "device_id").write_text("device-2", encoding="utf-8")

    real_rmtree = fetch_certs.shutil.rmtree

    def fail_backup_cleanup(path):
        path = Path(path)
        if path.name.startswith(".cradle-1-backup-"):
            raise OSError("cleanup failed")
        real_rmtree(path)

    monkeypatch.setattr(fetch_certs, "materialize_credentials", fake_materialize)
    monkeypatch.setattr(fetch_certs.shutil, "rmtree", fail_backup_cleanup)

    result = _run_refresh(tmp_path, monkeypatch, removed)

    backups = list(tmp_path.glob(".cradle-1-backup-*/credentials/device_id"))
    output = capsys.readouterr().out
    assert (
        result,
        removed,
        (output_directory / "device_id").read_text(encoding="utf-8"),
        len(backups),
        backups[0].read_text(encoding="utf-8"),
        "Previous credentials could not be removed" in output,
    ) == (0, [], "device-2", 1, "device-1", True)


def test_materialize_atomically_preserves_pinned_server_ca(tmp_path: Path):
    output_directory = tmp_path / "cradle-1"
    output_directory.mkdir()
    (output_directory / "server_ca.pem").write_text("pinned CA", encoding="utf-8")

    warning = fetch_certs._materialize_atomically(
        output_directory,
        _credentials(),
    )

    assert (
        warning,
        (output_directory / "device_id").read_text(encoding="utf-8"),
        (output_directory / "server_ca.pem").read_text(encoding="utf-8"),
    ) == (None, "device-2", "pinned CA")


def test_materialize_atomically_cleans_staging_when_backup_creation_fails(
    tmp_path: Path,
    monkeypatch,
):
    output_directory = tmp_path / "cradle-1"
    output_directory.mkdir()
    (output_directory / "device_id").write_text("device-1", encoding="utf-8")
    real_mkdtemp = fetch_certs.tempfile.mkdtemp

    def fail_backup_creation(*, prefix, dir):
        if prefix.startswith(".cradle-1-backup-"):
            raise OSError("backup creation failed")
        return real_mkdtemp(prefix=prefix, dir=dir)

    monkeypatch.setattr(fetch_certs.tempfile, "mkdtemp", fail_backup_creation)

    with pytest.raises(OSError, match="backup creation failed"):
        fetch_certs._materialize_atomically(output_directory, _credentials())

    assert (
        (output_directory / "device_id").read_text(encoding="utf-8"),
        list(tmp_path.glob(".cradle-1-staging-*")),
    ) == ("device-1", [])
