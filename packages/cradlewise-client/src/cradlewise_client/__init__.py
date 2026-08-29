"""Lightweight clients for Cradlewise local and cloud transports."""

from .certificates import (
    BrokerCertificateError,
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
    "CradleAccount",
    "CradlewiseCommandHandler",
    "LocalConnectionError",
    "LocalCradleClient",
    "LocalCradleUpdate",
    "LocalCredentials",
    "REMOTE_MQTT_ENDPOINT",
    "RemoteCradleClient",
    "ProvisionedCredentials",
    "CradlewiseStateStore",
    "normalize_device_state",
    "materialize_credentials",
    "pin_server_ca",
    "build_desired",
    "shadow_payload",
    "validate_server_chain",
]
