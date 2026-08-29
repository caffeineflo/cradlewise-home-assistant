"""Constants for the Cradlewise integration."""

DOMAIN = "cradlewise"

CONF_CONNECTION_MODE = "connection_mode"
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_BABY_ID = "baby_id"
CONF_CRADLE_ID = "cradle_id"
CONF_LOCAL_HOST = "local_host"
CONF_DEVICE_ID = "device_id"
CONF_CLIENT_CERTIFICATE = "client_certificate"
CONF_CLIENT_PRIVATE_KEY = "client_private_key"
CONF_GROUP_CA_CERTIFICATE = "group_ca_certificate"
CONF_SERVER_CA_CERTIFICATE = "server_ca_certificate"
CONF_STREAM_URL = "stream_url"
CONF_SNAPSHOT_URL = "snapshot_url"
CONF_BRIDGE_STATUS_URL = "bridge_status_url"
CONF_BEARER_TOKEN = "bearer_token"
CONF_BRIDGE_API_VERSION = "bridge_api_version"
CONF_BRIDGE_VERSION = "bridge_version"

CONNECTION_MODE_AUTOMATIC = "automatic"
CONNECTION_MODE_LOCAL = "local"
CONNECTION_MODE_CLOUD = "cloud"
CONNECTION_MODES = {
    CONNECTION_MODE_AUTOMATIC,
    CONNECTION_MODE_CLOUD,
    CONNECTION_MODE_LOCAL,
}

DEFAULT_NAME = "Cradlewise"
DEVICE_STATE_MAX_AGE_SECONDS = 120
SUPPORTED_BRIDGE_API_VERSION = 1
