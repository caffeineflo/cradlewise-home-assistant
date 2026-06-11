import json

from cradlewise_local.status import BridgeStatusStore


def test_status_store_tracks_media_and_connection_state():
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")

    store.set_mqtt_connected(True)
    store.set_webrtc_state("connecting")
    store.set_ice_state("checking")
    store.set_video_resolution(1280, 720)
    store.increment_video_frames()
    store.mark_audio_track()

    snapshot = store.snapshot()

    assert snapshot["bridge"]["healthy"] is True
    assert snapshot["mqtt"]["connected"] is True
    assert snapshot["webrtc"]["connection_state"] == "connecting"
    assert snapshot["media"]["video_frames"] == 1
    assert snapshot["media"]["audio_track"] is True
    assert snapshot["media"]["resolution"] == "1280x720"


def test_status_store_captures_cradle_state_and_beacon_payloads():
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
    cradle_state = {
        "id": "cradle-1",
        "state": {
            "state": 1,
            "expectedResumeTime": 0,
            "info": {
                "opMode": 2,
                "status": {
                    "cradle": {"state": "running"},
                    "updateAgent": {"state": "idle"},
                },
            },
        },
        "info": {
            "connectivity": {
                "ssid": "Nursery",
                "strength": -48,
                "frequency": 5180,
                "localIP": "192.0.2.10",
            },
        },
    }
    beacon = {"state": "alive"}

    store.update_cradle_state(cradle_state)
    store.update_beacon(beacon)

    snapshot = store.snapshot()

    assert snapshot["cradle_state"]["raw"] == cradle_state
    assert snapshot["cradle_state"]["state"] == 1
    assert snapshot["cradle_state"]["op_mode"] == 2
    assert snapshot["cradle_state"]["wifi_strength"] == -48
    assert snapshot["cradle_state"]["local_ip"] == "192.0.2.10"
    assert snapshot["beacon"]["raw"] == beacon


def test_status_store_maps_rich_shadow_state():
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
    store.update_cradle_state(
        {
            "state": {
                "reported": {
                    "babyPresent": True,
                    "babySleepState": "sleeping",
                    "babySleepPhaseV2": {"eventValue": 4},
                    "babyNeedsAttention": False,
                    "babyNeedsHelp": False,
                    "isCribHelping": True,
                    "loudSoundDetected": False,
                    "insideSleepSchedule": True,
                    "insideSoothingWindow": True,
                    "rockingNotEffective": False,
                    "mode": "Crib",
                    "bounceMode": "auto",
                    "bounceSetting": "medium",
                    "responsivitySetting": "normal",
                    "actuator": {"on": True, "amplitude": 3.7},
                    "musicMode": "lullaby",
                    "music": {"play": True, "volume": 5.0, "mood": "calm"},
                    "light": {"lightOn": True, "lightIntensity": 40.0},
                    "deviceStatus": {
                        "batteryLife": 87.0,
                        "charging": True,
                        "supplyRemoved": False,
                    },
                    "sleepTime": "2026-03-16T00:30:00Z",
                    "wakeUpTime": "2026-03-16T12:00:00Z",
                }
            }
        }
    )

    device_state = store.snapshot()["device_state"]

    assert device_state["baby_present"] is True
    assert device_state["sleep_phase"] == "sleep"
    assert device_state["bounce_amplitude"] == 3
    assert device_state["bouncing"] is True
    assert device_state["music_playing"] is True
    assert device_state["music_volume"] == 5
    assert device_state["light_on"] is True
    assert device_state["light_intensity"] == 40
    assert device_state["battery_life"] == 87
    assert device_state["charging"] is True
    assert device_state["power_supply_removed"] is False
    assert device_state["source"] == "local_mqtt"


def test_status_store_keeps_cloud_device_state_when_local_state_is_sparse():
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")

    store.update_device_state({"babyPresent": True}, source="cloud")
    store.update_cradle_state({"state": {"state": 1}})

    snapshot = store.snapshot()

    assert snapshot["cradle_state"]["state"] == 1
    assert snapshot["device_state"]["baby_present"] is True
    assert snapshot["device_state"]["source"] == "cloud"


def test_status_store_maps_live_cloud_state_shape():
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
    store.update_device_state(
        {
            "baby_present": True,
            "baby_sleep_state": "asleep",
            "bounce_setting": 2,
            "responsivity_setting": 3,
            "actuator": {"on": False, "amplitude": 1},
            "soundSynth": {"play": True, "trackName": "rain", "volume": 4},
            "rawShadow": {
                "babySleepPhaseV2": {"eventValue": 4},
                "bounceMode": 1,
                "musicMode": 2,
                "light": {"indicatorBrightness": 30},
                "detectedCradleMode": "Crib",
            },
        },
        source="cloud",
    )

    device_state = store.snapshot()["device_state"]

    assert device_state["baby_present"] is True
    assert device_state["sleep_state"] == "asleep"
    assert device_state["sleep_phase"] == "sleep"
    assert device_state["bouncing"] is False
    assert device_state["bounce_setting"] == 2
    assert device_state["bounce_mode"] == 1
    assert device_state["responsivity_setting"] == 3
    assert device_state["music_mode"] == 2
    assert device_state["music_playing"] is True
    assert device_state["music_volume"] == 4
    assert device_state["music_mood"] == "rain"
    assert device_state["light_intensity"] == 30
    assert device_state["cradle_mode"] == "Crib"


def test_status_store_returns_json_bytes():
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")

    payload = json.loads(store.to_json_bytes())

    assert payload["bridge"]["cradle_id"] == "cradle-1"
