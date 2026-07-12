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
    is_http_url,
    is_rtsp_url,
    snapshot_url_from_status_url,
    state_url_from_status_url,
)
from .const import (
    CONF_BEARER_TOKEN,
    CONF_BRIDGE_STATUS_URL,
    CONF_CRADLE_ID,
    CONF_SNAPSHOT_URL,
    CONF_STREAM_URL,
    DEFAULT_NAME,
    DEFAULT_STREAM_URL,
    DOMAIN,
)
from .coordinator import (
    BridgeApiError,
    BridgeAuthenticationError,
    BridgeIdentityError,
    async_fetch_bridge_state,
)


def _schema() -> vol.Schema:
    """Build the user and reconfigure form schema."""
    schema = vol.Schema(
        {
            vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
            vol.Required(CONF_CRADLE_ID): str,
            vol.Required(CONF_STREAM_URL, default=DEFAULT_STREAM_URL): str,
            vol.Optional(CONF_SNAPSHOT_URL): str,
            vol.Optional(CONF_BRIDGE_STATUS_URL): str,
            vol.Optional(CONF_BEARER_TOKEN): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        }
    )
    return schema


def _normalize(
    user_input: dict[str, Any],
    stored_bearer_token: str | None = None,
) -> dict[str, str]:
    """Normalize text fields and omit an empty credential."""
    data = {
        CONF_NAME: str(user_input.get(CONF_NAME, DEFAULT_NAME)).strip() or DEFAULT_NAME,
        CONF_CRADLE_ID: str(user_input.get(CONF_CRADLE_ID, "")).strip(),
        CONF_STREAM_URL: str(user_input.get(CONF_STREAM_URL, "")).strip(),
        CONF_SNAPSHOT_URL: str(user_input.get(CONF_SNAPSHOT_URL, "")).strip(),
        CONF_BRIDGE_STATUS_URL: str(user_input.get(CONF_BRIDGE_STATUS_URL, "")).strip(),
    }
    bearer_token = str(user_input.get(CONF_BEARER_TOKEN, "")).strip()
    if not bearer_token and stored_bearer_token:
        bearer_token = stored_bearer_token
    if bearer_token:
        data[CONF_BEARER_TOKEN] = bearer_token
    if not data[CONF_SNAPSHOT_URL] and data[CONF_BRIDGE_STATUS_URL]:
        data[CONF_SNAPSHOT_URL] = snapshot_url_from_status_url(
            data[CONF_BRIDGE_STATUS_URL]
        )
    return data


def _validate_urls(data: dict[str, str]) -> dict[str, str]:
    """Validate required identifiers and URL schemes before network I/O."""
    errors: dict[str, str] = {}
    if not data[CONF_CRADLE_ID]:
        errors[CONF_CRADLE_ID] = "invalid_cradle_id"
    if not is_rtsp_url(data[CONF_STREAM_URL]):
        errors[CONF_STREAM_URL] = "invalid_stream_url"
    if data[CONF_SNAPSHOT_URL] and not is_http_url(data[CONF_SNAPSHOT_URL]):
        errors[CONF_SNAPSHOT_URL] = "invalid_snapshot_url"
    if data[CONF_BRIDGE_STATUS_URL] and not is_http_url(data[CONF_BRIDGE_STATUS_URL]):
        errors[CONF_BRIDGE_STATUS_URL] = "invalid_bridge_status_url"
    return errors


class CradlewiseConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Cradlewise Local config flow."""

    VERSION = 2
    MINOR_VERSION = 1

    async def _async_validate_bridge(self, data: dict[str, str]) -> str | None:
        """Validate endpoint access and device identity when status is configured."""
        if not data[CONF_BRIDGE_STATUS_URL]:
            return None
        try:
            await async_fetch_bridge_state(
                async_get_clientsession(self.hass),
                state_url_from_status_url(data[CONF_BRIDGE_STATUS_URL]),
                data.get(CONF_BEARER_TOKEN),
                data[CONF_CRADLE_ID],
            )
        except BridgeAuthenticationError:
            return "invalid_auth"
        except BridgeIdentityError:
            return "wrong_cradle"
        except BridgeApiError:
            return "invalid_bridge_response"
        except (aiohttp.ClientError, TimeoutError):
            return "cannot_connect"
        return None

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _normalize(user_input)
            errors = _validate_urls(data)
            if not errors and (bridge_error := await self._async_validate_bridge(data)):
                errors["base"] = bridge_error
            if not errors:
                await self.async_set_unique_id(data[CONF_CRADLE_ID])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=data[CONF_NAME], data=data)

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
        """Validate and update an existing config entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _normalize(
                user_input,
                entry.data.get(CONF_BEARER_TOKEN),
            )
            errors = _validate_urls(data)
            if not errors and (bridge_error := await self._async_validate_bridge(data)):
                errors["base"] = bridge_error
            if not errors:
                await self.async_set_unique_id(data[CONF_CRADLE_ID])
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    entry,
                    title=data[CONF_NAME],
                    data_updates=data,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                _schema(),
                {
                    key: value
                    for key, value in (user_input or dict(entry.data)).items()
                    if key != CONF_BEARER_TOKEN
                },
            ),
            errors=errors,
        )
