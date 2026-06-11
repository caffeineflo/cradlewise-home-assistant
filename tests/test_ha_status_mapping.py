import importlib.util
from pathlib import Path


HELPERS_PATH = Path("custom_components/cradlewise_local/status_helpers.py")
spec = importlib.util.spec_from_file_location("cradlewise_local_status_helpers", HELPERS_PATH)
helpers = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(helpers)


def test_build_state_url_appends_state_to_base_url():
    assert helpers.build_state_url("http://bridge:8080") == "http://bridge:8080/state"
    assert helpers.build_state_url("http://bridge:8080/") == "http://bridge:8080/state"


def test_build_state_url_keeps_explicit_state_url():
    assert helpers.build_state_url("http://bridge:8080/state") == "http://bridge:8080/state"


def test_path_value_reads_nested_status_values():
    payload = {
        "bridge": {"healthy": True},
        "cradle_state": {"wifi_strength": -47},
    }

    assert helpers.path_value(payload, ("bridge", "healthy")) is True
    assert helpers.path_value(payload, ("cradle_state", "wifi_strength")) == -47
    assert helpers.path_value(payload, ("missing", "value")) is None
