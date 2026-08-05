import asyncio
from datetime import datetime, timezone

import pytest

import cradlewise_local.data_api as data_api
from cradlewise_local.config import BridgeConfig
from cradlewise_local.data_api import CradlewiseDataApiClient, DataApiError
from cradlewise_local.status import BridgeStatusStore


class FakeResponse:
    def __init__(self, status_code, payload, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise data_api.requests.HTTPError(f"HTTP {self.status_code}")


def _day_metrics_payload():
    return {
        "timezone": "America/New_York",
        "metrics": [
            {
                "date": "2026-03-09 00:00:00.000000",
                "banners": [],
            },
            {
                "date": "2026-03-10 00:00:00.000000",
                "banners": [
                    {"header": "SOOTHES", "data": {"value": 3}},
                    {"header": "NAPS", "data": {"value": 2}},
                    {"header": "LONGEST STRETCH", "data": {"value": 5400}},
                ],
            },
        ],
    }


def _c_chart_payload():
    return {
        "timezone": "America/New_York",
        "day_aggregates": {
            "2026-03-09 00:00:00.000000": {
                "total_time_asleep_in_seconds": 3600,
                "total_day_sleep": 3600,
                "total_night_sleep": 0,
            },
            "2026-03-10 00:00:00.000000": {
                "total_time_asleep_in_seconds": 7200,
                "total_day_sleep": 1800,
                "total_night_sleep": 5400,
            },
        },
    }


def test_data_api_client_normalizes_current_daily_metrics(monkeypatch):
    responses = [
        FakeResponse(200, _day_metrics_payload()),
        FakeResponse(200, _c_chart_payload()),
    ]
    monkeypatch.setattr(
        data_api.requests,
        "get",
        lambda url, headers, params, timeout: responses.pop(0),
    )
    client = CradlewiseDataApiClient(token="cw_test")

    metrics = client.get_daily_sleep_metrics(
        now=datetime(2026, 3, 10, 18, tzinfo=timezone.utc)
    )

    assert metrics == {
        "date": "2026-03-10",
        "timezone": "America/New_York",
        "total_sleep_today": 120,
        "day_sleep_today": 30,
        "night_sleep_today": 90,
        "naps_today": 2,
        "longest_stretch_today": 90,
        "soothes_today": 3,
    }


def test_data_api_client_reports_rate_limit_without_waiting(monkeypatch):
    monkeypatch.setattr(
        data_api.requests,
        "get",
        lambda url, headers, params, timeout: FakeResponse(
            429,
            {"detail": "Rate limit exceeded"},
            {"Retry-After": "60"},
        ),
    )

    with pytest.raises(DataApiError, match="rate limited; retry after 60 seconds"):
        CradlewiseDataApiClient(token="cw_test").get_daily_sleep_metrics()


def test_data_api_client_does_not_relabel_prior_day_as_today(monkeypatch):
    day_metrics = _day_metrics_payload()
    day_metrics["metrics"] = day_metrics["metrics"][:1]
    c_chart = _c_chart_payload()
    c_chart["day_aggregates"].pop("2026-03-10 00:00:00.000000")
    responses = [FakeResponse(200, day_metrics), FakeResponse(200, c_chart)]
    monkeypatch.setattr(
        data_api.requests,
        "get",
        lambda url, headers, params, timeout: responses.pop(0),
    )

    metrics = CradlewiseDataApiClient(token="cw_test").get_daily_sleep_metrics(
        now=datetime(2026, 3, 10, 18, tzinfo=timezone.utc)
    )

    assert metrics["total_sleep_today"] == 0


def test_data_api_poller_updates_analytics(monkeypatch, tmp_path):
    certs_dir = tmp_path / "certs"
    certs_dir.mkdir()
    for name in ("ca.pem", "client_cert.pem", "client_key.pem", "device_id"):
        (certs_dir / name).write_text("test")

    class FakeDataApiClient:
        def __init__(self, token):
            self.token = token

        def get_daily_sleep_metrics(self):
            return {
                "date": "2026-03-10",
                "timezone": "America/New_York",
                "total_sleep_today": 120,
            }

    async def run_once():
        config = BridgeConfig.from_values(
            cradle_id="cradle-1",
            certs_dir=certs_dir,
            output_url="rtsp://127.0.0.1:8554/cradlewise",
            data_api_token="cw_test",
            data_api_poll_interval=900,
        )
        store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
        task = asyncio.create_task(data_api.poll_data_api(config, store))
        try:
            for _ in range(20):
                await asyncio.sleep(0.01)
                if store.snapshot()["analytics"]["available"]:
                    break
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        return store.snapshot()["analytics"]

    monkeypatch.setattr(data_api, "CradlewiseDataApiClient", FakeDataApiClient)

    analytics = asyncio.run(run_once())

    assert analytics["total_sleep_today"] == 120
