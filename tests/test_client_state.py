from cradlewise_client.state import CradlewiseStateStore, normalize_device_state


def _local_state(**overrides):
    state = {
        "babyPresent": False,
        "babySleepPhaseV2": {"eventValue": 4},
        "babySleepState": 5,
        "actuator": {
            "on": True,
            "amplitude": 24,
            "duration": 15,
            "durationLimit": 30,
            "timeRemaining": 4,
        },
        "bounceLevel": 3,
        "bounceMode": 1,
        "soundSynth": {
            "play": True,
            "volume": 25,
            "trackName": "Calming Rain",
            "ambience": 0,
            "color": 1,
            "heartbeatVolume": 100,
            "breathVolume": 0,
        },
        "musicLevel": 2,
        "musicMode": 0,
        "musicDuration": 60,
        "musicTimeRemaining": 8,
        "light": {"lightOn": True},
        "deviceStatus": {"ambientTemp": 22350},
        "babyMonitor": {"breath": {"rate": 25}},
        "control": {"adaptiveSoothingEnabled": True},
        "maxBounceLimit": 80,
        "maxVolumeLimit": 70,
    }
    state.update(overrides)
    return {"state": {"reported": state}}


def test_normalizer_maps_public_state_surface():
    state = normalize_device_state(_local_state())

    assert (
        state["sleep_phase"],
        state["sleep_state"],
        state["ambient_temperature"],
        state["breath_rate"],
    ) == ("sleep", "Deep sleep", 22.35, 25)


def test_normalizer_rejects_boolean_as_number():
    state = normalize_device_state(_local_state(bounceLevel=True))

    assert state["bounce_level"] is None


def test_store_merges_partial_local_shadow_updates():
    store = CradlewiseStateStore("cradle-1")
    store.set_connected("local", True)
    store.update_device_state(_local_state(), "local", updated_at=1_000)
    store.update_device_state(
        {"state": {"reported": {"actuator": {"amplitude": 42}}}},
        "local",
        updated_at=1_001,
    )

    state = store.snapshot(now=1_002)["device_state"]

    assert (state["bounce_duration"], state["bounce_amplitude"]) == (15, 42)


def test_store_prefers_fresh_local_values_over_cloud():
    store = CradlewiseStateStore("cradle-1")
    store.set_connected("cloud", True)
    store.set_connected("local", True)
    store.update_device_state({"babyPresent": True}, "cloud", updated_at=1_000)
    store.update_device_state({"babyPresent": False}, "local", updated_at=1_001)

    state = store.snapshot(now=1_002)["device_state"]

    assert (state["baby_present"], state["source"]) == (False, "local")


def test_store_falls_back_after_local_state_becomes_stale():
    store = CradlewiseStateStore("cradle-1", local_stale_after=30, cloud_stale_after=90)
    store.set_connected("cloud", True)
    store.update_device_state({"babyPresent": True}, "cloud", updated_at=1_000)
    store.update_device_state({"babyPresent": False}, "local", updated_at=1_001)

    state = store.snapshot(now=1_032)["device_state"]

    assert (state["baby_present"], state["source"]) == (True, "cloud")


def test_connected_provider_state_does_not_expire_while_shadow_is_idle():
    store = CradlewiseStateStore("cradle-1", cloud_stale_after=90)
    store.set_connected("cloud", True)
    store.update_device_state({"babyPresent": True}, "cloud", updated_at=1_000)

    state = store.snapshot(now=2_000)["device_state"]

    assert (state["available"], state["baby_present"]) == (True, True)


def test_store_accepts_normalized_media_companion_state():
    store = CradlewiseStateStore("cradle-1")
    store.set_connected("local", True)
    store.update_normalized_device_state(
        {"baby_present": False, "sleep_phase": "away"},
        "local",
        updated_at=1_000,
    )

    state = store.snapshot(now=1_001)["device_state"]

    assert (state["baby_present"], state["sleep_phase"]) == (False, "away")


def test_store_never_overwrites_fresh_local_fields_with_cloud():
    store = CradlewiseStateStore("cradle-1")
    store.set_connected("cloud", True)
    store.set_connected("local", True)
    store.update_device_state(
        {"babyPresent": True, "musicDuration": 120},
        "cloud",
        updated_at=1_001,
    )
    store.update_device_state({"babyPresent": False}, "local", updated_at=1_000)

    state = store.snapshot(now=1_002)["device_state"]

    assert (state["baby_present"], state["music_duration"]) == (False, 120)


def test_store_exposes_source_error_without_losing_last_value():
    store = CradlewiseStateStore("cradle-1")
    store.set_connected("cloud", True)
    store.update_device_state({"babyPresent": True}, "cloud", updated_at=1_000)
    store.mark_error("cloud", "request timed out")

    state = store.snapshot(now=1_001)["device_state"]

    assert (state["baby_present"], state["sources"]["cloud"]["error"]) == (
        True,
        "request timed out",
    )
