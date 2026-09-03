# cradlewise-client

`cradlewise-client` is the media-free protocol layer used by the Cradlewise
Home Assistant integration. It supports direct local MQTT, Cradlewise AWS IoT
MQTT, account discovery, certificate provisioning, local broker pinning,
client-certificate validity inspection, targeted device-registration cleanup,
state normalization, and validated control payloads.

The package is unofficial and based on interoperability research against the
Cradlewise Android app. It does not start WebRTC sessions, process nursery
audio or video, or require Home Assistant.

This package is pre-release. Its public API can change before 1.0.
