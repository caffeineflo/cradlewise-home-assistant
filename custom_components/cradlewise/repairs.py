"""Repairs for Cradlewise client certificate problems."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import voluptuous as vol
from cradlewise_client.certificates import (
    BrokerCertificateError,
    ClientCertificateError,
    client_certificate_validity,
)
from cradlewise_client.cloud import (
    CloudAccountClient,
    CloudApiError,
    CloudAuthenticationError,
    CradleAccount,
    ProvisionedCredentials,
)
from homeassistant.components.repairs import (
    ConfirmRepairFlow,
    RepairsFlow,
    RepairsFlowResult,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers import selector
from homeassistant.helpers.event import async_track_point_in_utc_time

from .config_flow import _credential_data, _pin_credentials
from .const import (
    CLIENT_CERTIFICATE_ISSUE_PREFIX,
    CLIENT_CERTIFICATE_WARNING_DAYS,
    CONF_CLIENT_CERTIFICATE,
    CONF_CONNECTION_MODE,
    CONF_CRADLE_ID,
    CONF_DEVICE_ID,
    CONF_LOCAL_HOST,
    CONF_REMOVE_OLD_REGISTRATION,
    CONF_SERVER_CA_CERTIFICATE,
    CONNECTION_MODE_CLOUD,
    CONNECTION_MODE_LOCAL,
    DOMAIN,
)


def _issue_id(entry: ConfigEntry) -> str:
    return f"{CLIENT_CERTIFICATE_ISSUE_PREFIX}_{entry.entry_id}"


def async_update_client_certificate_issue(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    now: datetime | None = None,
) -> datetime | None:
    """Create, update, or clear the client certificate repair issue."""
    current = now or datetime.now(timezone.utc)
    certificate_pem = entry.data.get(CONF_CLIENT_CERTIFICATE)
    translation_key: str | None = None
    placeholders: dict[str, str] | None = None
    next_update: datetime | None = None
    try:
        if not isinstance(certificate_pem, str):
            raise ClientCertificateError("client certificate is missing")
        not_before, not_after = client_certificate_validity(certificate_pem)
    except ClientCertificateError:
        translation_key = "client_certificate_invalid"
    else:
        placeholders = {"expires_at": not_after.isoformat()}
        if current < not_before:
            translation_key = "client_certificate_invalid"
            placeholders = None
            next_update = not_before
        elif current >= not_after:
            translation_key = "client_certificate_expired"
        elif current >= not_after - timedelta(days=CLIENT_CERTIFICATE_WARNING_DAYS):
            translation_key = "client_certificate_expiring"
            next_update = not_after
        else:
            next_update = not_after - timedelta(days=CLIENT_CERTIFICATE_WARNING_DAYS)

    issue_id = _issue_id(entry)
    if translation_key is None:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
    else:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            data={"entry_id": entry.entry_id},
            is_fixable=True,
            severity=(
                ir.IssueSeverity.WARNING
                if translation_key == "client_certificate_expiring"
                else ir.IssueSeverity.ERROR
            ),
            translation_key=translation_key,
            translation_placeholders=placeholders,
        )
    return next_update


def async_schedule_client_certificate_issue_updates(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> CALLBACK_TYPE:
    """Update certificate repairs at each validity boundary."""
    cancel_scheduled_update: CALLBACK_TYPE | None = None

    @callback
    def update_issue(now: datetime | None = None) -> None:
        nonlocal cancel_scheduled_update
        next_update = async_update_client_certificate_issue(hass, entry, now=now)
        cancel_scheduled_update = (
            async_track_point_in_utc_time(hass, update_issue, next_update)
            if next_update is not None
            else None
        )

    @callback
    def cancel_updates() -> None:
        nonlocal cancel_scheduled_update
        if cancel_scheduled_update is not None:
            cancel_scheduled_update()
            cancel_scheduled_update = None

    update_issue()
    return cancel_updates


def _repair_schema(email: str) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_EMAIL, default=email): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.EMAIL)
            ),
            vol.Optional(CONF_PASSWORD): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Optional(
                CONF_REMOVE_OLD_REGISTRATION,
                default=False,
            ): selector.BooleanSelector(),
        }
    )


class ClientCertificateRepairFlow(RepairsFlow):
    """Reprovision certificate material without replacing HA device identity."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> RepairsFlowResult:
        """Start certificate reprovisioning."""
        return await self.async_step_reprovision()

    async def async_step_reprovision(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> RepairsFlowResult:
        """Authenticate and atomically replace the provisioned identity."""
        errors: dict[str, str] = {}
        if user_input is not None:
            email = str(user_input.get(CONF_EMAIL, "")).strip()
            password = str(user_input.get(CONF_PASSWORD, ""))
            if not password:
                password = str(self._entry.data.get(CONF_PASSWORD, ""))
            if not email or not password:
                errors["base"] = "invalid_auth"
            else:
                try:
                    credentials, server_ca = await self.hass.async_add_executor_job(
                        self._reprovision,
                        email,
                        password,
                        bool(user_input.get(CONF_REMOVE_OLD_REGISTRATION, False)),
                    )
                except CloudAuthenticationError:
                    errors["base"] = "invalid_auth"
                except WrongCradleError:
                    errors["base"] = "wrong_cradle"
                except BrokerCertificateError:
                    errors["base"] = "cannot_connect_local"
                except ClientCertificateError:
                    errors["base"] = "invalid_certificate"
                except CloudApiError:
                    errors["base"] = "cannot_connect"
                else:
                    data = {**self._entry.data, **_credential_data(credentials)}
                    if server_ca is not None:
                        data[CONF_SERVER_CA_CERTIFICATE] = server_ca
                    if data[CONF_CONNECTION_MODE] == CONNECTION_MODE_LOCAL:
                        data.pop(CONF_EMAIL, None)
                        data.pop(CONF_PASSWORD, None)
                    else:
                        data[CONF_EMAIL] = email
                        data[CONF_PASSWORD] = password
                    self.hass.config_entries.async_update_entry(
                        self._entry,
                        data=data,
                    )
                    ir.async_delete_issue(
                        self.hass,
                        DOMAIN,
                        _issue_id(self._entry),
                    )
                    return self.async_create_entry(data={})

        return self.async_show_form(
            step_id="reprovision",
            data_schema=self.add_suggested_values_to_schema(
                _repair_schema(str(self._entry.data.get(CONF_EMAIL, ""))),
                {CONF_EMAIL: self._entry.data.get(CONF_EMAIL, "")},
            ),
            errors=errors,
        )

    def _reprovision(
        self,
        email: str,
        password: str,
        remove_old_registration: bool,
    ) -> tuple[ProvisionedCredentials, str | None]:
        cloud = CloudAccountClient(email=email, password=password)
        cloud.authenticate()
        accounts = cloud.list_accounts()
        account = next(
            (
                account
                for account in accounts
                if account.cradle_id == self._entry.data[CONF_CRADLE_ID]
            ),
            None,
        )
        if account is None:
            raise WrongCradleError("account does not contain this crib")

        credentials = cloud.provision_credentials(
            account,
            timezone=self.hass.config.time_zone,
            country=self.hass.config.country or "US",
        )
        try:
            not_before, not_after = client_certificate_validity(
                credentials.client_certificate
            )
            current = datetime.now(timezone.utc)
            if not not_before <= current < not_after:
                raise ClientCertificateError(
                    "new client certificate is not currently valid"
                )
            server_ca = self._pin_local_credentials(credentials)
            if remove_old_registration:
                self._remove_old_registration(cloud, account)
        except (BrokerCertificateError, ClientCertificateError, CloudApiError) as exc:
            self._rollback_registration(cloud, account, credentials.device_id, exc)
            raise
        return credentials, server_ca

    def _pin_local_credentials(
        self,
        credentials: ProvisionedCredentials,
    ) -> str | None:
        if self._entry.data[CONF_CONNECTION_MODE] == CONNECTION_MODE_CLOUD:
            return None
        host = str(self._entry.data.get(CONF_LOCAL_HOST, "")).strip()
        if not host:
            raise BrokerCertificateError("local crib address is missing")
        return _pin_credentials(credentials, host)

    def _remove_old_registration(
        self,
        cloud: CloudAccountClient,
        account: CradleAccount,
    ) -> None:
        old_device_id = str(self._entry.data[CONF_DEVICE_ID])
        devices = cloud.list_user_devices(account)
        if old_device_id not in {device.device_id for device in devices}:
            return
        if cloud.remove_user_devices(account, [old_device_id]) != [old_device_id]:
            raise CloudApiError(
                "Cradlewise did not confirm the old registration removal"
            )

    @staticmethod
    def _rollback_registration(
        cloud: CloudAccountClient,
        account: CradleAccount,
        device_id: str,
        original_error: Exception,
    ) -> None:
        removed = cloud.remove_user_devices(account, [device_id])
        if removed != [device_id]:
            raise CloudApiError(
                "certificate repair failed and its new registration could not be "
                "removed"
            ) from original_error


class WrongCradleError(CloudApiError):
    """Raised when repair credentials do not contain the configured crib."""


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create a client certificate repair flow."""
    if (
        issue_id.startswith(f"{CLIENT_CERTIFICATE_ISSUE_PREFIX}_")
        and data is not None
        and isinstance(entry_id := data.get("entry_id"), str)
        and (entry := hass.config_entries.async_get_entry(entry_id)) is not None
    ):
        return ClientCertificateRepairFlow(entry)
    return ConfirmRepairFlow()
