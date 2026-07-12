from dataclasses import dataclass
from typing import Any

import pytest
import requests

import cradlewise_api


@dataclass
class FakeResponse:
    payload: dict[str, Any]

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


def test_get_accounts_uses_bounded_request_timeout(monkeypatch):
    timeout_seen = None

    def fake_get(url, *, headers, timeout):
        del url, headers
        nonlocal timeout_seen
        timeout_seen = timeout
        return FakeResponse({"accounts": []})

    monkeypatch.setattr(cradlewise_api, "sign_request", lambda *args: {})
    monkeypatch.setattr(cradlewise_api.requests, "get", fake_get)

    cradlewise_api.get_accounts("parent@example.test", object())

    assert timeout_seen == cradlewise_api.REQUEST_TIMEOUT_SECONDS


def test_get_cradle_ip_reads_v2_state_message(monkeypatch):
    payload = {"state_message": ('{"info":{"connectivity":{"localIP":"192.0.2.10"}}}')}
    monkeypatch.setattr(cradlewise_api, "sign_request", lambda *args: {})
    monkeypatch.setattr(
        cradlewise_api.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(payload),
    )

    result = cradlewise_api.get_cradle_ip("cradle-id", object())

    assert result == "192.0.2.10"


def test_get_cradle_ip_falls_back_to_v1(monkeypatch):
    responses = iter(
        [
            requests.ConnectionError("v2 unavailable"),
            FakeResponse({"local_ip": "192.0.2.11"}),
        ]
    )

    def fake_get(*args, **kwargs):
        del args, kwargs
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(cradlewise_api, "sign_request", lambda *args: {})
    monkeypatch.setattr(cradlewise_api.requests, "get", fake_get)

    result = cradlewise_api.get_cradle_ip("cradle-id", object())

    assert result == "192.0.2.11"


def test_get_cradle_ip_reports_both_endpoint_failures(monkeypatch):
    monkeypatch.setattr(cradlewise_api, "sign_request", lambda *args: {})
    monkeypatch.setattr(
        cradlewise_api.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            requests.ConnectionError("offline")
        ),
    )

    with pytest.raises(cradlewise_api.CradlewiseAPIError, match="v2=.*v1="):
        cradlewise_api.get_cradle_ip("cradle-id", object())
