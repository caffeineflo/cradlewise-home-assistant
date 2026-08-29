from __future__ import annotations

import json
from types import SimpleNamespace

import cradlewise_client.cloud as cloud
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from cradlewise_client.cloud import CloudAccountClient, CradleAccount


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise cloud.requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def request(self, method, url, headers, data, timeout):
        self.requests.append((method, url, headers, data, timeout))
        return self.responses.pop(0)


def _authenticated(client):
    client._credentials = "credentials"
    client._raw_credentials = {
        "AccessKeyId": "key",
        "SecretKey": "secret",
        "SessionToken": "token",
    }
    return client


def test_list_accounts_returns_only_paired_cradles(monkeypatch):
    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "accounts": [
                        {"baby_id": "4", "cradle_id": "crib-1", "name": "A"},
                        {"baby_id": "5", "cradle_id": None, "name": "B"},
                    ]
                },
            )
        ]
    )
    client = _authenticated(
        CloudAccountClient(email="user@example.com", password="secret", session=session)
    )
    monkeypatch.setattr(cloud, "sign_request", lambda *args, **kwargs: {})

    accounts = client.list_accounts()

    assert accounts == [CradleAccount(baby_id=4, cradle_id="crib-1", name="A")]


def test_cloud_request_reauthenticates_once_on_forbidden(monkeypatch):
    session = FakeSession(
        [FakeResponse(403, {}), FakeResponse(200, {"babyPresent": True})]
    )
    client = _authenticated(
        CloudAccountClient(email="user@example.com", password="secret", session=session)
    )
    auth_calls = []

    def authenticate():
        auth_calls.append(True)
        client._credentials = f"credentials-{len(auth_calls)}"

    monkeypatch.setattr(client, "authenticate", authenticate)
    monkeypatch.setattr(cloud, "sign_request", lambda *args, **kwargs: {})

    state = client.get_cradle_state("crib-1")

    assert (state, len(auth_calls)) == ({"babyPresent": True}, 1)


@pytest.mark.parametrize(
    "error",
    [
        cloud.requests.ConnectionError("offline"),
        cloud.requests.Timeout("timed out"),
    ],
)
def test_cloud_request_reports_transport_failures_as_cloud_api_errors(
    monkeypatch,
    error,
):
    class FailingSession:
        def request(self, method, url, headers, data, timeout):
            raise error

    client = _authenticated(
        CloudAccountClient(
            email="user@example.com",
            password="secret",
            session=FailingSession(),
        )
    )
    monkeypatch.setattr(cloud, "sign_request", lambda *args, **kwargs: {})

    with pytest.raises(cloud.CloudApiError, match="request failed"):
        client.get_cradle_state("crib-1")


def test_get_cradle_ip_prefers_v2_state_message(monkeypatch):
    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "state_message": json.dumps(
                        {"info": {"connectivity": {"localIP": "192.0.2.10"}}}
                    )
                },
            )
        ]
    )
    client = _authenticated(
        CloudAccountClient(email="user@example.com", password="secret", session=session)
    )
    monkeypatch.setattr(cloud, "sign_request", lambda *args, **kwargs: {})

    address = client.get_cradle_ip("crib-1")

    assert address == "192.0.2.10"


def test_provisioning_classifies_certificate_objects(monkeypatch):
    session = FakeSession(
        [
            FakeResponse(
                200,
                {
                    "device_config": {
                        "cradle_id": "crib-1",
                        "device_id": "device-1",
                        "group_ca_cert": "-----BEGIN CERTIFICATE-----\nca",
                        "s3_object_keys": ["crib/key.pem", "crib/cert.pem"],
                    }
                },
            )
        ]
    )
    client = _authenticated(
        CloudAccountClient(email="user@example.com", password="secret", session=session)
    )
    objects = {
        "crib/key.pem": b"TEST PRIVATE KEY MATERIAL",
        "crib/cert.pem": b"-----BEGIN CERTIFICATE-----\ncert",
    }
    s3 = SimpleNamespace(
        get_object=lambda Bucket, Key: {
            "Body": SimpleNamespace(read=lambda: objects[Key])
        }
    )
    monkeypatch.setattr(cloud, "sign_request", lambda *args, **kwargs: {})
    monkeypatch.setattr(cloud.boto3, "client", lambda *args, **kwargs: s3)

    credentials = client.provision_credentials(
        CradleAccount(baby_id=4, cradle_id="crib-1", name="A")
    )

    assert (
        credentials.device_id,
        credentials.client_private_key,
        credentials.client_certificate,
    ) == (
        "device-1",
        "TEST PRIVATE KEY MATERIAL",
        "-----BEGIN CERTIFICATE-----\ncert",
    )


def test_authentication_reports_network_failures_as_cloud_api_errors(monkeypatch):
    class OfflineCognito:
        id_token = None

        def authenticate(self, password):
            raise EndpointConnectionError(endpoint_url="https://cognito.test")

    monkeypatch.setattr(cloud, "Cognito", lambda *args, **kwargs: OfflineCognito())
    client = CloudAccountClient(email="user@example.com", password="secret")

    with pytest.raises(cloud.CloudApiError, match="service is unavailable"):
        client.authenticate()


def test_authentication_reports_rejected_credentials_as_invalid_auth(monkeypatch):
    class RejectedCognito:
        id_token = None

        def authenticate(self, password):
            raise ClientError(
                {
                    "Error": {
                        "Code": "NotAuthorizedException",
                        "Message": "Incorrect username or password",
                    }
                },
                "InitiateAuth",
            )

    monkeypatch.setattr(cloud, "Cognito", lambda *args, **kwargs: RejectedCognito())
    client = CloudAccountClient(email="user@example.com", password="secret")

    with pytest.raises(cloud.CloudAuthenticationError):
        client.authenticate()
