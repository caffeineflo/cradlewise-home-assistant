import json
import socket
import urllib.error
import urllib.request

import pytest

from cradlewise_local.status import (
    BridgeStatusHttpServer,
    BridgeStatusStore,
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


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


def test_status_store_marks_bridge_unhealthy_when_sink_stops_writing(monkeypatch):
    now = 1000.0
    monkeypatch.setattr("cradlewise_local.status._now", lambda: now)
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
    store.set_mqtt_connected(True)
    store.increment_video_frames()
    store.update_sink_health(
        {
            "started": True,
            "healthy": True,
            "error": None,
            "last_video_write_at": now,
            "last_audio_write_at": None,
        }
    )

    now = 1031.0
    snapshot = store.snapshot()

    assert snapshot["sink"]["process_healthy"] is True
    assert snapshot["sink"]["healthy"] is False
    assert snapshot["bridge"]["healthy"] is False


def test_connection_attempt_clears_stale_local_media_state():
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
    store.set_mqtt_connected(True)
    store.mark_stream_started()
    store.increment_video_frames()
    store.increment_audio_frames()
    store.update_snapshot(b"jpeg")

    store.begin_connection_attempt()
    snapshot = store.snapshot()

    assert (
        snapshot["mqtt"]["connected"],
        snapshot["media"]["video_frames"],
        snapshot["media"]["audio_frames"],
        store.snapshot_jpeg(),
    ) == (False, 0, 0, None)


def test_reconnect_error_is_exposed_and_cleared_by_video():
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
    store.mark_reconnecting("TLS failed")

    failed = store.snapshot()["bridge"]
    store.increment_video_frames()
    recovered = store.snapshot()["bridge"]

    assert (
        failed["last_error"],
        failed["reconnect_attempts"],
        recovered["last_error"],
    ) == ("TLS failed", 1, None)


def test_status_store_caches_latest_snapshot_jpeg():
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
    jpeg = b"\xff\xd8frame\xff\xd9"

    store.update_snapshot(jpeg)

    assert store.snapshot_jpeg() == jpeg
    assert store.snapshot()["media"]["last_snapshot_at"] is not None


def test_status_store_has_no_false_defaults_before_first_device_state():
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")

    device_state = store.snapshot()["device_state"]

    assert device_state["baby_needs_attention"] is None
    assert device_state["light_on"] is None
    assert device_state["volume_profile"] is None
    assert device_state["available"] is False


def test_status_store_merges_partial_updates_per_source():
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
    store.update_device_state(
        {"babyPresent": True, "actuator": {"duration": 15}}, source="cloud"
    )
    store.update_device_state(
        {"state": {"reported": {"actuator": {"on": True}}}},
        source="local_shadow",
    )
    store.update_device_state(
        {"state": {"reported": {"actuator": {"amplitude": 4}}}},
        source="local_shadow",
    )

    device_state = store.snapshot()["device_state"]

    assert device_state["baby_present"] is True
    assert device_state["bounce_duration"] == 15
    assert device_state["bouncing"] is True
    assert device_state["bounce_amplitude"] == 4
    assert device_state["source"] == "local_shadow"
    assert set(device_state["sources"]) == {"cloud", "local_shadow"}


def test_status_store_marks_source_state_stale(monkeypatch):
    now = 1000.0
    monkeypatch.setattr("cradlewise_local.status._now", lambda: now)
    store = BridgeStatusStore(
        cradle_id="cradle-1",
        crib_ip="192.0.2.10",
        cloud_state_stale_after=1,
    )
    store.update_device_state({"babyPresent": True}, source="cloud")

    now = 1002.0
    device_state = store.snapshot()["device_state"]

    assert device_state["baby_present"] is True
    assert device_state["available"] is False
    assert device_state["stale"] is True
    assert device_state["sources"]["cloud"]["stale"] is True


def test_status_store_does_not_treat_numeric_sentinel_as_true():
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
    store.update_device_state({"babyPresent": -1, "bounceLevel": True}, source="cloud")

    device_state = store.snapshot()["device_state"]

    assert device_state["baby_present"] is None
    assert device_state["bounce_level"] is None


def test_status_store_reports_source_error_before_first_state():
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
    store.mark_device_state_error("cloud", "request timed out")

    device_state = store.snapshot()["device_state"]

    assert device_state["available"] is False
    assert device_state["sources"]["cloud"]["stale"] is True
    assert device_state["sources"]["cloud"]["error"] == "request timed out"


def test_status_store_tracks_official_sleep_analytics(monkeypatch):
    now = 1000.0
    monkeypatch.setattr("cradlewise_local.status._now", lambda: now)
    store = BridgeStatusStore(
        cradle_id="cradle-1",
        crib_ip="192.0.2.10",
        analytics_stale_after=900,
    )
    store.update_sleep_analytics(
        {
            "date": "2026-03-10",
            "timezone": "America/New_York",
            "total_sleep_today": 120,
        }
    )

    analytics = store.snapshot()["analytics"]

    assert analytics["available"] is True
    assert analytics["total_sleep_today"] == 120


def test_status_store_marks_official_sleep_analytics_stale(monkeypatch):
    now = 1000.0
    monkeypatch.setattr("cradlewise_local.status._now", lambda: now)
    store = BridgeStatusStore(
        cradle_id="cradle-1",
        crib_ip="192.0.2.10",
        analytics_stale_after=1,
    )
    store.update_sleep_analytics({"total_sleep_today": 120})

    now = 1002.0

    assert store.snapshot()["analytics"]["available"] is False


def test_status_http_server_serves_cached_snapshot_jpeg():
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
    server = BridgeStatusHttpServer(store, "127.0.0.1", _free_port())
    server.start()

    try:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{server.port}/snapshot.jpg",
                timeout=2,
            ) as response:
                raise AssertionError(f"expected HTTP 404, got {response.status}")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404

        store.update_snapshot(b"\xff\xd8frame\xff\xd9")

        with urllib.request.urlopen(
            f"http://127.0.0.1:{server.port}/snapshot.jpg",
            timeout=2,
        ) as response:
            assert response.status == 200
            assert response.headers["Content-Type"] == "image/jpeg"
            assert response.read() == b"\xff\xd8frame\xff\xd9"
    finally:
        server.close()


