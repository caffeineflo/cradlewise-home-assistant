import ast
import json
from pathlib import Path

INTEGRATION_PATH = Path("custom_components/cradlewise")


def _keys(filename: str, assignment: str) -> set[str]:
    tree = ast.parse((INTEGRATION_PATH / filename).read_text(encoding="utf-8"))
    for node in tree.body:
        matches_assignment = isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == assignment
            for target in node.targets
        )
        matches_annotation = (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == assignment
        )
        if matches_assignment or matches_annotation:
            value = node.value
            assert isinstance(value, (ast.List, ast.Tuple))
            result = set()
            for item in value.elts:
                assert isinstance(item, ast.Call)
                for keyword in item.keywords:
                    if keyword.arg == "key":
                        result.add(ast.literal_eval(keyword.value))
                        break
            return result
    raise AssertionError(f"{assignment} not found in {filename}")


def test_manifest_is_a_hacs_compatible_device_integration() -> None:
    manifest = json.loads(
        (INTEGRATION_PATH / "manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["domain"] == "cradlewise"
    assert manifest["name"] == "Cradlewise"
    assert manifest["config_flow"] is True
    assert manifest["integration_type"] == "device"
    assert manifest["iot_class"] == "local_push"
    assert manifest["dependencies"] == []
    assert manifest["after_dependencies"] == ["ffmpeg", "stream"]
    assert manifest["requirements"] == ["cradlewise-client==0.1.0"]
    assert manifest["version"]
    assert manifest["codeowners"] == ["@caffeineflo"]


def test_repository_contains_exactly_one_custom_integration_manifest() -> None:
    manifests = sorted(Path("custom_components").glob("*/manifest.json"))

    assert manifests == [INTEGRATION_PATH / "manifest.json"]


def test_entity_surface_is_intentionally_bounded() -> None:
    keys = {
        "binary_sensor": _keys("binary_sensor.py", "BINARY_SENSORS"),
        "number": _keys("number.py", "NUMBERS"),
        "select": _keys("select.py", "SELECTS"),
        "sensor": _keys("sensor.py", "SENSORS"),
        "switch": _keys("switch.py", "SWITCHES"),
    }

    assert {domain: len(values) for domain, values in keys.items()} == {
        "binary_sensor": 10,
        "number": 5,
        "select": 3,
        "sensor": 9,
        "switch": 3,
    }
    assert "reported_state" not in set().union(*keys.values())
    assert "upload_rgb_data_enabled" not in set().union(*keys.values())
    assert "calibrate_cradle" not in set().union(*keys.values())


def test_camera_is_only_created_when_media_is_configured() -> None:
    source = (INTEGRATION_PATH / "camera.py").read_text(encoding="utf-8")

    assert "if not config.get(CONF_STREAM_URL):" in source
    assert "return" in source


def test_account_and_certificate_secrets_are_redacted() -> None:
    source = (INTEGRATION_PATH / "diagnostics.py").read_text(encoding="utf-8")

    for constant in (
        "CONF_PASSWORD",
        "CONF_CLIENT_CERTIFICATE",
        "CONF_CLIENT_PRIVATE_KEY",
        "CONF_GROUP_CA_CERTIFICATE",
        "CONF_SERVER_CA_CERTIFICATE",
        "CONF_BEARER_TOKEN",
    ):
        assert constant in source.split("TO_REDACT =", 1)[1].split("}", 1)[0]


def test_local_only_flow_does_not_persist_account_password() -> None:
    source = (INTEGRATION_PATH / "config_flow.py").read_text(encoding="utf-8")

    assert (
        "if self._mode in {CONNECTION_MODE_AUTOMATIC, CONNECTION_MODE_CLOUD}:" in source
    )
    assert "data[CONF_PASSWORD] = self._password" in source


def test_english_translation_matches_source_strings() -> None:
    strings = json.loads(
        (INTEGRATION_PATH / "strings.json").read_text(encoding="utf-8")
    )
    translation = json.loads(
        (INTEGRATION_PATH / "translations/en.json").read_text(encoding="utf-8")
    )

    assert translation == strings


def test_invalid_cradle_error_has_an_english_translation() -> None:
    strings = json.loads(
        (INTEGRATION_PATH / "strings.json").read_text(encoding="utf-8")
    )

    assert "invalid_cradle" in strings["config"]["error"]


def test_brand_asset_is_present() -> None:
    assert (INTEGRATION_PATH / "brand/icon.png").is_file()


def test_hacs_manifest_matches_the_tested_home_assistant_baseline() -> None:
    hacs = json.loads(Path("hacs.json").read_text(encoding="utf-8"))

    assert hacs == {"name": "Cradlewise", "homeassistant": "2026.7.0"}
