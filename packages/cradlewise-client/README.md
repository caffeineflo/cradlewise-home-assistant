# cradlewise-client

`cradlewise-client` is the media-free protocol layer used by the Cradlewise
Home Assistant integration. It supports direct local MQTT, Cradlewise AWS IoT
MQTT, account discovery, certificate provisioning, local broker pinning,
client-certificate validity inspection, targeted device-registration cleanup,
state normalization, and validated control payloads.

Direct local MQTT requires a broker CA validated and pinned with
`pin_server_ca`; the client doesn't disable TLS hostname verification when a
pin is missing.

Canceling startup or calling `async_stop()` waits for an in-flight connection
worker, then disconnects its final socket. Concurrent stop calls share that
cleanup; a replacement cannot start while it is pending. Cancellation does not
kill a blocking system resolver or TLS call, so shutdown can wait for that
operation's timeout instead of reporting success while it still owns a socket.

The package is unofficial and based on interoperability research against the
Cradlewise Android app. It does not start WebRTC sessions, process nursery
audio or video, or require Home Assistant.

This package is pre-release. Its public API can change before 1.0.
