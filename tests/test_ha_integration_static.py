import ast
import importlib.util
import json
import sys
from pathlib import Path

INTEGRATION_PATH = Path("custom_components/cradlewise_local")


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


helpers = _load_module(
    "cradlewise_local_config_helpers", INTEGRATION_PATH / "config_helpers.py"
)
policy = _load_module(
    "cradlewise_local_entity_policy", INTEGRATION_PATH / "entity_policy.py"
)


def _call_name(call: ast.Call) -> str:
    assert isinstance(call.func, ast.Name)
    return call.func.id


def _description_policy(
    filename: str,
    collection_name: str,
    disabled_helpers: set[str],
) -> tuple[set[str], set[str]]:
    tree = ast.parse((INTEGRATION_PATH / filename).read_text())
    collection = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == collection_name
    )
    assert isinstance(collection, ast.Tuple)

    keys: set[str] = set()
    disabled: set[str] = set()
    for element in collection.elts:
        assert isinstance(element, ast.Call)
        key_keyword = next(
            keyword for keyword in element.keywords if keyword.arg == "key"
        )
        assert isinstance(key_keyword.value, ast.Constant)
        key = key_keyword.value.value
        assert isinstance(key, str)
        assert key not in keys
        keys.add(key)

        explicitly_disabled = any(
            keyword.arg == "entity_registry_enabled_default"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is False
            for keyword in element.keywords
        )
        if _call_name(element) in disabled_helpers or explicitly_disabled:
            disabled.add(key)
    return keys, disabled


def _description_call(filename: str, collection_name: str, key: str) -> ast.Call:
    tree = ast.parse((INTEGRATION_PATH / filename).read_text())
    collection = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == collection_name
    )
    assert isinstance(collection, ast.Tuple)
    for element in collection.elts:
        assert isinstance(element, ast.Call)
        key_keyword = next(
            keyword for keyword in element.keywords if keyword.arg == "key"
        )
        if ast.literal_eval(key_keyword.value) == key:
            return element
    raise AssertionError(f"Missing {key} in {filename}")


def _keyword_value(call: ast.Call, name: str):
    keyword = next(keyword for keyword in call.keywords if keyword.arg == name)
    return ast.literal_eval(keyword.value)


def _assigned_literal(filename: str, name: str):
    tree = ast.parse((INTEGRATION_PATH / filename).read_text())
    value = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == name
    )
    return ast.literal_eval(value)


def _surface() -> dict[str, tuple[set[str], set[str]]]:
    return {
        "binary_sensor": _description_policy(
            "binary_sensor.py", "BINARY_SENSORS", set()
        ),
        "sensor": _description_policy("sensor.py", "SENSORS", {"_diagnostic"}),
        "number": _description_policy("number.py", "NUMBERS", {"_config_number"}),
        "select": _description_policy("select.py", "SELECTS", {"_config_select"}),
        "switch": _description_policy("switch.py", "SWITCHES", {"_config_switch"}),
        "camera": ({"camera"}, set()),
        "update": ({"firmware"}, {"firmware"}),
    }


def test_manifest_is_local_polling_config_flow_integration():
    manifest = json.loads((INTEGRATION_PATH / "manifest.json").read_text())

    assert manifest["domain"] == "cradlewise_local"
    assert manifest["codeowners"] == ["@caffeineflo"]
    assert manifest["config_flow"] is True
    assert (
        manifest["documentation"] == "https://github.com/caffeineflo/cradlewise-local"
    )
    assert manifest["integration_type"] == "device"
    assert manifest["iot_class"] == "local_polling"
    assert (
        manifest["issue_tracker"]
        == "https://github.com/caffeineflo/cradlewise-local/issues"
    )
    assert manifest["version"] == "0.1.0"
    assert manifest["name"] == "Cradlewise"


def test_package_and_integration_versions_match():
    manifest = json.loads((INTEGRATION_PATH / "manifest.json").read_text())
    project = Path("pyproject.toml").read_text()
    version_line = next(
        line for line in project.splitlines() if line.startswith("version = ")
    )

    assert version_line == f'version = "{manifest["version"]}"'