def test_status_http_server_requires_bearer_token_for_state():
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
    server = BridgeStatusHttpServer(
        store, "127.0.0.1", _free_port(), bearer_token="secret"
    )
    server.start()

    try:
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"http://127.0.0.1:{server.port}/state", timeout=2)
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.port}/state",
            headers={"Authorization": "Bearer secret"},
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            assert response.status == 200
    finally:
        server.close()

    assert exc_info.value.code == 401


def test_health_is_unauthenticated_and_returns_503_until_healthy():
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
    server = BridgeStatusHttpServer(
        store, "127.0.0.1", _free_port(), bearer_token="secret"
    )
    server.start()

    try:
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"http://127.0.0.1:{server.port}/health", timeout=2)
        store.set_mqtt_connected(True)
        store.increment_video_frames()
        with urllib.request.urlopen(
            f"http://127.0.0.1:{server.port}/health", timeout=2
        ) as response:
            assert response.status == 200
    finally:
        server.close()

    assert exc_info.value.code == 503


def test_status_http_server_rejects_stale_snapshot(monkeypatch):
    now = 1000.0
    monkeypatch.setattr("cradlewise_local.status._now", lambda: now)
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
    store.update_snapshot(b"\xff\xd8frame\xff\xd9")
    server = BridgeStatusHttpServer(
        store,
        "127.0.0.1",
        _free_port(),
        snapshot_max_age_seconds=1,
    )
    server.start()

    now = 1002.0
    try:
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(
                f"http://127.0.0.1:{server.port}/snapshot.jpg", timeout=2
            )
    finally:
        server.close()

    assert exc_info.value.code == 503


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
                    "bounceLevel": 2,
                    "bounceSetting": "medium",
                    "responsivitySetting": "normal",
                    "actuator": {"on": True, "amplitude": 3.7},
                    "musicMode": "lullaby",
                    "musicLevel": 3,
                    "music": {"play": True, "volume": 5.0, "mood": "calm"},
                    "volumeProfile": "normal",
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
    assert device_state["bounce_level"] == 2
    assert device_state["bouncing"] is True
    assert device_state["music_playing"] is True
    assert device_state["music_volume"] == 5
    assert device_state["music_level"] == 3
    assert device_state["light_on"] is True
    assert device_state["light_intensity"] == 40
    assert device_state["volume_profile"] == "normal"
    assert device_state["battery_life"] == 87
    assert device_state["charging"] is True
    assert device_state["power_supply_removed"] is False
    assert device_state["source"] == "local_mqtt"


