"""Config and options flows for the Cradlewise integration."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import aiohttp
import voluptuous as vol
from cradlewise_client.certificates import (
    BrokerCertificateError,
    materialize_credentials,
    pin_server_ca,
)
from cradlewise_client.cloud import (
    CloudAccountClient,
    CloudApiError,
    CloudAuthenticationError,
    CloudProvisioningError,
    CradleAccount,
    ProvisionedCredentials,
)
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_EMAIL, CONF_NAME, CONF_PASSWORD
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .config_helpers import (
    bridge_base_url,
    http_url_resolves_to_private_network,
    http_url_uses_tls,
    info_url_from_status_url,
    is_http_url,
    is_rtsp_url,
    snapshot_url_from_status_url,
)
from .const import (
    CONF_ALLOW_INSECURE_HTTP,
    CONF_BABY_ID,
    CONF_BEARER_TOKEN,
    CONF_BRIDGE_API_VERSION,
    CONF_BRIDGE_STATUS_URL,
    CONF_BRIDGE_VERSION,
    CONF_CLIENT_CERTIFICATE,
    CONF_CLIENT_PRIVATE_KEY,
    CONF_CONFIRM_REGISTRATION_REMOVAL,
    CONF_CONNECTION_MODE,
    CONF_CRADLE_ID,
    CONF_DEVICE_ID,
    CONF_GROUP_CA_CERTIFICATE,
    CONF_LOCAL_HOST,
    CONF_SERVER_CA_CERTIFICATE,
    CONF_SNAPSHOT_URL,
    CONF_STREAM_URL,
    CONNECTION_MODE_AUTOMATIC,
    CONNECTION_MODE_CLOUD,
    CONNECTION_MODE_LOCAL,
    CONNECTION_MODES,
    DEFAULT_NAME,
    DOMAIN,
)
from .coordinator import (
    BridgeApiError,
    BridgeAuthenticationError,
    BridgeVersionError,
    async_fetch_bridge_info,
)


def _mode_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_CONNECTION_MODE,
                default=CONNECTION_MODE_AUTOMATIC,
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        CONNECTION_MODE_AUTOMATIC,
                        CONNECTION_MODE_LOCAL,
                        CONNECTION_MODE_CLOUD,
                    ],
                    translation_key="connection_mode",
                    mode=selector.SelectSelectorMode.LIST,
                )
            )
        }
    )


def _account_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_EMAIL): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL)
            ),
            vol.Required(CONF_PASSWORD): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        }
    )


def _reconfigure_schema(
    mode: str,
    email: str,
    local_host: str,
) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_CONNECTION_MODE, default=mode): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        CONNECTION_MODE_AUTOMATIC,
                        CONNECTION_MODE_LOCAL,
                        CONNECTION_MODE_CLOUD,
                    ],
                    translation_key="connection_mode",
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
            vol.Optional(CONF_EMAIL, default=email): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL)
            ),
            vol.Optional(CONF_PASSWORD): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Optional(CONF_LOCAL_HOST, default=local_host): str,
        }
    )


def _media_schema(
    bridge_url: str = "",
) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_BRIDGE_STATUS_URL, default=bridge_url): str,
            vol.Optional(CONF_BEARER_TOKEN): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Optional(
                CONF_ALLOW_INSECURE_HTTP,
                default=False,
            ): selector.BooleanSelector(),
        }
    )


def _registration_removal_schema(email: str) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_EMAIL, default=email): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL)
            ),
            vol.Optional(CONF_PASSWORD): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(
                CONF_CONFIRM_REGISTRATION_REMOVAL,
                default=False,
            ): selector.BooleanSelector(),
        }
    )


def _credential_data(credentials: ProvisionedCredentials) -> dict[str, Any]:
    return {
        CONF_DEVICE_ID: credentials.device_id,
        CONF_CLIENT_CERTIFICATE: credentials.client_certificate,
        CONF_CLIENT_PRIVATE_KEY: credentials.client_private_key,
        CONF_GROUP_CA_CERTIFICATE: credentials.group_ca_certificate,
    }


def _provisioned_from_data(data: dict[str, Any]) -> ProvisionedCredentials:
    return ProvisionedCredentials(
        device_id=str(data[CONF_DEVICE_ID]),
        client_certificate=str(data[CONF_CLIENT_CERTIFICATE]),
        client_private_key=str(data[CONF_CLIENT_PRIVATE_KEY]),
        group_ca_certificate=str(data[CONF_GROUP_CA_CERTIFICATE]),
    )


def _pin_credentials(credentials: ProvisionedCredentials, host: str) -> str:
    with tempfile.TemporaryDirectory(prefix="cradlewise-setup-") as path:
        directory = Path(path)
        materialized = materialize_credentials(directory, credentials)
        return pin_server_ca(
            host,
            materialized.client_cert_path,
            materialized.client_key_path,
        )


class CradlewiseConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle Cradlewise setup."""

    VERSION = 1
    MINOR_VERSION = 0

    def __init__(self) -> None:
        self._mode = CONNECTION_MODE_AUTOMATIC
        self._email = ""
        self._password = ""
        self._cloud: CloudAccountClient | None = None
        self._accounts: dict[str, CradleAccount] = {}

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the optional media companion flow."""
        return CradlewiseOptionsFlow(config_entry)

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Choose the runtime connection policy."""
        errors: dict[str, str] = {}
        if user_input is not None:
            mode = str(user_input.get(CONF_CONNECTION_MODE, ""))
            if mode in CONNECTION_MODES:
                self._mode = mode
                return await getattr(self, f"async_step_account_{mode}")()
            errors["base"] = "invalid_connection_mode"
        return self.async_show_form(
            step_id="user",
            data_schema=_mode_schema(),
            errors=errors,
        )

    async def async_step_account_automatic(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Collect credentials retained for automatic cloud fallback."""
        return await self._async_step_account("account_automatic", user_input)

    async def async_step_account_local(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Collect credentials discarded after local-only provisioning."""
        return await self._async_step_account("account_local", user_input)

    async def async_step_account_cloud(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Collect credentials retained for cloud-only operation."""
        return await self._async_step_account("account_cloud", user_input)

    async def _async_step_account(
        self,
        step_id: str,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Authenticate once for discovery and certificate provisioning."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._email = str(user_input.get(CONF_EMAIL, "")).strip()
            self._password = str(user_input.get(CONF_PASSWORD, ""))
            cloud = CloudAccountClient(
                email=self._email,
                password=self._password,
            )
            try:
                accounts = await self.hass.async_add_executor_job(
                    self._authenticate_and_list,
                    cloud,
                )
            except CloudAuthenticationError:
                errors["base"] = "invalid_auth"
            except CloudApiError:
                errors["base"] = "cannot_connect"
            else:
                if not accounts:
                    errors["base"] = "no_cradles"
                else:
                    self._cloud = cloud
                    self._accounts = {
                        account.cradle_id: account for account in accounts
                    }
                    if len(accounts) == 1:
                        return await self._async_create_account_entry(accounts[0])
                    return await self.async_step_select_cradle()

        return self.async_show_form(
            step_id=step_id,
            data_schema=_account_schema(),
            errors=errors,
        )

    async def async_step_select_cradle(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Choose one cradle when the account has more than one."""
        errors: dict[str, str] = {}
        if user_input is not None:
            cradle_id = str(user_input.get(CONF_CRADLE_ID, ""))
            account = self._accounts.get(cradle_id)
            if account is not None:
                return await self._async_create_account_entry(account)
            errors["base"] = "invalid_cradle"
        return self.async_show_form(
            step_id="select_cradle",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CRADLE_ID): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                selector.SelectOptionDict(
                                    value=account.cradle_id,
                                    label=account.name,
                                )
                                for account in self._accounts.values()
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Change connection policy without replacing device identity."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        current_mode = str(
            entry.data.get(CONF_CONNECTION_MODE, CONNECTION_MODE_AUTOMATIC)
        )
        current_email = str(entry.data.get(CONF_EMAIL, ""))
        current_host = str(entry.data.get(CONF_LOCAL_HOST, ""))
        if user_input is not None:
            validated_cloud: CloudAccountClient | None = None
            mode = str(user_input.get(CONF_CONNECTION_MODE, ""))
            email = str(user_input.get(CONF_EMAIL, "")).strip()
            password = str(user_input.get(CONF_PASSWORD, ""))
            if not password:
                password = str(entry.data.get(CONF_PASSWORD, ""))
            local_host = str(user_input.get(CONF_LOCAL_HOST, "")).strip()
            if mode not in CONNECTION_MODES:
                errors["base"] = "invalid_connection_mode"
            elif mode != CONNECTION_MODE_LOCAL and (not email or not password):
                errors["base"] = "invalid_auth"
            elif mode != CONNECTION_MODE_LOCAL:
                validated_cloud, error = await self._async_validate_existing_account(
                    email,
                    password,
                    entry.data[CONF_CRADLE_ID],
                )
                if error is not None:
                    errors["base"] = error

            if not errors and mode != CONNECTION_MODE_CLOUD and not local_host:
                if validated_cloud is None:
                    errors["base"] = "cannot_find_device"
                else:
                    try:
                        discovered_host = await self.hass.async_add_executor_job(
                            validated_cloud.get_cradle_ip,
                            entry.data[CONF_CRADLE_ID],
                        )
                    except CloudAuthenticationError:
                        errors["base"] = "invalid_auth"
                    except CloudApiError:
                        errors["base"] = "cannot_connect"
                    else:
                        if discovered_host:
                            local_host = discovered_host
                        else:
                            errors["base"] = "cannot_find_device"

            server_ca = entry.data.get(CONF_SERVER_CA_CERTIFICATE)
            if not errors and mode != CONNECTION_MODE_CLOUD:
                try:
                    server_ca = await self.hass.async_add_executor_job(
                        _pin_credentials,
                        _provisioned_from_data(dict(entry.data)),
                        local_host,
                    )
                except (BrokerCertificateError, OSError):
                    errors["base"] = "cannot_connect_local"

            if not errors:
                data = {
                    **entry.data,
                    CONF_CONNECTION_MODE: mode,
                    CONF_LOCAL_HOST: local_host,
                }
                if server_ca:
                    data[CONF_SERVER_CA_CERTIFICATE] = server_ca
                if mode == CONNECTION_MODE_LOCAL:
                    data.pop(CONF_EMAIL, None)
                    data.pop(CONF_PASSWORD, None)
                else:
                    data[CONF_EMAIL] = email
                    data[CONF_PASSWORD] = password
                return self.async_update_and_abort(
                    entry,
                    data=data,
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                _reconfigure_schema(current_mode, current_email, current_host),
                {
                    CONF_CONNECTION_MODE: current_mode,
                    CONF_EMAIL: current_email,
                    CONF_LOCAL_HOST: current_host,
                },
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self,
        entry_data: dict[str, Any],
    ) -> ConfigFlowResult:
        """Start Home Assistant's account reauthentication flow."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Validate and replace expired or changed account credentials."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            email = str(user_input.get(CONF_EMAIL, "")).strip()
            password = str(user_input.get(CONF_PASSWORD, ""))
            _, error = await self._async_validate_existing_account(
                email,
                password,
                entry.data[CONF_CRADLE_ID],
            )
            if error is None:
                return self.async_update_and_abort(
                    entry,
                    data_updates={CONF_EMAIL: email, CONF_PASSWORD: password},
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                _account_schema(),
                {CONF_EMAIL: entry.data.get(CONF_EMAIL, "")},
            ),
            errors=errors,
        )

    async def _async_validate_existing_account(
        self,
        email: str,
        password: str,
        cradle_id: str,
    ) -> tuple[CloudAccountClient | None, str | None]:
        cloud = CloudAccountClient(email=email, password=password)
        try:
            accounts = await self.hass.async_add_executor_job(
                self._authenticate_and_list,
                cloud,
            )
        except CloudAuthenticationError:
            return None, "invalid_auth"
        except CloudApiError:
            return None, "cannot_connect"
        if not any(account.cradle_id == cradle_id for account in accounts):
            return None, "wrong_cradle"
        return cloud, None

    async def _async_create_account_entry(
        self,
        account: CradleAccount,
    ) -> ConfigFlowResult:
        if self._cloud is None:
            return self.async_abort(reason="cannot_connect")
        await self.async_set_unique_id(account.cradle_id)
        self._abort_if_unique_id_configured()
        try:
            credentials, local_host = await self.hass.async_add_executor_job(
                self._provision_account,
                self._cloud,
                account,
                self.hass.config.time_zone,
                self.hass.config.country or "US",
                self._mode != CONNECTION_MODE_CLOUD,
            )
        except CloudAuthenticationError:
            return self.async_abort(reason="invalid_auth")
        except (CloudApiError, CloudProvisioningError):
            return self.async_abort(reason="cannot_connect")
        except OSError:
            return self.async_abort(reason="cannot_connect")

        server_ca = None
        if self._mode != CONNECTION_MODE_CLOUD:
            if local_host is None:
                if self._mode == CONNECTION_MODE_LOCAL:
                    return self.async_abort(reason="cannot_find_device")
            else:
                try:
                    server_ca = await self.hass.async_add_executor_job(
                        _pin_credentials,
                        credentials,
                        local_host,
                    )
                except (BrokerCertificateError, OSError):
                    if self._mode == CONNECTION_MODE_LOCAL:
                        return self.async_abort(reason="cannot_connect_local")
                    local_host = None

        data: dict[str, Any] = {
            CONF_NAME: account.name or DEFAULT_NAME,
            CONF_CONNECTION_MODE: self._mode,
            CONF_BABY_ID: account.baby_id,
            CONF_CRADLE_ID: account.cradle_id,
            **_credential_data(credentials),
        }
        if local_host:
            data[CONF_LOCAL_HOST] = local_host
        if server_ca:
            data[CONF_SERVER_CA_CERTIFICATE] = server_ca
        if self._mode in {CONNECTION_MODE_AUTOMATIC, CONNECTION_MODE_CLOUD}:
            data[CONF_EMAIL] = self._email
            data[CONF_PASSWORD] = self._password
        return self.async_create_entry(
            title=account.name or DEFAULT_NAME,
            data=data,
        )

    @staticmethod
    def _authenticate_and_list(
        cloud: CloudAccountClient,
    ) -> list[CradleAccount]:
        cloud.authenticate()
        return cloud.list_accounts()

    @staticmethod
    def _provision_account(
        cloud: CloudAccountClient,
        account: CradleAccount,
        timezone: str,
        country: str,
        discover_local: bool,
    ) -> tuple[ProvisionedCredentials, str | None]:
        credentials = cloud.provision_credentials(
            account,
            timezone=timezone,
            country=country,
        )
        local_host = cloud.get_cradle_ip(account.cradle_id) if discover_local else None
        return credentials, local_host


class CradlewiseOptionsFlow(OptionsFlow):
    """Configure media or explicitly remove a cloud device registration."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Choose an integration option."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["media", "remove_registration"],
        )

    async def async_step_media(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Validate optional bridge media endpoints."""
        current = {**self._entry.data, **self._entry.options}
        errors: dict[str, str] = {}
        if user_input is not None:
            bridge_url = bridge_base_url(
                str(user_input.get(CONF_BRIDGE_STATUS_URL, "")).strip()
            )
            if not bridge_url:
                return self.async_create_entry(title="", data={})
            if not is_http_url(bridge_url):
                errors["base"] = "invalid_bridge_status_url"
            else:
                if not http_url_uses_tls(bridge_url):
                    try:
                        is_private = await self.hass.async_add_executor_job(
                            http_url_resolves_to_private_network,
                            bridge_url,
                        )
                    except OSError:
                        errors["base"] = "cannot_connect"
                    else:
                        if not is_private:
                            errors["base"] = "insecure_public_http"
                        elif not user_input.get(CONF_ALLOW_INSECURE_HTTP, False):
                            errors["base"] = "insecure_http_requires_confirmation"
                if not errors:
                    token = str(user_input.get(CONF_BEARER_TOKEN, "")).strip()
                    if not token:
                        token = str(current.get(CONF_BEARER_TOKEN, ""))
                    data, error = await self._async_media_data(bridge_url, token)
                    if error is not None:
                        errors["base"] = error
                    elif data is not None:
                        if not http_url_uses_tls(bridge_url):
                            data[CONF_ALLOW_INSECURE_HTTP] = True
                        return self.async_create_entry(title="", data=data)

        return self.async_show_form(
            step_id="media",
            data_schema=self.add_suggested_values_to_schema(
                _media_schema(str(current.get(CONF_BRIDGE_STATUS_URL, ""))),
                {
                    CONF_BRIDGE_STATUS_URL: current.get(CONF_BRIDGE_STATUS_URL, ""),
                },
            ),
            errors=errors,
        )

    async def async_step_remove_registration(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Remove exactly this integration's cloud device registration."""
        errors: dict[str, str] = {}
        if user_input is not None:
            email = str(user_input.get(CONF_EMAIL, "")).strip()
            password = str(user_input.get(CONF_PASSWORD, ""))
            if not password:
                password = str(self._entry.data.get(CONF_PASSWORD, ""))
            if not user_input.get(CONF_CONFIRM_REGISTRATION_REMOVAL, False):
                errors["base"] = "registration_removal_not_confirmed"
            elif not email or not password:
                errors["base"] = "cleanup_invalid_auth"
            else:
                try:
                    await self.hass.async_add_executor_job(
                        self._remove_registration,
                        email,
                        password,
                    )
                except CloudAuthenticationError:
                    errors["base"] = "cleanup_invalid_auth"
                except RegistrationWrongCradleError:
                    errors["base"] = "cleanup_wrong_cradle"
                except RegistrationNotFoundError:
                    errors["base"] = "registration_not_found"
                except CloudApiError:
                    errors["base"] = "cleanup_cannot_connect"
                else:
                    await self.hass.config_entries.async_remove(self._entry.entry_id)
                    return self.async_abort(reason="registration_removed")

        return self.async_show_form(
            step_id="remove_registration",
            data_schema=self.add_suggested_values_to_schema(
                _registration_removal_schema(str(self._entry.data.get(CONF_EMAIL, ""))),
                {CONF_EMAIL: self._entry.data.get(CONF_EMAIL, "")},
            ),
            description_placeholders={
                "device_id": str(self._entry.data[CONF_DEVICE_ID])
            },
            errors=errors,
        )

    def _remove_registration(self, email: str, password: str) -> None:
        cloud = CloudAccountClient(email=email, password=password)
        cloud.authenticate()
        accounts = cloud.list_accounts()
        cradle_id = str(self._entry.data[CONF_CRADLE_ID])
        account = next(
            (account for account in accounts if account.cradle_id == cradle_id),
            None,
        )
        if account is None:
            raise RegistrationWrongCradleError("account does not contain this crib")
        device_id = str(self._entry.data[CONF_DEVICE_ID])
        if device_id not in {
            device.device_id for device in cloud.list_user_devices(account)
        }:
            raise RegistrationNotFoundError(
                "integration device registration was not found"
            )
        removed = cloud.remove_user_devices(account, [device_id])
        if removed != [device_id]:
            raise CloudApiError(
                "Cradlewise did not confirm the requested device registration removal"
            )

    async def _async_media_data(
        self,
        bridge_url: str,
        token: str,
    ) -> tuple[dict[str, Any] | None, str | None]:
        try:
            bridge = await async_fetch_bridge_info(
                async_get_clientsession(self.hass),
                info_url_from_status_url(bridge_url),
                token or None,
            )
        except BridgeAuthenticationError:
            return None, "invalid_auth"
        except BridgeVersionError:
            return None, "unsupported_bridge"
        except BridgeApiError:
            return None, "invalid_bridge_response"
        except (aiohttp.ClientError, TimeoutError):
            return None, "cannot_connect"

        cradle_id = bridge["device"]["id"].strip()
        if cradle_id != self._entry.data[CONF_CRADLE_ID]:
            return None, "wrong_cradle"
        stream_url = bridge["stream"]["url"].strip()
        if not is_rtsp_url(stream_url):
            return None, "invalid_bridge_response"
        data: dict[str, Any] = {
            CONF_BRIDGE_STATUS_URL: bridge_url,
            CONF_STREAM_URL: stream_url,
            CONF_SNAPSHOT_URL: snapshot_url_from_status_url(bridge_url),
            CONF_BRIDGE_API_VERSION: bridge["api_version"],
            CONF_BRIDGE_VERSION: str(bridge.get("bridge_version", "unknown")),
        }
        if token:
            data[CONF_BEARER_TOKEN] = token
        return data, None


class RegistrationWrongCradleError(CloudApiError):
    """Raised when cleanup credentials do not contain the configured crib."""


class RegistrationNotFoundError(CloudApiError):
    """Raised when the configured device registration is already absent."""
