# Device Discovery Protocol

**App version:** 2.55.5
**Protocol:** Custom UDP broadcast + TCP callback
**UDP port:** 5055

## Overview

The app discovers the Cradlewise crib on the local network using a custom UDP broadcast protocol. This is not mDNS/Bonjour -- it's a proprietary mechanism.

## Discovery Flow

```
App                                Network                           Crib
 |                                    |                               |
 |-- open TCP server (port 10000-60000)                               |
 |                                    |                               |
 |-- UDP broadcast to :5055 --------->|------------------------------>|
 |   {"cradlewise_mobile_port":"X",   |                               |
 |    "device_id":"Y"}                |                               |
 |                                    |                               |
 |<----- TCP connect to port X -------|-------------------------------|
 |   (crib sends its IP address)      |                               |
 |                                    |                               |
 |-- close TCP server                 |                               |
```

## Broadcast Message

Sent as UDP broadcast to the network broadcast address on port **5055**.

```json
{
  "cradlewise_mobile_port": "<tcp_server_port>",
  "device_id": "<mobile_device_id>"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `cradlewise_mobile_port` | String | Random TCP port (10000-60000) the app is listening on |
| `device_id` | String | Mobile device identifier |

## Broadcast Address Calculation

The app calculates the broadcast address from Android's `DhcpInfo`:

```
broadcast = (dhcp.ipAddress & dhcp.netmask) | ~dhcp.netmask
```

This derives the standard broadcast address for the current subnet.

## TCP Response

After receiving the UDP broadcast, the crib connects back to the app's TCP server socket and sends its local IP address. The app validates the response against its known cradle list.

## Retry Logic

| Parameter | Value |
|-----------|-------|
| Max retry attempts | 3 |
| Broadcasts per attempt | 5 |
| TCP server socket timeout | 1000ms |
| Backoff base duration | 30s |
| Backoff formula | `base * 2^attempt` |
| Max backoff | 30 minutes (1,800,000ms) |

## IP Caching

Discovered IPs are cached locally via `MqttRepository`:

- `saveIp(cradleId, ip)` -- stores IP after successful discovery
- `getSavedIp(cradleId)` -- retrieves cached IP for faster reconnection

On subsequent connections, the app tries the cached IP first before falling back to UDP discovery.

## Alternative IP Source

The crib's local IP is also available in the MQTT device shadow at `info.connectivity.localIP`. The app can obtain this via the remote MQTT connection if local discovery fails.

## Error Types

| Error | Description |
|-------|-------------|
| `DISCOVERY_FAILED` | UDP broadcast got no response |
| `SERVER_IP_UNAVAILABLE` | No IP returned from discovery |
| `ALL_IPS_FAILED` | All cached + discovered IPs exhausted |
| `HOST_UNREACHABLE` | IP found but host not reachable |
| `NETWORK_UNREACHABLE` | No network connectivity |
| `CONNECTION_TIMEOUT` | MQTT connection to discovered IP timed out |

## Source Files

- `com/cradlewise/nini/core/mqtt/local/UdpBroadcasterV2.java`
- `com/cradlewise/nini/core/mqtt/local/CradleLocalDiscoveryMonitorV2.java`
- `com/cradlewise/nini/core/mqtt/local/LocalMqttConnectionV2.java`
- `com/cradlewise/nini/core/mqtt/local/LocalMqttError.java`
- `com/cradlewise/nini/core/mqtt/local/LocalMqttErrorType.java`
- `com/cradlewise/nini/core/mqtt/MqttRepository.java`