def test_hacs_metadata_and_brand_asset_exist():
    hacs = json.loads(Path("hacs.json").read_text())

    assert hacs["name"] == "Cradlewise"
    assert hacs["homeassistant"] >= "2026.5.0"
    assert (INTEGRATION_PATH / "brand/icon.png").exists()


def test_public_repo_scaffolding_exists():
    assert Path("CODEOWNERS").read_text().strip() == "* @caffeineflo"
    assert Path(".github/workflows/tests.yml").exists()
    assert Path(".env.example").exists()
    assert Path("examples/docker-compose.yaml").exists()
    assert Path("LICENSE").exists()
    assert Path("CHANGELOG.md").exists()
    assert Path("CONTRIBUTING.md").exists()
    assert Path("SECURITY.md").exists()


def test_url_helpers_validate_hosts_schemes_and_ports():
    assert helpers.is_rtsp_url("rtsp://192.0.2.20:8560/cradlewise")
    assert helpers.is_rtsp_url("rtsps://[2001:db8::1]:8560/cradlewise")
    assert helpers.is_http_url("http://127.0.0.1:8088/snapshot.jpg")
    assert helpers.is_http_url("https://homeassistant.example/local/cradlewise.jpg")

    assert not helpers.is_rtsp_url("http://127.0.0.1:8554/cradlewise")
    assert not helpers.is_rtsp_url("rtsp:///cradlewise")
    assert not helpers.is_http_url("rtsp://127.0.0.1:8554/cradlewise")
    assert not helpers.is_http_url("https:///snapshot.jpg")
    assert not helpers.is_http_url("http://bridge:70000/state")


def test_url_helpers_replace_only_the_endpoint_path_segment():
    assert (
        helpers.snapshot_url_from_status_url(
            "http://state-bridge:8088/api/state?mode=state"
        )
        == "http://state-bridge:8088/api/snapshot.jpg?mode=state"
    )
    assert (
        helpers.state_url_from_status_url("http://bridge:8088/api/command")
        == "http://bridge:8088/api/state"
    )
    assert (
        helpers.command_url_from_status_url("http://bridge:8088/api/state")
        == "http://bridge:8088/api/command"
    )
    assert (
        helpers.bridge_base_url(
            "https://user:secret@bridge.local:8443/api/state?token=secret"
        )
        == "https://bridge.local:8443/api"
    )


def test_bearer_auth_is_limited_to_the_bridge_origin():
    assert helpers.same_url_origin(
        "https://bridge.local/state",
        "https://bridge.local:443/snapshot.jpg",
    )
    assert not helpers.same_url_origin(
        "https://bridge.local/state",
        "http://bridge.local/snapshot.jpg",
    )
    assert not helpers.same_url_origin(
        "https://bridge.local/state",
        "https://snapshot-proxy.local/snapshot.jpg",
    )


def test_entity_surface_is_exactly_35_enabled_and_78_disabled():
    surface = _surface()
    enabled = sum(len(keys - disabled) for keys, disabled in surface.values())
    disabled = sum(len(disabled) for _, disabled in surface.values())

    assert enabled == policy.DEFAULT_ENABLED_ENTITY_COUNT == 35
    assert disabled == policy.DISABLED_ENTITY_COUNT == 78
    assert sum(len(keys) for keys, _ in surface.values()) == 113


def test_official_sleep_analytics_are_enabled_by_default():
    sensor_keys, disabled = _surface()["sensor"]

    assert {
        "total_sleep_today",
        "day_sleep_today",
        "night_sleep_today",
        "naps_today",
        "longest_stretch_today",
        "soothes_today",
    } <= sensor_keys - disabled


def test_entity_migration_policy_matches_platform_defaults_and_pruning():
    surface = _surface()

    for domain, (keys, disabled) in surface.items():
        domain_policy = policy.ENTITY_POLICIES.get(domain)
        if domain_policy is None:
            assert not disabled
            continue
        assert disabled == set(domain_policy.disabled)
        assert keys.isdisjoint(domain_policy.removed)

    assert (
        sum(
            len(domain_policy.removed)
            for domain_policy in policy.ENTITY_POLICIES.values()
        )
        == 112
    )