@pytest.mark.parametrize(
    ("raw_state", "expected"),
    [
        (0, "Baby not present"),
        (2, "Active Awake"),
        (3, "Quite Awake"),
        (4, "Light sleep"),
        (5, "Deep sleep"),
        (1, "unknown (1)"),
    ],
)
def test_status_store_maps_local_sleep_state_values(raw_state, expected):
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")

    store.update_device_state(
        {"state": {"reported": {"babySleepState": raw_state}}},
        source="local_shadow",
    )

    assert store.snapshot()["device_state"]["sleep_state"] == expected


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
                "actuator": {
                    "accFramePeaksThreshold": 10,
                    "bounceAlwaysOn": False,
                    "bounceAlwaysOnIntensity": 3,
                    "bounceSuperGentle": False,
                    "disableBouncing": True,
                    "duration": 15,
                    "durationLimit": 30,
                    "movementEnergyThreshold": 50,
                    "pushGestureEnable": True,
                    "quiescentBounce": False,
                    "tapDetectionEnable": True,
                    "tiltState": 0,
                    "timeRemaining": 0,
                },
                "appSettings": {"flipVideo": False},
                "autoModeLockDuration": 10,
                "babySleepPhaseV2": {
                    "durationStartTime": "2026-06-24 01:08:31.968945",
                    "eventStartTime": "2026-06-24 02:10:31.856625",
                    "eventValue": 4,
                    "presentToggleTime": "2026-06-24 01:08:20.242141",
                },
                "babySleepState": 5,
                "babySleepStateInternal": 0,
                "babySleepStateBeingDetermined": False,
                "babyPresenceBeingDetermined": False,
                "babyPresentPrev": True,
                "babyMonitor": {
                    "breath": {
                        "finalRate": -1,
                        "rate": -1,
                        "reason": -1,
                        "state": 0,
                    },
                    "breathTrigger": False,
                    "lowerBreathRateAlert": False,
                },
                "bluetooth": {
                    "wifiStats": json.dumps(
                        {
                            "ARPSuccessCount": 870870,
                            "BeaconLossCount": 1,
                            "bitrate": 72200000,
                            "noise": -85,
                            "rssi0": -50,
                            "rssi1": -44,
                            "ssid": "Nursery",
                            "strength": 77,
                        }
                    )
                },
                "bounceMode": 1,
                "bounceLevel": 4,
                "calibrateCradle": 0,
                "calibrationHistory": {
                    "complete": "success",
                    "gainSetup": "success",
                    "micSetup": "success",
                    "noiseProfileSetup": "success",
                    "tofCalibration": "success",
                    "weightCalibration": "success",
                },
                "calibrationStatus": {"stage": "", "status": ""},
                "calibrationType": 1,
                "connectivity": {
                    "wifiScore": {
                        "Jitter": 3,
                        "Loss": 3,
                        "SNR": 3,
                        "Speed": 3,
                        "WiFi": 3,
                    }
                },
                "control": {
                    "adaptiveSoothingEnabled": False,
                    "bnaAlertControl": 8,
                    "breathEnabled": True,
                    "crySensitivity": 1,
                    "cssResponsiveness": "low",
                    "videoServiceBitMask": 0,
                },
                "deviceStatus": {
                    "ambientTemp": 23750,
                    "uptimeService": 35997.596906,
                    "uptimeTotal": 36006.22,
                },
                "deployState": 4,
                "musicMode": 2,
                "musicLevel": 5,
                "musicDuration": 60,
                "musicTimeRemaining": -1,
                "operationState": 9,
                "lullabies": {
                    "action": 1,
                    "curSongId": "hpx4mmji",
                    "desiredPlaylistId": "bfalhqi6",
                    "desiredSongId": "",
                    "elapsedTime": 0,
                    "enableMusic": False,
                    "loop": "all",
                    "timerDuration": 30,
                    "timerOn": False,
                    "volume": 45,
                },
                "maxBounceLimit": 55,
                "maxSoundPreview": False,
                "maxVolumeLimit": 45,
                "meta": {
                    "babyProfileLastUpdatedTime": "2025-03-24 20:49:01.573754",
                    "rootfs_version": "6.25",
                    "shadow_version": 1,
                    "software_version": "0.2.72",
                    "timezone": "America/New_York",
                },
                "light": {"indicatorBrightness": 30},
                "detectedCradleMode": "Crib",
                "obstructionToFDetected": False,
                "userActionForObstruction": "",
                "volumeProfile": "max",
                "keepBounceOnDuringSleep": False,
                "keepBounceOnDuringSleepLevel": 0,
                "keepMusicOnDuringSleep": True,
                "keepMusicOnDuringSleepLevel": 2,
                "autoModeLockOn": False,
                "autoModeLockEndTime": "",
                "startRecipeOn": False,
                "startRecipeEnabled": False,
                "startRecipeLockEndTime": "",
                "startRecipeLockDuration": 15,
                "startRecipeBounceLevel": -1,
                "startRecipeMusicLevel": 2,
                "state": 1,
                "reportWrongStatus": "",
                "sequenceId": 0,
                "shadowSync": {"restartGGCRequest": False},
                "soundSynth": {
                    "ambience": 0,
                    "breathVolume": 0,
                    "color": 1,
                    "heartbeatVolume": 100,
                    "spotifyServiceEnable": True,
                },
                "update": {
                    "available": False,
                    "errReason": "none",
                    "first": False,
                    "progress": 0,
                    "status": "NONE",
                    "step": "download",
                    "type": "partial",
                    "version": "0.0",
                },
                "upload3DDataEnable": True,
                "uploadRGBDataEnable": True,
                "significantChangeInWeightEnable": False,
                "weightDetectionEnable": False,
            },
        },
        source="cloud",
    )

    device_state = store.snapshot()["device_state"]

    assert device_state["baby_present"] is True
    assert device_state["sleep_state"] == "asleep"
    assert device_state["sleep_phase"] == "sleep"
    assert device_state["sleep_phase_raw"] == 4
    assert device_state["sleep_event"] == "sleep"
    assert device_state["sleep_state_raw"] == 5
    assert device_state["sleep_state_internal"] == 0
    assert device_state["sleep_state_being_determined"] is False
    assert device_state["sleep_phase_event_start_time"] == "2026-06-24 02:10:31.856625"
    assert (
        device_state["sleep_phase_duration_start_time"] == "2026-06-24 01:08:31.968945"
    )
    assert (
        device_state["sleep_phase_present_toggle_time"] == "2026-06-24 01:08:20.242141"
    )
    assert device_state["baby_presence_being_determined"] is False
    assert device_state["baby_needs_attention"] is False
    assert device_state["baby_needs_help"] is False
    assert device_state["loud_sound_detected"] is False
    assert device_state["bouncing"] is False
    assert device_state["bounce_setting"] == 2
    assert device_state["bounce_level"] == 4
    assert device_state["bounce_mode"] == 1
    assert device_state["responsivity_setting"] == 3
    assert device_state["music_mode"] == 2
    assert device_state["music_playing"] is True
    assert device_state["music_volume"] == 4
    assert device_state["music_level"] == 5
    assert device_state["music_mood"] == "rain"
    assert device_state["light_intensity"] is None
    assert device_state["light_indicator_brightness"] == 30
    assert device_state["cradle_mode"] == "Crib"
    assert device_state["volume_profile"] == "max"
    assert device_state["music_duration"] == 60
    assert device_state["music_time_remaining"] == -1
    assert device_state["ambient_temperature"] == 23.75
    assert device_state["device_uptime_service"] == 35997.596906
    assert device_state["device_uptime_total"] == 36006.22
    assert device_state["reported_state"] == 1
    assert device_state["deploy_state"] == 4
    assert device_state["sequence_id"] == 0
    assert device_state["report_wrong_status"] == ""
    assert device_state["operation_state"] == 9
    assert device_state["calibrate_cradle"] == "idle"
    assert device_state["calibrate_cradle_raw"] == 0
    assert device_state["calibration_type"] == "partial"
    assert device_state["calibration_type_raw"] == 1
    assert device_state["calibration_stage"] == ""
    assert device_state["calibration_status"] == ""
    assert device_state["calibration_history_complete"] == "success"
    assert device_state["calibration_history_gain_setup"] == "success"
    assert device_state["calibration_history_mic_setup"] == "success"
    assert device_state["calibration_history_noise_profile_setup"] == "success"
    assert device_state["calibration_history_tof_calibration"] == "success"
    assert device_state["calibration_history_weight_calibration"] == "success"
    assert device_state["obstruction_detected"] is False
    assert device_state["user_action_for_obstruction"] == ""
    assert device_state["baby_present_previous"] is True
    assert device_state["bounce_disabled"] is True
    assert device_state["bounce_super_gentle"] is False
    assert device_state["bounce_always_on"] is False
    assert device_state["bounce_always_on_intensity"] == 3
    assert device_state["bounce_duration"] == 15
    assert device_state["bounce_duration_limit"] == 30
    assert device_state["bounce_time_remaining"] == 0
    assert device_state["bounce_tap_detection_enabled"] is True
    assert device_state["bounce_push_gesture_enabled"] is True
    assert device_state["bounce_quiescent"] is False
    assert device_state["bounce_tilt_state"] == 0
    assert device_state["bounce_movement_energy_threshold"] == 50
    assert device_state["bounce_acc_frame_peaks_threshold"] == 10
    assert device_state["wifi_score"] == 3
    assert device_state["wifi_score_snr"] == 3
    assert device_state["wifi_score_speed"] == 3
    assert device_state["wifi_score_loss"] == 3
    assert device_state["wifi_score_jitter"] == 3
    assert device_state["wifi_stats_strength"] == 77
    assert device_state["wifi_stats_rssi0"] == -50
    assert device_state["wifi_stats_rssi1"] == -44
    assert device_state["wifi_stats_noise"] == -85
    assert device_state["wifi_stats_bitrate"] == 72200000
    assert device_state["wifi_stats_ssid"] == "Nursery"
    assert device_state["wifi_stats_arp_success_count"] == 870870
    assert device_state["wifi_stats_beacon_loss_count"] == 1
    assert device_state["software_version"] == "0.2.72"
    assert device_state["rootfs_version"] == "6.25"
    assert device_state["shadow_version"] == 1
    assert device_state["cradle_timezone"] == "America/New_York"
    assert device_state["update_available"] is False
    assert device_state["update_status"] == "NONE"
    assert device_state["update_step"] == "download"
    assert device_state["update_version"] == "0.0"
    assert device_state["update_progress"] == 0
    assert device_state["update_type"] == "partial"
    assert device_state["update_error_reason"] == "none"
    assert device_state["control_adaptive_soothing_enabled"] is False
    assert device_state["control_bna_alert_control"] == 8
    assert device_state["control_breath_enabled"] is True
    assert device_state["control_cry_sensitivity"] == 1
    assert device_state["control_css_responsiveness"] == "low"
    assert device_state["control_video_service_bit_mask"] == 0
    assert device_state["breath_rate"] == -1
    assert device_state["breath_final_rate"] == -1
    assert device_state["breath_state"] == 0
    assert device_state["breath_reason"] == -1
    assert device_state["breath_trigger"] is False
    assert device_state["lower_breath_rate_alert"] is False
    assert device_state["keep_bounce_on_during_sleep"] is False
    assert device_state["keep_bounce_on_during_sleep_level"] == 0
    assert device_state["keep_music_on_during_sleep"] is True
    assert device_state["keep_music_on_during_sleep_level"] == 2
    assert device_state["auto_mode_lock_on"] is False
    assert device_state["auto_mode_lock_duration"] == 10
    assert device_state["auto_mode_lock_end_time"] == ""
    assert device_state["start_recipe_on"] is False
    assert device_state["start_recipe_enabled"] is False
    assert device_state["start_recipe_lock_end_time"] == ""
    assert device_state["start_recipe_lock_duration"] == 15
    assert device_state["start_recipe_bounce_level"] == -1
    assert device_state["start_recipe_music_level"] == 2
    assert device_state["sound_ambience"] == "light rain"
    assert device_state["sound_ambience_raw"] == 0
    assert device_state["sound_color"] == "pink"
    assert device_state["sound_color_raw"] == 1
    assert device_state["sound_heartbeat_volume"] == 100
    assert device_state["sound_breath_volume"] == 0
    assert device_state["sound_spotify_service_enabled"] is True
    assert device_state["lullabies_action"] == 1
    assert device_state["lullabies_current_song_id"] == "hpx4mmji"
    assert device_state["lullabies_desired_playlist_id"] == "bfalhqi6"
    assert device_state["lullabies_desired_song_id"] == ""
    assert device_state["lullabies_elapsed_time"] == 0
    assert device_state["lullabies_enabled"] is False
    assert device_state["lullabies_loop"] == "all"
    assert device_state["lullabies_timer_duration"] == 30
    assert device_state["lullabies_timer_on"] is False
    assert device_state["lullabies_volume"] == 45
    assert device_state["app_flip_video"] is False
    assert device_state["max_bounce_limit"] == 55
    assert device_state["max_volume_limit"] == 45
    assert device_state["max_sound_preview"] is False
    assert device_state["upload_3d_data_enabled"] is True
    assert device_state["upload_rgb_data_enabled"] is True
    assert device_state["significant_change_in_weight_enabled"] is False
    assert device_state["weight_detection_enabled"] is False
    assert device_state["restart_ggc_requested"] is False


