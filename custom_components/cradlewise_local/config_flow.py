"""Config flow for the Cradlewise Local integration."""

from __future__ import annotations

from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_NAME
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .config_helpers import (
    bridge_base_url,
    info_url_from_status_url,
    is_http_url,
    is_rtsp_url,
    snapshot_url_from_status_url,
)
from .const import (
    CONF_BEARER_TOKEN,
    CONF_BRIDGE_API_VERSION,
    CONF_BRIDGE_STATUS_URL,
    CONF_BRIDGE_VERSION,
    CONF_CRADLE_ID,
    CONF_SNAPSHOT_URL,
    CONF_STREAM_URL,
    DEFAULT_NAME,
    DOMAIN,
)
from .coordinator import (
    BridgeApiError,
    BridgeAuthenticationError,
    BridgeVersionError,
    async_fetch_bridge_info,
)


def _schema() -> vol.Schema:
    """Build the compact user and reconfigure form schema."""
    return vol.Schema(
        {
            vol.Required(CONF_BRIDGE_STATUS_URL): str,
            vol.Required(CONF_BEARER_TOKEN): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        }
    )


def _normalize(
    user_input: dict[str, Any],
    stored_bearer_token: str | None = None,
) -> dict[str, str]:
    """Normalize the bridge address and retain an existing hidden token."""
    bridge_url = bridge_base_url(
        str(user_input.get(CONF_BRIDGE_STATUS_URL, "")).strip()
    )
    bearer_token = str(user_input.get(CONF_BEARER_TOKEN, "")).strip()
    if not bearer_token and stored_bearer_token:
        bearer_token = stored_bearer_token
    return {
        CONF_BRIDGE_STATUS_URL: bridge_url,
        CONF_BEARER_TOKEN: bearer_token,
    }


def _entry_data(
    bridge: dict[str, Any],
    connection: dict[str, str],
    name: str,
) -> dict[str, Any]:
    """Build stable config-entry data from the authenticated bridge contract."""
    bridge_url = connection[CONF_BRIDGE_STATUS_URL]
    data: dict[str, Any] = {
        CONF_NAME: name,
        CONF_CRADLE_ID: bridge["device"]["id"].strip(),
        CONF_STREAM_URL: bridge["stream"]["url"].strip(),
        CONF_SNAPSHOT_URL: snapshot_url_from_status_url(bridge_url),
        CONF_BRIDGE_STATUS_URL: bridge_url,
        CONF_BRIDGE_API_VERSION: bridge["api_version"],
        CONF_BRIDGE_VERSION: str(bridge.get("bridge_version", "unknown")),
    }
    if connection[CONF_BEARER_TOKEN]:
        data[CONF_BEARER_TOKEN] = connection[CONF_BEARER_TOKEN]
    return data


class CradlewiseConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Cradlewise Local config flow."""

    VERSION = 3
    MINOR_VERSION = 0

    async def _async_bridge_data(
        self,
        connection: dict[str, str],
        name: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Validate the compact connection form and derive device configuration."""
        bridge_url = connection[CONF_BRIDGE_STATUS_URL]
        if not is_http_url(bridge_url):
            return None, "invalid_bridge_status_url"
        try:
            bridge = await async_fetch_bridge_info(
                async_get_clientsession(self.hass),
                info_url_from_status_url(bridge_url),
                connection.get(CONF_BEARER_TOKEN),
            )
        except BridgeAuthenticationError:
            return None, "invalid_auth"
        except BridgeVersionError:
            return None, "unsupported_bridge"
        except BridgeApiError:
            return None, "invalid_bridge_response"
        except (aiohttp.ClientError, TimeoutError):
            return None, "cannot_connect"

        data = _entry_data(bridge, connection, name)
        if not is_rtsp_url(data[CONF_STREAM_URL]):
            return None, "invalid_bridge_response"
        return data, None

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            connection = _normalize(user_input)
            data, error = await self._async_bridge_data(connection, DEFAULT_NAME)
            if error is not None:
                errors["base"] = error
            elif data is not None:
                await self.async_set_unique_id(data[CONF_CRADLE_ID])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=DEFAULT_NAME, data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _schema(),
                {
                    key: value
                    for key, value in (user_input or {}).items()
                    if key != CONF_BEARER_TOKEN
                },
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Validate and update an existing config entry without changing identity."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            connection = _normalize(
                user_input,
                entry.data.get(CONF_BEARER_TOKEN),
            )
            name = str(entry.data.get(CONF_NAME, entry.title))
            data, error = await self._async_bridge_data(connection, name)
            if error is not None:
                errors["base"] = error
            elif data is not None:
                await self.async_set_unique_id(data[CONF_CRADLE_ID])
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry,
                    title=entry.title,
                    data_updates=data,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                _schema(),
                {
                    key: value
                    for key, value in (user_input or dict(entry.data)).items()
                    if key == CONF_BRIDGE_STATUS_URL
                },
            ),
            errors=errors,
        )