def test_writable_ui_matches_discrete_and_dynamic_command_contracts():
    surface = _surface()
    number_keys = surface["number"][0]
    select_keys = surface["select"][0]
    discrete_keys = {
        "music_duration",
        "responsivity_setting",
        "start_recipe_music_level",
        "start_recipe_bounce_level",
        "start_recipe_lock_duration",
    }

    assert discrete_keys.isdisjoint(number_keys)
    assert discrete_keys <= select_keys
    assert set(_assigned_literal("select.py", "MUSIC_DURATION_VALUES").values()) == {
        -1,
        60,
        180,
    }
    assert set(_assigned_literal("select.py", "RESPONSIVITY_VALUES").values()) == {
        2,
        4,
        6,
        8,
        10,
    }
    assert _assigned_literal("select.py", "RECIPE_LEVEL_VALUES") == {
        "Off": -1,
        "Gentle": 0,
        "Level 1": 1,
        "Level 2": 2,
        "Level 3": 3,
        "Level 4": 4,
    }
    assert set(
        _assigned_literal("select.py", "RECIPE_LOCK_DURATION_VALUES").values()
    ) == {10, 20, 30}

    auto_lock = _description_call("number.py", "NUMBERS", "auto_mode_lock_duration")
    assert _keyword_value(auto_lock, "native_min_value") == 1
    assert _keyword_value(auto_lock, "native_max_value") == 60

    dynamic_limits = {
        "bounce_amplitude": ("device_state", "max_bounce_limit"),
        "bounce_duration": ("device_state", "bounce_duration_limit"),
        "music_volume": ("device_state", "max_volume_limit"),
    }
    for key, limit_path in dynamic_limits.items():
        call = _description_call("number.py", "NUMBERS", key)
        assert _keyword_value(call, "limit_path") == limit_path


def test_flipbook_automation_anchor_entities_remain_enabled():
    surface = _surface()
    enabled = {key for keys, disabled in surface.values() for key in keys - disabled}

    assert {
        "baby_present",
        "baby_needs_attention",
        "baby_needs_help",
        "loud_sound_detected",
        "sleep_phase",
        "sleep_state",
    } <= enabled


def test_all_entity_translation_keys_have_english_names():
    strings = json.loads((INTEGRATION_PATH / "strings.json").read_text())
    translations = json.loads((INTEGRATION_PATH / "translations/en.json").read_text())

    assert translations == strings
    for domain, (keys, _) in _surface().items():
        translated = strings["entity"][domain]
        assert set(translated) == keys
        assert all(item["name"] for item in translated.values())


def test_config_flow_supports_validated_reconfigure_and_bearer_auth():
    source = (INTEGRATION_PATH / "config_flow.py").read_text()
    coordinator_source = (INTEGRATION_PATH / "coordinator.py").read_text()
    camera_source = (INTEGRATION_PATH / "camera.py").read_text()
    diagnostics_source = (INTEGRATION_PATH / "diagnostics.py").read_text()

    assert "VERSION = 2" in source
    assert "MINOR_VERSION = 1" in source
    assert "async_step_reconfigure" in source
    assert "async_update_reload_and_abort" in source
    assert "async_fetch_bridge_state" in source
    assert "CONF_BEARER_TOKEN" in source
    assert "stored_bearer_token" in source
    assert "if key != CONF_BEARER_TOKEN" in source
    assert "CONF_BEARER_TOKEN" in coordinator_source
    assert "request_headers" in camera_source
    assert "same_url_origin" in camera_source
    assert '("bridge", "healthy")' in camera_source
    assert "TO_REDACT" in diagnostics_source


def test_runtime_uses_typed_config_entry_data_and_update_platform():
    source = (INTEGRATION_PATH / "__init__.py").read_text()

    assert "CradlewiseRuntimeData" in source
    assert "ConfigEntry[CradlewiseRuntimeData]" in source
    assert "entry.runtime_data" in source
    assert "Platform.UPDATE" in source
    assert "async_migrate_entry" in source