def test_status_store_defaults_omitted_inactive_flags_from_live_shadow():
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
    store.update_device_state(
        {
            "rawShadow": {
                "bluetooth": {
                    "wifiStats": json.dumps(
                        {
                            "activeConnection": {"ssid": "Nursery-IoT"},
                            "rssi0": -50,
                            "strength": 77,
                        }
                    )
                },
                "light": {"indicatorBrightness": 0},
            }
        },
        source="cloud",
    )

    device_state = store.snapshot()["device_state"]

    assert device_state["crib_helping"] is False
    assert device_state["inside_sleep_schedule"] is False
    assert device_state["inside_soothing_window"] is False
    assert device_state["rocking_not_effective"] is False
    assert device_state["light_on"] is None
    assert device_state["light_intensity"] is None
    assert device_state["light_indicator_brightness"] == 0
    assert device_state["volume_profile"] == "normal"
    assert device_state["wifi_stats_ssid"] == "Nursery-IoT"
    assert device_state["wifi_stats_bitrate"] is None

    assert store.snapshot()["cradle_state"]["wifi_ssid"] == "Nursery-IoT"
    assert store.snapshot()["cradle_state"]["wifi_strength"] == -50
    assert store.snapshot()["cradle_state"]["local_ip"] == "192.0.2.10"


