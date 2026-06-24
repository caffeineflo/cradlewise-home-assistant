import json
import importlib.util
from pathlib import Path


HELPERS_PATH = Path("custom_components/cradlewise_local/config_helpers.py")
spec = importlib.util.spec_from_file_location("cradlewise_local_config_helpers", HELPERS_PATH)
helpers = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(helpers)


def test_manifest_is_custom_config_flow_integration():
    manifest = json.loads(
        Path("custom_components/cradlewise_local/manifest.json").read_text()
    )

    assert manifest["domain"] == "cradlewise_local"
    assert manifest["codeowners"] == ["@caffeineflo"]
    assert manifest["config_flow"] is True
    assert manifest["documentation"] == "https://github.com/caffeineflo/cradlewise-local"
    assert manifest["iot_class"] == "local_push"
    assert manifest["issue_tracker"] == "https://github.com/caffeineflo/cradlewise-local/issues"
    assert manifest["version"] == "0.1.0"


def test_hacs_metadata_and_brand_asset_exist():
    hacs = json.loads(Path("hacs.json").read_text())

    assert hacs["name"] == "Cradlewise Local"
    assert hacs["homeassistant"] >= "2026.5.0"
    assert Path("brands/cradlewise_local/icon.png").exists()


def test_public_repo_scaffolding_exists():
    assert Path("CODEOWNERS").read_text().strip() == "* @caffeineflo"
    assert Path(".github/workflows/tests.yml").exists()
    assert Path(".env.example").exists()
    assert Path("examples/docker-compose.yaml").exists()


def test_url_helpers_accept_expected_bridge_urls():
    assert helpers.is_rtsp_url("rtsp://192.0.2.20:8560/cradlewise")
    assert helpers.is_http_url("http://127.0.0.1:8088/snapshot.jpg")
    assert helpers.is_http_url("http://127.0.0.1:8080/state")
    assert helpers.is_http_url("https://homeassistant.example/local/cradlewise.jpg")


def test_snapshot_url_defaults_to_bridge_status_endpoint():
    assert (
        helpers.snapshot_url_from_status_url("http://127.0.0.1:8088/state")
        == "http://127.0.0.1:8088/snapshot.jpg"
    )
    assert (
        helpers.snapshot_url_from_status_url("http://127.0.0.1:8088/api/state")
        == "http://127.0.0.1:8088/api/snapshot.jpg"
    )


def test_url_helpers_reject_wrong_schemes_or_missing_hosts():
    assert not helpers.is_rtsp_url("http://127.0.0.1:8554/cradlewise")
    assert not helpers.is_rtsp_url("rtsp:///cradlewise")
    assert not helpers.is_http_url("rtsp://127.0.0.1:8554/cradlewise")
    assert not helpers.is_http_url("https:///snapshot.jpg")


def test_status_entities_include_community_state_surface():
    init_source = Path("custom_components/cradlewise_local/__init__.py").read_text()
    sensor_source = Path("custom_components/cradlewise_local/sensor.py").read_text()
    binary_source = Path("custom_components/cradlewise_local/binary_sensor.py").read_text()
    switch_source = Path("custom_components/cradlewise_local/switch.py").read_text()
    number_source = Path("custom_components/cradlewise_local/number.py").read_text()
    select_source = Path("custom_components/cradlewise_local/select.py").read_text()

    for platform in ("Platform.NUMBER", "Platform.SELECT", "Platform.SWITCH"):
        assert platform in init_source

    for key in (
        "sleep_phase",
        "sleep_phase_raw",
        "sleep_event",
        "sleep_state_raw",
        "ambient_temperature",
        "operation_state",
        "reported_state",
        "deploy_state",
        "calibrate_cradle",
        "calibration_type",
        "calibration_history_complete",
        "cradle_mode_to_calibrate",
        "bounce_duration",
        "bounce_time_remaining",
        "sound_ambience",
        "sound_color",
        "lullabies_current_song_id",
        "lullabies_timer_duration",
        "wifi_score",
        "wifi_stats_strength",
        "wifi_stats_rssi0",
        "software_version",
        "update_status",
        "control_cry_sensitivity",
        "breath_rate",
        "device_state_source",
        "device_state_updated_at",
        "bounce_mode",
        "bounce_level",
        "music_volume",
        "music_level",
        "volume_profile",
        "light_intensity",
        "battery_life",
    ):
        assert f'key="{key}"' in sensor_source

    for key in (
        "baby_present",
        "baby_present_previous",
        "has_baby_ever_been_placed",
        "baby_needs_attention",
        "bouncing",
        "bounce_disabled",
        "bounce_tap_detection_enabled",
        "music_playing",
        "lullabies_enabled",
        "sound_spotify_service_enabled",
        "light_on",
        "obstruction_detected",
        "breath_trigger",
        "auto_mode_lock_on",
        "update_available",
        "control_breath_enabled",
        "upload_3d_data_enabled",
        "upload_rgb_data_enabled",
        "charging",
    ):
        assert f'key="{key}"' in binary_source

    for key in (
        "actuator_on",
        "disable_bounce",
        "super_gentle_bounce",
        "always_on_bounce",
        "tap_detection_enabled",
        "push_gesture_enabled",
        "music_playing",
        "keep_music_on_during_sleep",
        "keep_bounce_on_during_sleep",
        "auto_mode_lock_on",
        "start_recipe_enabled",
        "adaptive_soothing_enabled",
    ):
        assert f'key="{key}"' in switch_source

    for key in (
        "bounce_level",
        "music_level",
        "bounce_amplitude",
        "bounce_duration",
        "always_on_bounce_intensity",
        "keep_music_on_during_sleep_level",
        "keep_bounce_on_during_sleep_level",
        "music_duration",
        "auto_mode_lock_duration",
        "max_bounce_limit",
        "max_volume_limit",
        "start_recipe_music_level",
        "start_recipe_bounce_level",
        "start_recipe_lock_duration",
        "music_volume",
        "light_indicator_brightness",
    ):
        assert f'key="{key}"' in number_source

    for key in (
        "bounce_mode",
        "music_mode",
        "volume_profile",
        "light_indicator_mode",
        "cry_sensitivity",
    ):
        assert f'key="{key}"' in select_source
