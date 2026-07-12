# Community Implementations

This project was shaped by existing Cradlewise community work.

- [`jlamendo/ha-cradlewise`](https://github.com/jlamendo/ha-cradlewise) provides a Home Assistant integration for Cradlewise cloud/API state, analytics, sensors, and binary sensors.
- [`jlamendo/pycradlewise`](https://pypi.org/project/pycradlewise/) provides the async Python REST/AWS IoT client used by that integration.
- [`imaznation/cradlewise-bridge`](https://github.com/imaznation/cradlewise-bridge) explores Cradlewise video/audio through cloud Janus WebRTC.
- [`Cradlewise-Org/cradlewise-api`](https://github.com/Cradlewise-Org/cradlewise-api) documents the official read-only REST API for Nurture Plus beta tokens.

The bridge in this repo takes a different first path: it uses local Greengrass
MQTT/WebRTC for camera audio/video, device state, and controls. Optional cloud
polling is a lower-priority fallback for fields absent from a local update; it
is not required to create the mapped Home Assistant entities.
