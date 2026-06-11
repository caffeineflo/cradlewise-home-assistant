# MQTT Topics & Device Shadow

**App version:** 2.55.5

## Connection Types

The app maintains two MQTT connections:

| Type | Broker | Port | Auth |
|------|--------|------|------|
| Local | `ssl://{crib_local_ip}:8883` | 8883 | Mutual TLS (X.509 client certs) |
| Remote | `a2bby18smixe1f-ats.iot.us-east-1.amazonaws.com` | 8883 | AWS IoT device certificates |

### Connection Parameters

| Parameter | Local | Remote |
|-----------|-------|--------|
| Clean session | false | -- |
| Connection timeout | 2s | -- |
| Keep-alive interval | 5s | 5s |
| Auto-reconnect | manual | false (manual) |
| QoS | 0 | 0 |
| Max retries | 3 | -- |

## Topics

### AWS IoT Shadow (Remote)

| Topic | Direction | Description |
|-------|-----------|-------------|
| `$aws/things/{cradleId}/shadow/update` | Publish | Send desired state changes |
| `$aws/things/{cradleId}/shadow/update/accepted` | Subscribe | Confirmation of accepted updates |
| `$aws/things/{cradleId}/shadow/update/rejected` | Subscribe | Rejection notifications |
| `$aws/things/{cradleId}/shadow/get` | Publish | Request current shadow document |
| `$aws/things/{cradleId}/shadow/get/accepted` | Subscribe | Receive shadow document |
| `$aws/things/{cradleId}/shadow/get/rejected` | Subscribe | Shadow get rejection |

### Cradle State & Monitoring

| Topic | Direction | Description |
|-------|-----------|-------------|
| `/{cradleId}/beacon` | Subscribe | Heartbeat/beacon messages |
| `/cradle/{cradleId}/cradle_state` | Subscribe | Detailed cradle state updates |
| `/{cradleId}/room` | Pub/Sub | WebRTC signaling (local video) |

### Firmware Updates

| Topic | Direction | Description |
|-------|-----------|-------------|
| `/{cradleId}/update_request/new` | Subscribe | New firmware update available |
| `/{cradleId}/update_request/progress` | Subscribe | Update progress notifications |
| `/{cradleId}/update_request/succeeded` | Subscribe | Update completed successfully |
| `/{cradleId}/update_request/failed` | Subscribe | Update failed |

### Remote Video (Janus)

| Topic | Direction | Description |
|-------|-----------|-------------|
| `/janus-server/{ip}/to-janus` | Publish | Send video requests to Janus |
| `/janus-server/{ip}/from-janus` | Subscribe | Receive video responses from Janus |

Current Janus server IP: `34.226.215.23`

## Device Shadow Structure

```json
{
  "id": "<cradleId>",
  "state": {
    "state": 1,
    "expectedResumeTime": 0.0,
    "info": {
      "opMode": 0,
      "status": {
        "cradle": { /* ServiceState */ },
        "updateAgent": { /* ServiceState */ },
        "connectivityReporter": { /* ServiceState */ }
      }
    }
  },
  "info": {
    "upSince": 1700000000.0,
    "nextMaintenance": 1700100000.0,
    "connectivity": {
      "ssid": "MyWiFiNetwork",
      "strength": -45,
      "frequency": 5180,
      "localIP": "192.0.2.10"
    }
  }
}
```

### Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `id` | String | Cradle identifier |
| `state.state` | Int | 1 = Online/Active |
| `state.expectedResumeTime` | Float | Timestamp for expected resume |
| `state.info.opMode` | Int | Operating mode |
| `state.info.status` | Object | Service states (cradle, updateAgent, connectivityReporter) |
| `info.upSince` | Double | Epoch timestamp when device came online |
| `info.nextMaintenance` | Double | Scheduled maintenance timestamp |
| `info.connectivity.ssid` | String | Connected WiFi network name |
| `info.connectivity.strength` | Integer | WiFi signal strength (dBm) |
| `info.connectivity.frequency` | Integer | WiFi frequency (MHz) |
| `info.connectivity.localIP` | String | Device's local IP address |

## Connection Priority

1. App attempts **local MQTT** first when on WiFi
2. Falls back to **remote MQTT** (AWS IoT) if local fails
3. `MqttManager` coordinates switching between connections
4. Cached IPs stored via `MqttRepository.saveIp(cradleId, ip)` for faster reconnection

## Source Files

- `com/cradlewise/nini/core/mqtt/MqttManager.java`
- `com/cradlewise/nini/core/mqtt/local/LocalMqttConnectionV2.java`
- `com/cradlewise/nini/core/mqtt/remote/RemoteMqttConnectionV2.java`
- `com/cradlewise/nini/core/mqtt/utils/Topics.java`
- `com/cradlewise/nini/core/mqtt/utils/MqttConstantsV2Kt.java`
- `com/cradlewise/nini/core/mqtt/api/model/Connectivity.java`
- `com/cradlewise/nini/core/mqtt/api/model/CradleStateMessage.java`
