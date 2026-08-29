import importlib.util
import sys
from pathlib import Path
from types import ModuleType

INTEGRATION_PATH = Path("custom_components/cradlewise")
PACKAGE = "_cradlewise_status_test"

package = ModuleType(PACKAGE)
package.__path__ = [str(INTEGRATION_PATH)]
sys.modules[PACKAGE] = package


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


config_helpers = _load_module(
    f"{PACKAGE}.config_helpers", INTEGRATION_PATH / "config_helpers.py"
)
helpers = _load_module(
    f"{PACKAGE}.status_helpers", INTEGRATION_PATH / "status_helpers.py"
)


def test_build_state_url_appends_state_to_base_url():
    assert helpers.build_state_url("http://bridge:8080") == "http://bridge:8080/state"
    assert helpers.build_state_url("http://bridge:8080/") == "http://bridge:8080/state"


def test_build_state_url_keeps_explicit_state_url():
    assert (
        helpers.build_state_url("http://bridge:8080/state")
        == "http://bridge:8080/state"
    )


def test_build_command_url_accepts_base_state_or_command_urls():
    assert (
        helpers.build_command_url("http://bridge:8080") == "http://bridge:8080/command"
    )
    assert (
        helpers.build_command_url("http://bridge:8080/state")
        == "http://bridge:8080/command"
    )
    assert (
        helpers.build_command_url("http://bridge:8080/command")
        == "http://bridge:8080/command"
    )


def test_health_url_replaces_any_supported_bridge_endpoint():
    assert {
        config_helpers.health_url_from_status_url("http://bridge:8080"),
        config_helpers.health_url_from_status_url("http://bridge:8080/state"),
        config_helpers.health_url_from_status_url("http://bridge:8080/live"),
    } == {"http://bridge:8080/health"}


def test_path_value_reads_nested_status_values():
    payload = {
        "bridge": {"healthy": True},
        "cradle_state": {"wifi_strength": -47},
    }

    assert helpers.path_value(payload, ("bridge", "healthy")) is True
    assert helpers.path_value(payload, ("cradle_state", "wifi_strength")) == -47
    assert helpers.path_value(payload, ("missing", "value")) is None


def test_strict_bool_does_not_treat_nonempty_false_string_as_true():
    assert helpers.strict_bool(True) is True
    assert helpers.strict_bool("true") is True
    assert helpers.strict_bool(1) is True
    assert helpers.strict_bool(False) is False
    assert helpers.strict_bool("false") is False
    assert helpers.strict_bool(0) is False
    assert helpers.strict_bool("unknown") is None
    assert helpers.strict_bool(2) is None
    assert helpers.strict_bool(None) is None


def test_bounded_numbers_reject_protocol_sentinels_and_nonfinite_values():
    assert helpers.bounded_number("4", minimum=0, maximum=5) == 4
    assert helpers.nonnegative_int(0) == 0
    assert helpers.positive_int(12) == 12

    assert helpers.bounded_number(-1, minimum=0) is None
    assert helpers.bounded_number(float("nan")) is None
    assert helpers.bounded_number(True) is None
    assert helpers.nonnegative_int(1.5) is None
    assert helpers.positive_int(0) is None


def test_timestamp_freshness_requires_a_current_source_timestamp():
    payload = {
        "device_state": {"updated_at": 1_000},
        "cradle_state": {"updated_at": 800},
    }
    paths = (
        ("cradle_state", "updated_at"),
        ("device_state", "updated_at"),
    )

    assert helpers.timestamp_is_fresh(payload, paths, 120, now=1_100)
    assert not helpers.timestamp_is_fresh(payload, paths, 60, now=1_100)
    assert not helpers.timestamp_is_fresh({}, paths, 120, now=1_100)
    assert not helpers.timestamp_is_fresh(
        {"device_state": {"updated_at": 1_500}},
        (("device_state", "updated_at"),),
        120,
        now=1_100,
    )


def test_device_availability_trusts_bridge_source_policy_before_timestamp():
    assert helpers.device_state_is_available(
        {
            "device_state": {
                "available": True,
                "stale": False,
                "updated_at": 1_000,
            }
        },
        120,
        now=10_000,
    )
    assert not helpers.device_state_is_available(
        {
            "device_state": {
                "available": False,
                "stale": True,
                "updated_at": 9_999,
            }
        },
        120,
        now=10_000,
    )


def test_device_availability_falls_back_for_older_bridge_payloads():
    assert helpers.device_state_is_available(
        {"device_state": {"updated_at": 1_000}},
        120,
        now=1_100,
    )
    assert not helpers.device_state_is_available(
        {"device_state": {"updated_at": 1_000}},
        120,
        now=1_121,
    )
