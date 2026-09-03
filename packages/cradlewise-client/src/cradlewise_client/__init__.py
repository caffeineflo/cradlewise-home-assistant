"""Lightweight clients for Cradlewise local and cloud transports."""

from .certificates import (
    BrokerCertificateError,
    ClientCertificateError,
    client_certificate_validity,
    materialize_credentials,
    pin_server_ca,
    validate_server_chain,
)
from .cloud import (
    CloudAccountClient,
    CloudApiError,
    CloudAuthenticationError,
    CloudProvisioningError,
    CradleAccount,
    ProvisionedCredentials,
    UserDevice,
)
from .commands import (
    CommandError,
    CommandUnavailable,
    CradlewiseCommandHandler,
    build_desired,
    shadow_payload,
)
from .local import (
    LocalConnectionError,
    LocalCradleClient,
    LocalCradleUpdate,
    LocalCredentials,
)
from .remote import REMOTE_MQTT_ENDPOINT, RemoteCradleClient
from .state import CradlewiseStateStore, normalize_device_state

__all__ = [
    "CommandError",
    "CommandUnavailable",
    "CloudAccountClient",
    "CloudApiError",
    "CloudAuthenticationError",
    "CloudProvisioningError",
    "BrokerCertificateError",
    "ClientCertificateError",
    "CradleAccount",
    "CradlewiseCommandHandler",
    "LocalConnectionError",
    "LocalCradleClient",
    "LocalCradleUpdate",
    "LocalCredentials",
    "REMOTE_MQTT_ENDPOINT",
    "RemoteCradleClient",
    "ProvisionedCredentials",
    "UserDevice",
    "CradlewiseStateStore",
    "normalize_device_state",
    "materialize_credentials",
    "client_certificate_validity",
    "pin_server_ca",
    "build_desired",
    "shadow_payload",
    "validate_server_chain",
]
