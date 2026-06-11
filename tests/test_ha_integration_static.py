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


def test_url_helpers_reject_wrong_schemes_or_missing_hosts():
    assert not helpers.is_rtsp_url("http://127.0.0.1:8554/cradlewise")
    assert not helpers.is_rtsp_url("rtsp:///cradlewise")
    assert not helpers.is_http_url("rtsp://127.0.0.1:8554/cradlewise")
    assert not helpers.is_http_url("https:///snapshot.jpg")


def test_status_entities_include_community_state_surface():
    sensor_source = Path("custom_components/cradlewise_local/sensor.py").read_text()
    binary_source = Path("custom_components/cradlewise_local/binary_sensor.py").read_text()

    for key in (
        "sleep_phase",
        "bounce_mode",
        "music_volume",
        "light_intensity",
        "battery_life",
    ):
        assert f'key="{key}"' in sensor_source

    for key in (
        "baby_present",
        "baby_needs_attention",
        "bouncing",
        "music_playing",
        "light_on",
        "charging",
    ):
        assert f'key="{key}"' in binary_source
