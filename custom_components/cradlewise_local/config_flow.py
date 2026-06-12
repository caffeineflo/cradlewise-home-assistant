"""Config flow for the Cradlewise Local integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME

from .config_helpers import is_http_url, is_rtsp_url, snapshot_url_from_status_url
from .const import (
    CONF_BRIDGE_STATUS_URL,
    CONF_CRADLE_ID,
    CONF_SNAPSHOT_URL,
    CONF_STREAM_URL,
    DEFAULT_NAME,
    DEFAULT_STREAM_URL,
    DOMAIN,
)


class CradlewiseConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Cradlewise Local config flow."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            cradle_id = user_input[CONF_CRADLE_ID].strip()
            stream_url = user_input[CONF_STREAM_URL].strip()
            snapshot_url = user_input.get(CONF_SNAPSHOT_URL, "").strip()
            bridge_status_url = user_input.get(CONF_BRIDGE_STATUS_URL, "").strip()

            if not is_rtsp_url(stream_url):
                errors[CONF_STREAM_URL] = "invalid_stream_url"
            if snapshot_url and not is_http_url(snapshot_url):
                errors[CONF_SNAPSHOT_URL] = "invalid_snapshot_url"
            if bridge_status_url and not is_http_url(bridge_status_url):
                errors[CONF_BRIDGE_STATUS_URL] = "invalid_bridge_status_url"

            if not errors:
                if not snapshot_url and bridge_status_url:
                    snapshot_url = snapshot_url_from_status_url(bridge_status_url)
                await self.async_set_unique_id(cradle_id)
                self._abort_if_unique_id_configured(
                    updates={
                        CONF_NAME: user_input.get(CONF_NAME, DEFAULT_NAME),
                        CONF_STREAM_URL: stream_url,
                        CONF_SNAPSHOT_URL: snapshot_url,
                        CONF_BRIDGE_STATUS_URL: bridge_status_url,
                    }
                )
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME, DEFAULT_NAME),
                    data={
                        CONF_NAME: user_input.get(CONF_NAME, DEFAULT_NAME),
                        CONF_CRADLE_ID: cradle_id,
                        CONF_STREAM_URL: stream_url,
                        CONF_SNAPSHOT_URL: snapshot_url,
                        CONF_BRIDGE_STATUS_URL: bridge_status_url,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                    vol.Required(CONF_CRADLE_ID): str,
                    vol.Required(CONF_STREAM_URL, default=DEFAULT_STREAM_URL): str,
                    vol.Optional(CONF_SNAPSHOT_URL): str,
                    vol.Optional(CONF_BRIDGE_STATUS_URL): str,
                }
            ),
            errors=errors,
        )
