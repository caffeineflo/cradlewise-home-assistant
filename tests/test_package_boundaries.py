import json
import re
from pathlib import Path


def _project_version(pyproject: str) -> str:
    match = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)
    assert match is not None
    return match.group(1)


def _dependency_block(pyproject: str) -> str:
    match = re.search(
        r"^dependencies = \[\n(?P<dependencies>.*?)^\]$",
        pyproject,
        re.MULTILINE | re.DOTALL,
    )
    assert match is not None
    return match.group("dependencies")


def test_client_package_is_independent_from_media_and_home_assistant() -> None:
    package = Path("packages/cradlewise-client")
    project = (package / "pyproject.toml").read_text(encoding="utf-8")
    dependencies = _dependency_block(project)
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (package / "src/cradlewise_client").glob("*.py")
    )

    assert "aiortc" not in dependencies
    assert "numpy" not in dependencies
    assert "homeassistant" not in dependencies
    assert "aiortc" not in source
    assert "homeassistant" not in source


def test_integration_pins_the_workspace_client_release() -> None:
    package = Path("packages/cradlewise-client/pyproject.toml").read_text(
        encoding="utf-8"
    )
    manifest = json.loads(
        Path("custom_components/cradlewise/manifest.json").read_text(encoding="utf-8")
    )
    version = _project_version(package)

    assert manifest["requirements"] == [f"cradlewise-client=={version}"]


def test_bridge_consumes_the_workspace_client_instead_of_bundling_it() -> None:
    root = Path("pyproject.toml").read_text(encoding="utf-8")

    assert 'packages = ["cradlewise_local"]' in root
    assert "cradlewise-client = {workspace = true}" in root