@pytest.mark.parametrize(
    ("raw_phase", "expected_phase"),
    [
        (0, "away"),
        (1, "awake"),
        (2, "stirring"),
        (3, "stirring"),
        (4, "sleep"),
        (5, "awake"),
        (6, "stirring"),
        (99, "unknown (99)"),
    ],
)
def test_status_store_maps_apk_sleep_phase_values(raw_phase, expected_phase):
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
    store.update_device_state(
        {"rawShadow": {"babySleepPhaseV2": {"eventValue": raw_phase}}},
        source="cloud",
    )

    device_state = store.snapshot()["device_state"]

    assert device_state["sleep_phase"] == expected_phase


@pytest.mark.parametrize(
    ("raw_phase", "expected_event"),
    [
        (0, "away"),
        (1, "awake"),
        (2, "awake"),
        (3, "stirring"),
        (4, "sleep"),
        (5, "sleep"),
        (6, "unknown (6)"),
    ],
)
def test_status_store_maps_apk_sleep_event_values(raw_phase, expected_event):
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")
    store.update_device_state(
        {"rawShadow": {"babySleepPhaseV2": {"eventValue": raw_phase}}},
        source="cloud",
    )

    device_state = store.snapshot()["device_state"]

    assert device_state["sleep_event"] == expected_event


def test_status_store_returns_json_bytes():
    store = BridgeStatusStore(cradle_id="cradle-1", crib_ip="192.0.2.10")

    payload = json.loads(store.to_json_bytes())

    assert payload["bridge"]["cradle_id"] == "cradle-1"
