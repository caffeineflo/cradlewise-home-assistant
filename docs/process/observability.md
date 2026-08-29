# Private Observability

The optional Cradlewise media companion exposes standard observability hooks without selecting or
operating a monitoring backend for the consumer. All outbound reporting is off
by default.

## Defaults

- Bridge logs stay on stdout for Docker or the service supervisor to collect.
- `/live` reports API-process liveness so Docker and reverse proxies keep state
  and control routes available during a media outage.
- `/health` reports semantic bridge health. Loopback container probes do not
  need credentials; remote monitors must send the bridge bearer token.
- `/metrics` returns 404 unless `CRADLEWISE_METRICS_ENABLED=true`.
- Error reporting does not import or initialize the Sentry SDK unless a DSN is
  explicitly configured.
- Cloud polling and observability are independent. Enabling either one does not
  enable the other.

The repository ships no hosted telemetry destination, anonymous installation
identifier, metrics database, visualization layer, or maintainer-controlled
DSN.

## Health monitoring

Use `GET /health` with the same bearer token used by Home Assistant:

```text
Authorization: Bearer <CRADLEWISE_STATUS_TOKEN>
```

HTTP 200 means MQTT, WebRTC, recent video, and the active RTSP sink are healthy.
HTTP 503 means the API is reachable but one of those semantic checks is failing.
This works with Uptime Kuma or any monitor that can attach an HTTP header.

Use `GET /live` only for process and container routing checks. It returns HTTP
200 while the API server is responding and does not imply that media is healthy.

## Pull metrics

Enable metrics explicitly:

```text
CRADLEWISE_METRICS_ENABLED=true
```

Then configure any Prometheus-compatible scraper to request `/metrics` with the
bridge bearer token. The endpoint is pull-only and has no labels. It contains
only operational values such as health, uptime, reconnects, connection state,
frame counters, media freshness, sink drops, and state freshness.

The endpoint never exposes cradle IDs, crib or bridge addresses, account data,
Wi-Fi details, baby state, sleep values, MQTT topics, URLs, tokens, or stream
credentials.

## Consumer-owned error reporting

The official bridge image includes the optional Sentry-compatible client, but
it remains inactive unless one of these is set:

```text
CRADLEWISE_ERROR_REPORTING_DSN=https://public-key@errors.example/project
CRADLEWISE_ERROR_REPORTING_ENVIRONMENT=production
```

For a mounted secret, use
`CRADLEWISE_ERROR_REPORTING_DSN_FILE=/run/secrets/cradlewise_error_reporting_dsn`
and leave the direct DSN empty. Bugsink, GlitchTip, Sentry, or another
Sentry-protocol implementation can be used.

Only an unexpected fatal process exception is captured. Normal crib outages,
MQTT reconnects, WebRTC recovery, stale media restarts, and FFmpeg recovery stay
in local logs and metrics. Reporting disables PII, tracing, profiling, request
data, user data, breadcrumbs, source context, and local variables. A final
event scrub removes email addresses, IP addresses, URLs, and UUIDs.

With no DSN, no error-reporting connection is attempted.

## Home Assistant diagnostics

Home Assistant diagnostics are generated only when a user manually downloads
them. The integration redacts account credentials, device certificate
material, the bearer token, bridge and stream URLs, cradle ID, device ID, and
snapshot URL. It includes versions, provider health, reconnect and frame
counters, and data freshness, but not raw nursery or baby state.
