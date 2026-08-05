"""Optional client for the official Cradlewise Data API."""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from .config import BridgeConfig
from .status import BridgeStatusStore

log = logging.getLogger(__name__)

DATA_API_BASE_URL = "https://integrations.cradlewise.com/api/v1"


class DataApiError(RuntimeError):
    """Raised when official Data API data cannot be fetched or normalized."""


def _date_from_value(value: Any) -> date | None:
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result) or result < 0:
        return None
    return result


def _minutes_from_seconds(value: Any) -> int:
    seconds = _number(value)
    return round(seconds / 60) if seconds is not None else 0


def _count(value: Any) -> int:
    number = _number(value)
    return round(number) if number is not None else 0


def _dated_object(
    values: list[Any],
    *,
    target_date: date,
    date_field: str,
) -> dict[str, Any]:
    for value in values:
        if not isinstance(value, dict):
            continue
        value_date = _date_from_value(value.get(date_field))
        if value_date == target_date:
            return value
    return {}


def _dated_mapping(
    values: dict[str, Any],
    *,
    target_date: date,
) -> dict[str, Any]:
    for raw_date, value in values.items():
        value_date = _date_from_value(raw_date)
        if value_date == target_date and isinstance(value, dict):
            return value
    return {}


@dataclass(frozen=True)
class CradlewiseDataApiClient:
    """Blocking, read-only client for official daily sleep analytics."""

    token: str
    timeout_seconds: int = 20

    def _get_json(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        try:
            response = requests.get(
                f"{DATA_API_BASE_URL}{path}",
                headers={"Authorization": f"Bearer {self.token}"},
                params=params,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise DataApiError(f"Cradlewise Data API request failed: {exc}") from exc
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            detail = (
                f"; retry after {retry_after} seconds"
                if retry_after is not None
                else ""
            )
            raise DataApiError(f"Cradlewise Data API rate limited{detail}")
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise DataApiError(
                f"Cradlewise Data API request failed: HTTP {response.status_code}"
            ) from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise DataApiError("Cradlewise Data API returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise DataApiError("Cradlewise Data API response was not an object")
        return payload

    def get_daily_sleep_metrics(
        self,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Fetch and normalize the current Cradlewise sleep day."""
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise DataApiError("Data API polling requires a timezone-aware clock")
        utc_now = current.astimezone(timezone.utc)
        start = (utc_now - timedelta(days=2)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end = (utc_now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        params = {
            "start_time": start.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": end.strftime("%Y-%m-%d %H:%M:%S"),
        }
        day_metrics = self._get_json("/sleep/day-metrics", params)
        c_chart = self._get_json("/sleep/c-chart", params)

        timezone_name = day_metrics.get("timezone") or c_chart.get("timezone")
        if not isinstance(timezone_name, str) or not timezone_name:
            raise DataApiError("Cradlewise Data API response is missing timezone")
        try:
            local_date = current.astimezone(ZoneInfo(timezone_name)).date()
        except ZoneInfoNotFoundError as exc:
            raise DataApiError(
                f"Cradlewise Data API returned unknown timezone {timezone_name!r}"
            ) from exc

        raw_metrics = day_metrics.get("metrics")
        metrics = raw_metrics if isinstance(raw_metrics, list) else []
        metric = _dated_object(
            metrics,
            target_date=local_date,
            date_field="date",
        )
        banners = metric.get("banners")
        banner_values = {}
        if isinstance(banners, list):
            for banner in banners:
                if not isinstance(banner, dict):
                    continue
                header = banner.get("header")
                data = banner.get("data")
                if isinstance(header, str) and isinstance(data, dict):
                    banner_values[header] = data.get("value")

        raw_aggregates = c_chart.get("day_aggregates")
        aggregates = raw_aggregates if isinstance(raw_aggregates, dict) else {}
        aggregate = _dated_mapping(
            aggregates,
            target_date=local_date,
        )
        return {
            "date": local_date.isoformat(),
            "timezone": timezone_name,
            "total_sleep_today": _minutes_from_seconds(
                aggregate.get("total_time_asleep_in_seconds")
            ),
            "day_sleep_today": _minutes_from_seconds(aggregate.get("total_day_sleep")),
            "night_sleep_today": _minutes_from_seconds(
                aggregate.get("total_night_sleep")
            ),
            "naps_today": _count(banner_values.get("NAPS")),
            "longest_stretch_today": _minutes_from_seconds(
                banner_values.get("LONGEST STRETCH")
            ),
            "soothes_today": _count(banner_values.get("SOOTHES")),
        }


async def poll_data_api(
    config: BridgeConfig,
    status_store: BridgeStatusStore,
) -> None:
    """Poll official daily analytics until cancelled."""
    if not config.data_api_enabled:
        return
    if config.data_api_token is None:
        raise DataApiError("Data API polling requires a token")

    client = CradlewiseDataApiClient(token=config.data_api_token)
    log.info(
        "Official Data API sleep polling enabled every %d seconds",
        config.data_api_poll_interval,
    )
    while True:
        try:
            payload = await asyncio.to_thread(client.get_daily_sleep_metrics)
            status_store.update_sleep_analytics(payload)
            log.debug("Official Data API sleep analytics updated")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            status_store.mark_sleep_analytics_error(str(exc))
            log.warning("Official Data API poll failed: %s", exc)
        await asyncio.sleep(config.data_api_poll_interval)
